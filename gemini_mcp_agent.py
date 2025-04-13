import os
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
import asyncio
from google import genai
from concurrent.futures import TimeoutError
from functools import partial
import json
import re
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create file handler
file_handler = logging.FileHandler('output.txt')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Load environment variables
load_dotenv()

# Initialize Gemini client
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("Please set GEMINI_API_KEY environment variable")

client = genai.Client(api_key=api_key)

async def generate_with_timeout(client, prompt, timeout=10):
    """Generate content with a timeout using Gemini"""
    try:
        loop = asyncio.get_event_loop()
        
        # Add explicit JSON structure request
        prompt += "\n\nYou MUST respond with a valid JSON object in one of these two formats:\n"
        prompt += '''For tool calls:
{
    "type": "tool_call",
    "tool": {
        "name": "tool_name",
        "parameters": {
            "param1": "value1"
        }
    },
    "reasoning": "explanation"
}

For final answers:
{
    "type": "final_answer",
    "response": "your response here",
    "reasoning": "explanation"
}'''
        
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None, 
                lambda: client.models.generate_content(
                    model= "gemini-2.0-flash",
                    contents=[prompt]
                )
            ),
            timeout=timeout
        )
        return response
    except TimeoutError:
        logger.error("LLM generation timed out!")
        raise
    except Exception as e:
        logger.error(f"Error in LLM generation: {e}")
        raise

class GeminiMCPAgent:
    # Context prompt with all necessary checks
    CONTEXT_PROMPT = '''You are an AI assistant that helps users with drawing tasks using Pinta tools.

Your task is to:
1. Understand the user's drawing request
2. Break it down into simple steps taking screen resolution into account and draw in center of screen
3. Use available tools to execute each step
4. Verify the results
5. Provide clear feedback

Important Guidelines:
- Always use the get_screen_size() tool first to determine screen dimensions
- Center drawings by calculating coordinates based on screen size
- Keep drawings proportional to screen size
- Use appropriate tool parameters for screen scale
- Perform self-checks at each step
- Tag reasoning types (arithmetic, logic, lookup)
- Handle uncertainties gracefully

Self-Check Protocol:
1. Before each action:
   - Verify screen dimensions match previous measurements
   - Confirm coordinates are within bounds
   - Check tool parameters are valid
2. After each action:
   - Verify tool execution was successful
   - Confirm results match expectations
   - Check for any errors or exceptions

Reasoning Type Tags:
- Use [ARITHMETIC] for calculations (coordinates, dimensions)
- Use [LOGIC] for decision making (tool selection, parameter validation)
- Use [LOOKUP] for tool information and capabilities

Fallback Procedures:
1. If tool fails:
   - Try alternative tools
   - Adjust parameters
   - Request user clarification
2. If calculation fails:
   - Use default safe values
   - Scale down the drawing
   - Center the drawing
3. If uncertain:
   - Ask for user confirmation
   - Provide multiple options
   - Suggest simpler alternatives

Available Tools:
{tools_description}

When responding:
1. For using a tool: Return a JSON with "type": "tool_call"
2. For final answers: Return a JSON with "type": "final_answer"
3. Always include your reasoning with type tags
4. Keep responses concise and focused
5. Include self-check results
6. Suggest fallbacks if needed
'''

    def __init__(self):
        """Initialize the Gemini-powered MCP agent."""
        self.tools = []
        self.tools_description = []
        self.iteration = 0
        self.iteration_response = []
        self.session = None
        self._client = None
        self._read = None
        self._write = None
        self.max_iterations = 10
    
    async def initialize(self, server_params):
        """Initialize the MCP session and get available tools."""
        self._client = stdio_client(server_params)
        self._read, self._write = await self._client.__aenter__()
        self.session = ClientSession(self._read, self._write)
        await self.session.__aenter__()
        await self.session.initialize()
        
        # Get available tools
        tools_result = await self.session.list_tools()
        self.tools = tools_result.tools
        
        # Create tools description for the prompt
        for i, tool in enumerate(self.tools):
            params = tool.inputSchema
            desc = getattr(tool, 'description', 'No description available')
            name = getattr(tool, 'name', f'tool_{i}')
            
            if 'properties' in params:
                param_details = []
                for param_name, param_info in params['properties'].items():
                    param_type = param_info.get('type', 'unknown')
                    param_details.append(f"{param_name}: {param_type}")
                params_str = ', '.join(param_details)
            else:
                params_str = 'no parameters'

            self.tools_description.append(f"{name}({params_str}) - {desc}")
        
        return self.tools_description

    async def cleanup(self):
        """Cleanup resources properly."""
        if self.session:
            await self.session.__aexit__(None, None, None)
        if self._client:
            await self._client.__aexit__(None, None, None)

    def _parse_tool_call(self, text):
        """Parse tool name and arguments from response text.
        
        Args:
            text (str): Raw response text from the LLM
            
        Returns:
            tuple: (tool_name, arguments) or ("FINAL_ANSWER", response_text)
            None: If parsing fails
        """
        try:
            # Clean the text by removing leading/trailing whitespace and any markdown code block markers
            cleaned_text = text.strip()
            cleaned_text = re.sub(r'^```json\s*|\s*```$', '', cleaned_text, flags=re.MULTILINE)
            
            # Try to parse the JSON response
            try:
                response = json.loads(cleaned_text)
            except json.JSONDecodeError as e:
                # Try to extract JSON from the text if it's wrapped in other text
                json_match = re.search(r'\{.*?\}', cleaned_text, re.DOTALL)
                if json_match:
                    try:
                        response = json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        raise ValueError(f"Failed to parse JSON response: {e}\nRaw text: {repr(cleaned_text)}")
                else:
                    raise ValueError(f"Failed to parse JSON response: {e}\nRaw text: {repr(cleaned_text)}")
            
            # Validate response structure
            if not isinstance(response, dict):
                raise ValueError(f"Response is not a dictionary: {repr(response)}")
            
            # Check response type
            if "type" not in response:
                raise KeyError("Missing 'type' field in response")
            
            response_type = response["type"]
            
            if response_type == "tool_call":
                # Validate tool call structure
                if "tool" not in response or not isinstance(response["tool"], dict):
                    raise KeyError("Missing or invalid 'tool' field in tool_call response")
                
                tool_name = response["tool"].get("name")
                arguments = response["tool"].get("parameters", {})
                
                if not tool_name:
                    raise KeyError("Missing 'name' in tool specification")
                
                # Self-check: Verify tool exists
                if tool_name not in [t.name for t in self.tools]:
                    raise ValueError(f"Unknown tool: {tool_name}")
                
                return tool_name, arguments
            
            elif response_type == "final_answer":
                # Validate final answer structure
                if "response" not in response:
                    raise KeyError("Missing 'response' field in final_answer")
                
                return "FINAL_ANSWER", response["response"]
            
            else:
                raise ValueError(f"Invalid response type: {response_type}")
                
        except Exception as e:
            logger.error(f"Error parsing response: {str(e)}")
            logger.error("Raw text: %s", repr(text))
            return None, None

    async def process_request(self, user_request: str) -> str:
        """Process a user request using Gemini and MCP tools."""
        if not self.session:
            raise ValueError("Agent not initialized. Call initialize() first.")

        self.iteration = 0
        self.iteration_response = []
        #pdb.set_trace()

        while self.iteration < self.max_iterations:
            try:
                logger.info(f"\n--- Iteration {self.iteration + 1} ---")
                if self.iteration_response is None:
                    current_query = user_request
                else:
                    current_query = user_request + "\n\n" + " ".join(self.iteration_response)
                    current_query = current_query + "  What should I do next?"
                # Create prompt with context
                logger.info("Created system prompt...")
                #pdb.set_trace()
                
                context = self.CONTEXT_PROMPT.format(tools_description="\n".join([
                    f"- {desc}" for desc in self.tools_description
                ]))
                #pdb.set_trace()

                
                # Add history
                if self.iteration_response:
                    context += f"\n\nPrevious actions: {'; '.join(self.iteration_response)}"
                context += f"\n\nUser Request: {current_query}"

                logger.info("\nProcessing request: %s", current_query)
                logger.info("\nSending context to LLM: %s", context)
                #pdb.set_trace()
                
                # Generate response using Gemini
                try:
                    logger.info("\nFull system prompt:")
                    logger.info("=" * 80)
                    logger.info(context)
                    logger.info("=" * 80)
                    
                    response = await generate_with_timeout(client, context)

                    #pdb.set_trace()
                    if not response:
                        return "Failed to get response from LLM"
                    
                    # Get response text and debug
                    text = response.text
                    logger.info("\nRaw response object: %s", response)
                    logger.info("\nRaw response text: %s", repr(text))
                    
                    if not text:
                        return "Empty response from LLM"
                    
                    # Clean the text
                    cleaned_text = text.strip()
                    cleaned_text = re.sub(r'^```json\s*|\s*```$', '', cleaned_text, flags=re.MULTILINE)
                    logger.info("\nCleaned text: %s", repr(cleaned_text))
                    
                    # Parse the response
                    tool_name, arguments = self._parse_tool_call(cleaned_text)
                    
                    if not tool_name:
                        return "Failed to parse response from LLM"
                    
                    if tool_name == "FINAL_ANSWER":
                        return arguments  # arguments contains the final response in this case
                    
                    try:
                        # Find the matching tool
                        tool = next((t for t in self.tools if t.name == tool_name), None)
                        if not tool:
                            return f"Unknown tool: {tool_name}"
                            
                        result = await asyncio.wait_for(
                            self.session.call_tool(name=tool_name, arguments=arguments),
                            timeout=5.0
                        )
                        
                        # Format the result
                        if hasattr(result, 'content'):
                            if isinstance(result.content, list):
                                result_str = [
                                    item.text if hasattr(item, 'text') else str(item)
                                    for item in result.content
                                ]
                                result_str = f"[{', '.join(result_str)}]"
                            else:
                                result_str = str(result.content)
                        else:
                            result_str = str(result)
                        
                        # Record the action
                        self.iteration_response.append(
                            f"Called {tool_name} with {arguments}, got: {result_str}"
                        )
                    except Exception as e:
                        logger.error(f"Error calling tool: %s", e)
                        self.iteration_response.append(f"Error calling {tool_name}: {e}")
                        return f"Error executing tool {tool_name}: {e}"
                except Exception as e:
                    logger.error(f"Error in process_request: %s", e)
                    return f"Error processing request: {e}"
                
                self.iteration += 1
            except Exception as e:
                return f"Error processing request: {str(e)}"

        return "Max iterations reached without finding a solution."

async def main():
    # Initialize the agent
    agent = GeminiMCPAgent()
    logger.info("\n=== Gemini MCP Agent Chat Interface ===")
    logger.info("Type 'exit' or 'quit' to end the session")
    logger.info("Type 'help' to see available commands")
    
    # Set up server parameters
    server_params = StdioServerParameters(
        command=".venv/bin/python",
        args=["pinta_mcp_server.py"]
    )
    
    try:
        # Initialize agent and get tools
        logger.info("\nInitializing agent and connecting to MCP server...")
        tools = await agent.initialize(server_params)
        logger.info("✓ Connected successfully!")
        logger.info(f"\nAvailable tools: {len(tools)} tools loaded")
        
        # Main chat loop
        while True:
            try:
                # Get user input
                logger.info("\n> ")
                user_input = await asyncio.get_event_loop().run_in_executor(None, input)
                
                # Check for exit commands
                if user_input.lower() in ['exit', 'quit']:
                    logger.info("Goodbye!")
                    break
                
                # Handle help command
                if user_input.lower() == 'help':
                    logger.info("\nAvailable commands:")
                    logger.info("  help  - Show this help message")
                    logger.info("  tools - List available tools")
                    logger.info("  exit  - Exit the chat")
                    logger.info("  quit  - Exit the chat")
                    logger.info("\nYou can also type any natural language request to use the tools.")
                    continue
                
                # Handle tools command
                if user_input.lower() == 'tools':
                    logger.info("\nAvailable tools:")
                    for tool in tools:
                        logger.info(f"  - {tool}")
                    continue
                
                # Process the request
                if user_input.strip():
                    logger.info("\nProcessing request...")
                    response = await agent.process_request(user_input)
                    logger.info(f"\nResponse: {response}")
            
            except KeyboardInterrupt:
                logger.info("\nUse 'exit' or 'quit' to end the session")
                continue
            except Exception as e:
                logger.error(f"\nError: {str(e)}")
                continue
    
    except Exception as e:
        logger.error(f"\nFatal error: {str(e)}")
    finally:
        await agent.cleanup()
        logger.info("\nClosing session...")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nSession terminated by user")
    except Exception as e:
        logger.error(f"\nFatal error: {str(e)}")
