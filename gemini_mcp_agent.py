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
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None, 
                lambda: client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt
                )
            ),
            timeout=timeout
        )
        return response
    except TimeoutError:
        print("LLM generation timed out!")
        raise
    except Exception as e:
        print(f"Error in LLM generation: {e}")
        raise

class GeminiMCPAgent:
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
        """Parse tool name and arguments from response text."""
        # Look for tool calls in the format: TOOL: name(arg1=value1, arg2=value2)
        match = re.search(r'TOOL:\s*(\w+)\s*\((.*?)\)', text)
        if not match:
            print("Unable to parse tool call from response text.")
            return None, None

        tool_name = match.group(1)
        args_str = match.group(2)

        # Parse arguments
        arguments = {}
        if args_str:
            for arg in args_str.split(','):
                if '=' in arg:
                    key, value = arg.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    # Handle boolean values
                    if value.lower() == 'true':
                        value = True
                    elif value.lower() == 'false':
                        value = False
                    # Handle numeric values
                    elif value.isdigit():
                        value = int(value)
                    elif value.replace('.', '').isdigit() and value.count('.') == 1:
                        value = float(value)
                    arguments[key] = value

        return tool_name, arguments

    async def process_request(self, user_request: str) -> str:
        """Process a user request using Gemini and MCP tools."""
        if not self.session:
            raise ValueError("Agent not initialized. Call initialize() first.")

        self.iteration = 0
        self.iteration_response = []

        while self.iteration < self.max_iterations:
            try:
                print(f"\n--- Iteration {self.iteration + 1} ---")
                if self.iteration_response is None:
                    current_query = user_request
                else:
                    current_query = user_request + "\n\n" + " ".join(self.iteration_response)
                    current_query = current_query + "  What should I do next?"
                # Create prompt with context
                print("Created system prompt...")
                

                
                context = "\n".join([
                    "You are a ai agent solving problems in iteration with access to these tools:",
                    *[f"- {desc}" for desc in self.tools_description],
                    "\nTo use a tool, respond with: TOOL:name(param1=value1, param2=value2)",
                    "For final answers, start with: FINAL_ANSWER:",
                    """ Important:
- When a function returns multiple values, you need to process all of them
- Only give FINAL_ANSWER when you have completed all necessary calculations
- Do not repeat function calls with the same parameters""",
                    f"\nPrevious actions: {'; '.join(self.iteration_response)}",
                    f"\nUser Request: {current_query}"
                ])

                print("current query prompt:\n", current_query)

                # Generate response using Gemini
                response = await generate_with_timeout(client, context)
                response_text = response.text.strip()

                print("response:\n", response_text)

                # Check if it's a final answer
                final_answer_match = re.search(r'FINAL_ANSWER:\s*(.*?)(?:\n|$)', response_text)
                if final_answer_match:
                    return final_answer_match.group(1).strip()

                # Parse and execute tool call
                tool_name, arguments = self._parse_tool_call(response_text)
                if tool_name:
                    try:
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
                        print("Error calling tool:  ", str(e))
                        self.iteration_response.append(f"Error calling {tool_name}: {str(e)}")
                        return f"Error executing tool {tool_name}: {str(e)}"
                else:
                    return "I couldn't understand how to handle that request. Please try again."

                self.iteration += 1
            except Exception as e:
                return f"Error processing request: {str(e)}"

        return "Max iterations reached without finding a solution."

async def main():
    # Initialize the agent
    agent = GeminiMCPAgent()
    print("\n=== Gemini MCP Agent Chat Interface ===")
    print("Type 'exit' or 'quit' to end the session")
    print("Type 'help' to see available commands")
    
    # Set up server parameters
    server_params = StdioServerParameters(
        command=".venv/bin/python",
        args=["pinta_mcp_server.py"]
    )
    
    try:
        # Initialize agent and get tools
        print("\nInitializing agent and connecting to MCP server...")
        tools = await agent.initialize(server_params)
        print("✓ Connected successfully!")
        print(f"\nAvailable tools: {len(tools)} tools loaded")
        
        # Main chat loop
        while True:
            try:
                # Get user input
                print("\n> ", end='', flush=True)
                user_input = await asyncio.get_event_loop().run_in_executor(None, input)
                
                # Check for exit commands
                if user_input.lower() in ['exit', 'quit']:
                    print("Goodbye!")
                    break
                
                # Handle help command
                if user_input.lower() == 'help':
                    print("\nAvailable commands:")
                    print("  help  - Show this help message")
                    print("  tools - List available tools")
                    print("  exit  - Exit the chat")
                    print("  quit  - Exit the chat")
                    print("\nYou can also type any natural language request to use the tools.")
                    continue
                
                # Handle tools command
                if user_input.lower() == 'tools':
                    print("\nAvailable tools:")
                    for tool in tools:
                        print(f"  - {tool}")
                    continue
                
                # Process the request
                if user_input.strip():
                    print("\nProcessing request...")
                    response = await agent.process_request(user_input)
                    print(f"\nResponse: {response}")
            
            except KeyboardInterrupt:
                print("\nUse 'exit' or 'quit' to end the session")
                continue
            except Exception as e:
                print(f"\nError: {str(e)}")
                continue
    
    except Exception as e:
        print(f"\nFatal error: {str(e)}")
    finally:
        await agent.cleanup()
        print("\nClosing session...")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSession terminated by user")
    except Exception as e:
        print(f"\nFatal error: {str(e)}")
