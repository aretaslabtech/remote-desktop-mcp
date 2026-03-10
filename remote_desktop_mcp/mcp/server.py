import structlog
from fastmcp import FastMCP

from ..protocol.base import GUISession
from ..protocol.base import Key
from ..protocol.base import MouseButton
from .debug import ActionType
from .debug import get_debug_logger
from .recorder import ScreenRecorder

logger = structlog.get_logger()

mcp = FastMCP('Remote Desktop MCP')

# Global session instance
_session: GUISession | None = None

# Global recorder instance (None when not recording)
_recorder: ScreenRecorder | None = None


def set_session(session: GUISession) -> None:
    """Set the active session and automatically start silent screen recording."""
    global _session, _recorder
    _session = session
    _session.start()

    # Auto-start recording; output alongside the debug session directory.
    debug = get_debug_logger(session.protocol)
    output_path = str(debug.session_dir / 'recording.mp4')
    _recorder = ScreenRecorder()
    try:
        _recorder.start(session, output_path=output_path, fps=5)
        logger.info('auto_recording_started', output=output_path)
    except Exception as exc:
        logger.warning('auto_recording_start_failed', error=str(exc))
        _recorder = None


def teardown() -> None:
    """Stop the active recording and save the video.  Call before session.stop()."""
    global _recorder
    if _recorder is not None and _recorder.is_running:
        try:
            path = _recorder.stop()
            logger.info('auto_recording_saved', path=str(path))
        except Exception as exc:
            logger.warning('auto_recording_stop_failed', error=str(exc))
        _recorder = None


def _notify(action_type: str, params: dict) -> None:
    """Forward an action notification to the active recorder (if any)."""
    if _recorder is not None and _recorder.is_running:
        _recorder.notify_action(action_type, params)


@mcp.tool()
def take_screenshot(output_path: str = 'screenshot.png') -> str:
    """Capture a screenshot of the remote desktop."""
    if not _session:
        return 'Error: No session active.'

    # Debug logging
    debug = get_debug_logger(_session.protocol)
    step_dir = debug.log_step(
        ActionType.SCREENSHOT, {
            'output_path': output_path,
        }, _session,
    )

    _session.take_screenshot(output_path)

    _notify('screenshot', {'output_path': output_path})
    debug.log_after(step_dir, _session)
    return f"Screenshot saved to {output_path} (Debug: {step_dir})"


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
    debug = get_debug_logger(_session.protocol)
    step_dir = debug.log_step(
        ActionType.CLICK, {'x': x, 'y': y, 'button': button}, _session,
    )

    _session.click(x, y, btn)

    _notify('click', {'x': x, 'y': y, 'button': button})
    debug.log_after(step_dir, _session)
    return f"Clicked {button} at ({x}, {y}) (Debug: {step_dir})"


@mcp.tool()
def mouse_move(x: int, y: int) -> str:
    """Move the mouse cursor to (x, y)."""
    if not _session:
        return 'Error: No session active.'

    # Debug logging
    debug = get_debug_logger(_session.protocol)
    step_dir = debug.log_step(ActionType.MOVE, {'x': x, 'y': y}, _session)

    _session.move(x, y)

    _notify('move', {'x': x, 'y': y})
    debug.log_after(step_dir, _session)
    return f"Moved mouse to ({x}, {y}) (Debug: {step_dir})"


@mcp.tool()
def mouse_scroll(clicks: int) -> str:
    """Scroll the mouse wheel. Positive for up, negative for down."""
    if not _session:
        return 'Error: No session active.'

    # Debug logging
    debug = get_debug_logger(_session.protocol)
    step_dir = debug.log_step(ActionType.SCROLL, {'clicks': clicks}, _session)

    _session.scroll(clicks)

    _notify('scroll', {'clicks': clicks})
    debug.log_after(step_dir, _session)
    return f"Scrolled {clicks} clicks (Debug: {step_dir})"


@mcp.tool()
def type_text(text: str) -> str:
    """Type the specified text."""
    if not _session:
        return 'Error: No session active.'

    # Debug logging
    debug = get_debug_logger(_session.protocol)
    step_dir = debug.log_step(ActionType.TYPE, {'text': text}, _session)

    _session.type_text(text)

    _notify('type', {'text': text})
    debug.log_after(step_dir, _session)
    return f"Typed: {text} (Debug: {step_dir})"


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
    debug = get_debug_logger(_session.protocol)
    step_dir = debug.log_step(ActionType.KEY, {'key': key_name}, _session)

    _session.key_event(key)

    _notify('key', {'key': key_name})
    debug.log_after(step_dir, _session)
    return f"Pressed key: {key_name} (Debug: {step_dir})"


@mcp.tool()
def start_recording(output_path: str = 'recording.mp4', fps: int = 5) -> str:
    """Start a continuous screen recording of the remote desktop session.

    Captures the live screen at the given frame-rate and overlays transient
    visual annotations for every action:
    - **Left click**: red shrinking ripple circle + crosshair.
    - **Right click**: blue shrinking ripple circle + crosshair.
    - **Mouse move**: yellow crosshair at the destination.
    - **Type / key-press**: semi-transparent bottom banner with the text.

    Call :func:`stop_recording` to finish and save the video.

    Args:
        output_path: Destination file for the MP4 video.
            Falls back to an animated GIF if ffmpeg is unavailable.
        fps: Capture frame-rate (default 5).  Higher values give smoother
            video at the cost of more CPU / disk I/O.

    Returns:
        Confirmation message.
    """
    global _recorder
    if not _session:
        return 'Error: No session active.'

    # Stop any existing recording (auto or previous manual) before starting a new one.
    if _recorder is not None and _recorder.is_running:
        try:
            saved = _recorder.stop()
            logger.info('previous_recording_saved', path=str(saved))
        except Exception as exc:
            logger.warning('previous_recording_stop_failed', error=str(exc))
        _recorder = None

    _recorder = ScreenRecorder()
    try:
        _recorder.start(_session, output_path=output_path, fps=fps)
        return f"Recording started → {output_path}  (fps={fps})"
    except Exception as exc:
        _recorder = None
        return f"Error starting recording: {exc}"


@mcp.tool()
def stop_recording() -> str:
    """Stop the active screen recording and save the video file.

    Returns:
        Path to the saved video file.
    """
    global _recorder
    if _recorder is None or not _recorder.is_running:
        return 'Error: No recording is currently active.'

    try:
        path = _recorder.stop()
        _recorder = None
        return f"Recording saved to: {path}"
    except Exception as exc:
        _recorder = None
        return f"Error stopping recording: {exc}"
