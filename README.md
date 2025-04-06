# Pinta MCP Server

A powerful server implementation that enhances Pinta with advanced drawing capabilities through keyboard shortcuts and automated controls.

## Features

- **Rectangle Drawing**: Create rectangles with precision using the keyboard
  - Press `R` to activate rectangle tool
  - Hold `Shift` for perfect squares
  - Press `Enter` to confirm

- **Text Insertion**: Add formatted text with ease
  - Press `T` to activate text tool
  - `Ctrl+B` for bold text
  - `Ctrl+I` for italic text

- **Line Width Control**: Adjust stroke thickness
  - `Ctrl+]` to increase width
  - `Ctrl+[` to decrease width

- **Drawing Management**:
  - `Ctrl+S` to save drawings
  - `Ctrl+Z` to undo changes
  - `Ctrl+Y` to redo changes

## Getting Started

1. Ensure you have Python installed
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the server:
   ```bash
   python pinta_mcp_server.py
   ```

## Project Structure

- `pinta_mcp_server.py`: Main server implementation
- `gemini_mcp_agent.py`: Gemini integration for enhanced capabilities

## License

MIT License - Feel free to use and modify as needed.

## Last Updated

April 6, 2025