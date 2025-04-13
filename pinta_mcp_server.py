import os
import time

if 'DISPLAY' not in os.environ:
    os.environ['DISPLAY'] = ':0'
    
import pyautogui
from mcp.server.fastmcp import FastMCP
import platform

# Set default display if not set


# Configure PyAutoGUI settings
pyautogui.FAILSAFE = False  # Disable fail-safe
pyautogui.PAUSE = 0.5  # Add small delays between actions

server = FastMCP("MCP for Pinta")

@server.tool()
def click(x: int, y: int) -> bool:
    """Perform a mouse click at the given (x, y) coordinates. Returns true if success, else false."""
    try:
        pyautogui.click(x, y)
        return True
    except Exception as e:
        return False

@server.tool()
def type_text(text: str) -> bool:
    """Type the given text using the keyboard. Returns true if success, else false."""
    try:
        pyautogui.typewrite(text)
        return True
    except Exception as e:
        return False

@server.tool()
def move_to(x, y) -> bool:
    """Move the mouse to the given (x, y) coordinates. Returns true if success, else false."""
    try:
        pyautogui.moveTo(x, y, duration=2.0)
        return True
    except Exception as e:
        return False

@server.tool()
def right_click(x: int, y: int) -> bool:
    """Perform a right-click at the given (x, y) coordinates. Returns true if success, else false."""
    try:
        pyautogui.rightClick(x, y)
        return True
    except Exception as e:
        return False

@server.tool()
def press_key(key: str) -> bool:
    """Press and release a single key (e.g., 'enter', 'space', 'a'). Returns true if success, else false."""
    try:
        pyautogui.press(key)
        return True
    except Exception as e:
        return False

@server.tool()
def take_screenshot(filename: str) -> bool:
    """Take a screenshot and save it to the specified filename. Returns true if success, else false."""
    try:
        screenshot = pyautogui.screenshot()
        screenshot.save(filename)
        return True
    except Exception as e:
        return False

@server.tool()
def scroll(amount: int) -> bool:
    """Scroll the mouse up (positive amount) or down (negative amount). Returns true if success, else false."""
    try:
        pyautogui.scroll(amount)
        return True
    except Exception as e:
        return False

@server.tool()
def get_mouse_position() -> str:
    """Get the current (x, y) coordinates of the mouse. Returns (x, y). The string will have negative values if failed."""
    try:
        x, y = pyautogui.position()
        return str((x, y))
    except Exception as e:
        return str((-1, -1))

@server.tool()
def hotkey(keys: str) -> bool:
    """Press multiple keys together (e.g., 'ctrl+c'). Keys should be space-separated. Returns true if success, else false."""
    try:
        key_list = keys.split()
        pyautogui.hotkey(*key_list)
        return True
    except Exception as e:
        return False
    
@server.tool()
def double_click(x: int, y: int) -> bool:
    """Perform a double-click at the given (x, y) coordinates. Returns true if success, else false."""
    try:
        pyautogui.doubleClick(x, y)
        return True
    except Exception as e:
        return False

@server.tool()
def get_screen_size() -> str:
    """Get the screen resolution as (width, height). Returns a string in the format (width, height). On failure it returns (-1, -1)"""
    try:
        width, height = pyautogui.size()
        return str((width, height))
    except Exception as e:
        return str((-1, -1))
    
@server.tool()
def get_pixel_color(x: int, y: int) -> str:
    """Get the RGB color of the pixel at (x, y). Returns a string in the format (r, g, b). On failure it returns (-1, -1, -1)"""
    try:
        r, g, b = pyautogui.pixel(x, y)
        return str((r, g, b))
    except Exception as e:
        return str((-1, -1, -1))

@server.tool()
def get_os() -> str:
    """Get the name of the current operating system (e.g., 'Windows', 'macOS', 'Linux'). Returns OS name or 'Unknown' on failure."""
    try:
        os_name = platform.system()
        if os_name == "Windows":
            return "Windows"
        elif os_name == "Darwin":
            return "macOS"
        elif os_name == "Linux":
            return "Linux"
        else:
            return os_name
    except Exception as e:
        return "Unknown"       

@server.tool()
def open_pinta() -> bool:
    """Open the Pinta image editor. Returns true if success, else false."""
    try:
        os.system('pinta &')  # Run Pinta in the background

        time.sleep(2.5)
        pyautogui.hotkey('fn', 'alt', 'f10')
        time.sleep(0.5)

        return True
    except Exception as e:
        return False

# New Pinta-specific drawing tools

@server.tool()
def draw_rectangle(x1: int, y1: int, x2: int, y2: int, is_square: bool = False) -> bool:
    """Draw a rectangle in Pinta using keyboard shortcuts. 
    (x1,y1) is start point, (x2,y2) is end point. 
    Set is_square=True to force square shape."""
    try:
        # Select rectangle tool
        pyautogui.press('o')
        pyautogui.press('o')
        time.sleep(0.5)
    
        log_mouse_movement()
        # Move to start position
        pyautogui.moveTo(x1, y1)
        log_mouse_movement()
        pyautogui.mouseDown()
        
        # If square is requested, hold shift
        if is_square:
            pyautogui.keyDown('shift')
            
        # Draw to end position
        log_mouse_movement()
        pyautogui.moveTo(x2, y2)
        log_mouse_movement()
        pyautogui.mouseUp()
        
        if is_square:
            pyautogui.keyUp('shift')
        
        log_mouse_movement()
            
        return True
    except Exception as e:
        print(f"Error drawing rectangle: {e}")
        return False

@server.tool()
def add_text(x: int, y: int, text: str, bold: bool = False, italic: bool = False) -> bool:
    """Add text in Pinta at specified coordinates with optional formatting."""
    try:
        # Select text tool
        pyautogui.press('t')
        time.sleep(0.5)
        
        # Click where to add text
        pyautogui.click(x, y)
        time.sleep(0.5)
        
        # Apply formatting if requested
        if bold:
            pyautogui.hotkey('ctrl', 'b')
        if italic:
            pyautogui.hotkey('ctrl', 'i')
            
        # Type the text
        pyautogui.write(text)
        
        # Confirm text by pressing Enter
        pyautogui.press('enter')
        return True
    except Exception as e:
        print(f"Error adding text: {e}")
        return False

@server.tool()
def set_line_width(increase: bool = True) -> bool:
    """Increase or decrease the line width using keyboard shortcuts."""
    try:
        if increase:
            pyautogui.hotkey('ctrl', ']')
        else:
            pyautogui.hotkey('ctrl', '[')
        return True
    except Exception as e:
        print(f"Error changing line width: {e}")
        return False

@server.tool()
def save_drawing(filename: str) -> bool:
    """Save the current drawing to a file."""
    try:
        pyautogui.hotkey('ctrl', 's')
        time.sleep(0.5)
        pyautogui.write(filename)
        pyautogui.press('enter')
        return True
    except Exception as e:
        print(f"Error saving drawing: {e}")
        return False

@server.tool()
def log_mouse_movement() -> bool:
    """Log mouse coordinates for the specified duration in seconds."""
    x, y = pyautogui.position()
    current_time = time.strftime("%H:%M:%S")
    print(f"{current_time}\t{x}\t{y}")

def main():
    try:
        server.run(transport="stdio")
    except KeyboardInterrupt:
        print("Server stopped.")
    except Exception as e:
        print(f"An error occurred: {e}")        

if __name__ == "__main__":
    #use the above command
    # open_pinta()
    # time.sleep(2)
    
    # log_mouse_movement()
    
    # pyautogui.hotkey('alt', 'fn', 'f10')
    # time.sleep(0.5)
    # draw_rectangle(650, 650, 800, 800)
    # time.sleep(0.5)
    # add_text(700, 700, "MCP for Pinta")
    # time.sleep(0.5)
     
    main()