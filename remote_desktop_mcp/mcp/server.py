from fastmcp import FastMCP

from ..protocol.base import GUISession
from ..protocol.base import Key
from ..protocol.base import MouseButton
from .debug import ActionType
from .debug import get_debug_logger

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

    # Debug logging
    debug = get_debug_logger()
    step_dir = debug.log_step(
        ActionType.SCREENSHOT, {
            'output_path': output_path,
        }, _session,
    )

    _session.take_screenshot(output_path)

    debug.log_after(step_dir, _session)
    return f"Screenshot saved to {output_path} (Debug info in {step_dir})"


@mcp.tool()
def mouse_click(x: int, y: int, button: str = 'left') -> str:
    """Click at the specified coordinates (x, y)."""
    if not _session:
        return 'Error: No session active.'
    try:
        btn = MouseButton(button.lower())
    except ValueError:
        return f"Error: Invalid button '{button}'. Use 'left', 'middle', or 'right'."

    # Debug logging
    debug = get_debug_logger()
    step_dir = debug.log_step(
        ActionType.CLICK, {'x': x, 'y': y, 'button': button}, _session,
    )

    _session.click(x, y, btn)

    debug.log_after(step_dir, _session)
    return f"Clicked {button} at ({x}, {y}) (Debug info in {step_dir})"


@mcp.tool()
def mouse_move(x: int, y: int) -> str:
    """Move the mouse cursor to (x, y)."""
    if not _session:
        return 'Error: No session active.'

    # Debug logging
    debug = get_debug_logger()
    step_dir = debug.log_step(ActionType.MOVE, {'x': x, 'y': y}, _session)

    _session.move(x, y)

    debug.log_after(step_dir, _session)
    return f"Moved mouse to ({x}, {y}) (Debug info in {step_dir})"


@mcp.tool()
def mouse_scroll(clicks: int) -> str:
    """Scroll the mouse wheel. Positive for up, negative for down."""
    if not _session:
        return 'Error: No session active.'

    # Debug logging
    debug = get_debug_logger()
    step_dir = debug.log_step(ActionType.SCROLL, {'clicks': clicks}, _session)

    _session.scroll(clicks)

    debug.log_after(step_dir, _session)
    return f"Scrolled {clicks} clicks (Debug info in {step_dir})"


@mcp.tool()
def type_text(text: str) -> str:
    """Type the specified text."""
    if not _session:
        return 'Error: No session active.'

    # Debug logging
    debug = get_debug_logger()
    step_dir = debug.log_step(ActionType.TYPE, {'text': text}, _session)

    _session.type_text(text)

    debug.log_after(step_dir, _session)
    return f"Typed: {text} (Debug info in {step_dir})"


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

    # Debug logging
    debug = get_debug_logger()
    step_dir = debug.log_step(ActionType.KEY, {'key': key_name}, _session)

    _session.key_event(key)

    debug.log_after(step_dir, _session)
    return f"Pressed key: {key_name} (Debug info in {step_dir})"
