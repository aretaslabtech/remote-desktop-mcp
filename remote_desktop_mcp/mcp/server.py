from fastmcp import FastMCP

from ..protocol.base import GUISession
from ..protocol.base import Key
from ..protocol.base import MouseButton

mcp = FastMCP('Remote Desktop MCP')

# Global session instance
_session: GUISession | None = None


def set_session(session: GUISession) -> None:
    global _session
    _session = session
    _session.start()


@mcp.tool()
def take_screenshot(output_path: str = 'screenshot.png') -> str:
    """Capture a screenshot of the remote desktop."""
    if not _session:
        return 'Error: No session active.'
    _session.take_screenshot(output_path)
    return f"Screenshot saved to {output_path}"


@mcp.tool()
def mouse_click(x: int, y: int, button: str = 'left') -> str:
    """Click at the specified coordinates (x, y)."""
    if not _session:
        return 'Error: No session active.'
    try:
        btn = MouseButton(button.lower())
    except ValueError:
        return f"Error: Invalid button '{button}'. Use 'left', 'middle', or 'right'."
    _session.click(x, y, btn)
    return f"Clicked {button} at ({x}, {y})"


@mcp.tool()
def mouse_move(x: int, y: int) -> str:
    """Move the mouse cursor to (x, y)."""
    if not _session:
        return 'Error: No session active.'
    _session.move(x, y)
    return f"Moved mouse to ({x}, {y})"


@mcp.tool()
def mouse_scroll(clicks: int) -> str:
    """Scroll the mouse wheel. Positive for up, negative for down."""
    if not _session:
        return 'Error: No session active.'
    _session.scroll(clicks)
    return f"Scrolled {clicks} clicks"


@mcp.tool()
def type_text(text: str) -> str:
    """Type the specified text."""
    if not _session:
        return 'Error: No session active.'
    _session.type_text(text)
    return f"Typed: {text}"


@mcp.tool()
def press_key(key_name: str) -> str:
    """Press a special key (e.g., enter, backspace, tab, space, esc, up, down, left, right)."""
    if not _session:
        return 'Error: No session active.'
    try:
        key = Key(key_name.lower())
    except ValueError:
        valid_keys = ', '.join([k.value for k in Key])
        return f"Error: Invalid key '{key_name}'. Valid keys: {valid_keys}"
    _session.key_event(key)
    return f"Pressed key: {key_name}"
