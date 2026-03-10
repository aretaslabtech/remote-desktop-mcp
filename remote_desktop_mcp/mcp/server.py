import atexit
import signal
from pathlib import Path

import structlog
from fastmcp import FastMCP

from ..protocol.base import GUISession
from ..protocol.base import Key
from ..protocol.base import MouseButton
from .debug import ActionType
from .debug import get_debug_logger
from .recorder import ScreenRecorder
from .trace import TraceLogger

logger = structlog.get_logger()

mcp = FastMCP('Remote Desktop MCP')

# Global session instance
_session: GUISession | None = None

# Global recorder instance (None when not recording)
_recorder: ScreenRecorder | None = None

# Global trace logger (runs for the lifetime of the session)
_tracer: TraceLogger | None = None


def set_session(session: GUISession, record: bool = False) -> None:
    """Set the active session and open the trace file.

    Args:
        session: The GUI session backend to use.
        record: When True, also start a continuous raw screen recording.
            Disabled by default to avoid producing large files during long
            Claude Code sessions.  Pass ``--record`` on the CLI to enable.
    """
    global _session, _recorder, _tracer
    _session = session
    _session.start()

    debug = get_debug_logger(session.protocol)

    # Optionally start raw screen recording (annotation-free).
    if record:
        output_path = str(debug.session_dir / 'recording.mp4')
        _recorder = ScreenRecorder()
        try:
            _recorder.start(session, output_path=output_path, fps=5)
            logger.info('auto_recording_started', output=output_path)
        except Exception as exc:
            logger.warning('auto_recording_start_failed', error=str(exc))
            _recorder = None

    # Open JSONL trace file alongside the recording.
    trace_path = debug.session_dir / 'trace.jsonl'
    _tracer = TraceLogger(trace_path, fps=5)
    logger.info('trace_started', path=str(trace_path))

    # Ensure teardown runs even on abrupt exit or SIGTERM.
    atexit.register(teardown)
    signal.signal(signal.SIGTERM, lambda *_: teardown())


def teardown() -> None:
    """Stop recording, close the trace, and save both files.  Call before session.stop()."""
    global _recorder, _tracer
    if _recorder is not None and _recorder.is_running:
        try:
            path = _recorder.stop()
            logger.info('auto_recording_saved', path=str(path))
        except Exception as exc:
            logger.warning('auto_recording_stop_failed', error=str(exc))
        _recorder = None
    if _tracer is not None:
        try:
            _tracer.close()
            logger.info('trace_closed', path=str(_tracer.path))
        except Exception as exc:
            logger.warning('trace_close_failed', error=str(exc))
        _tracer = None


def _notify(action_type: str, params: dict) -> None:
    """Write an action to the trace file (if the tracer is active)."""
    if _tracer is not None:
        _tracer.log_action(action_type, params)


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
    """Press a single special key.

    Supported keys: enter, backspace, delete, tab, space, esc,
    up, down, left, right, home, end, pageup, pagedown, insert,
    f1-f12, shift, ctrl, alt, cmd (macOS Command), win, option,
    capslock, numlock, scrolllock, printscreen,
    volumeup, volumedown, volumemute.

    For key combinations (e.g. cmd+space, ctrl+c) use press_hotkey instead.
    """
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
def press_hotkey(keys: str) -> str:
    """Press a key combination simultaneously, e.g. 'ctrl+c', 'cmd+space', 'ctrl+shift+t'.

    Separate keys with '+'. Use the same key names as pyautogui (e.g. ctrl, alt,
    shift, cmd, win, enter, space, tab, esc, f1-f12, or any single character).
    """
    if not _session:
        return 'Error: No session active.'
    key_list = [k.strip() for k in keys.split('+') if k.strip()]
    if not key_list:
        return 'Error: No keys provided.'

    debug = get_debug_logger(_session.protocol)
    step_dir = debug.log_step(ActionType.KEY, {'key': keys}, _session)

    _session.hotkey(*key_list)

    _notify('hotkey', {'keys': keys})
    debug.log_after(step_dir, _session)
    return f"Pressed hotkey: {keys} (Debug: {step_dir})"


@mcp.tool()
def start_recording(output_path: str = 'recording.mp4', fps: int = 5, segment_seconds: int = 60) -> str:
    """Start a continuous screen recording of the remote desktop session.

    Recording is split into segment files (e.g. recording_0000.mp4,
    recording_0001.mp4, …) so that data is written to disk incrementally
    rather than held entirely in memory.

    Args:
        output_path: Template path for segment files.  The stem and directory
            are reused; actual files are named ``<stem>_NNNN.mp4``.
        fps: Capture frame-rate (default 5).
        segment_seconds: Duration of each segment file in seconds (default 60).

    Returns:
        Confirmation message.
    """
    global _recorder
    if not _session:
        return 'Error: No session active.'

    # Stop any existing recording before starting a new one.
    if _recorder is not None and _recorder.is_running:
        try:
            saved = _recorder.stop()
            logger.info('previous_recording_saved', path=str(saved))
        except Exception as exc:
            logger.warning('previous_recording_stop_failed', error=str(exc))
        _recorder = None

    _recorder = ScreenRecorder()
    try:
        _recorder.start(
            _session, output_path=output_path,
            fps=fps, segment_seconds=segment_seconds,
        )
        return (
            f"Recording started → {Path(output_path).parent}/  "
            f"(fps={fps}, segment={segment_seconds}s)\n"
            f"Trace: {_tracer.path if _tracer else 'n/a'}"
        )
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
        out_dir = _recorder.stop()
        _recorder = None
        return f"Recording saved to: {out_dir}"
    except Exception as exc:
        _recorder = None
        return f"Error stopping recording: {exc}"
