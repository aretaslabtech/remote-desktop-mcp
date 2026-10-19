import atexit
import base64
import signal
from pathlib import Path
from typing import cast

import structlog
from fastmcp import FastMCP
from mcp.types import ImageContent
from mcp.types import TextContent

from ..protocol.base import DesktopSession
from ..protocol.base import GUISession
from ..protocol.base import Key
from ..protocol.base import MobileSession
from ..protocol.base import MouseButton
from ..protocol.rdp import ClipboardError
from ..protocol.rdp import RDPSession
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
        output_path = str(debug.recordings_dir / 'recording.mp4')
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
    session_dir = None
    if _recorder is not None and _recorder.is_running:
        try:
            # We assume output_dir is within the session_dir
            out_dir = _recorder.stop()
            session_dir = out_dir.parent
            logger.info('auto_recording_saved', path=str(out_dir))
        except Exception as exc:
            logger.warning('auto_recording_stop_failed', error=str(exc))
        _recorder = None

    trace_path = None
    if _tracer is not None:
        try:
            trace_path = _tracer.path
            _tracer.close()
            logger.info('trace_closed', path=str(trace_path))
        except Exception as exc:
            logger.warning('trace_close_failed', error=str(exc))
        _tracer = None

    # Automatically generate annotated video if we have both recording and trace
    if session_dir and trace_path:
        try:
            from .annotate import run_annotate
            video_dir = session_dir / 'recordings'
            output_path = session_dir / 'annotated.mp4'
            logger.info('auto_annotation_started', session=session_dir.name)
            run_annotate(
                video_path=video_dir,
                trace_path=trace_path,
                output_path=output_path,
            )
            logger.info('auto_annotation_finished', output=str(output_path))
        except ImportError:
            logger.warning(
                'auto_annotation_skipped',
                reason='imageio/numpy not installed',
            )
        except Exception as exc:
            logger.warning('auto_annotation_failed', error=str(exc))


def _notify(action_type: str, params: dict) -> None:
    """Write an action to the trace file (if the tracer is active)."""
    if _tracer is not None:
        _tracer.log_action(action_type, params)


def _denormalize_coords(x: int, y: int) -> tuple[int, int]:
    """Convert normalized (0-1000) coordinates to actual screen pixels."""
    if not _session:
        return x, y
    width, height = _session.get_screen_size()
    if width == 0 or height == 0:
        return x, y
    return round(x * width / 1000), round(y * height / 1000)


# =========================================================================== #
# Common tools — available on both desktop and mobile sessions
# =========================================================================== #

@mcp.tool()
def take_screenshot(output_path: str = 'screenshot.png') -> list[TextContent | ImageContent]:
    """Capture a screenshot of the remote desktop or mobile screen."""
    if not _session:
        return [TextContent(type='text', text='Error: No session active.')]

    debug = get_debug_logger(_session.protocol)
    step_dir = debug.log_step(
        ActionType.SCREENSHOT, {
            'output_path': output_path,
        }, _session,
    )

    _session.take_screenshot(output_path)

    _notify('screenshot', {'output_path': output_path})
    debug.log_after(step_dir, _session)

    image_data = base64.standard_b64encode(
        Path(output_path).read_bytes(),
    ).decode()
    return [
        TextContent(
            type='text', text=f"Screenshot saved to {output_path} (Debug: {step_dir})",
        ),
        ImageContent(type='image', data=image_data, mimeType='image/png'),
    ]


@mcp.tool()
def tap(x: int, y: int) -> str:
    """Tap at the specified coordinates (x, y).

    Coordinates are normalized (0-1000). (0,0) is top-left, (1000,1000) is bottom-right.
    On desktop sessions this is equivalent to a left-click.
    On mobile sessions this is a touch tap.
    """
    if not _session:
        return 'Error: No session active.'

    nx, ny = _denormalize_coords(x, y)
    debug = get_debug_logger(_session.protocol)
    step_dir = debug.log_step(
        ActionType.TAP, {
            'x': x, 'y': y,
            'actual_x': nx, 'actual_y': ny,
        }, _session,
    )

    _session.tap(nx, ny)

    _notify('tap', {'x': x, 'y': y, 'actual_x': nx, 'actual_y': ny})
    debug.log_after(step_dir, _session)
    return f"Tapped at ({x}, {y}) [scaled to ({nx}, {ny})] (Debug: {step_dir})"


@mcp.tool()
def type_text(text: str) -> str:
    """Type the specified text."""
    if not _session:
        return 'Error: No session active.'

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

    For key combinations (e.g. cmd+space, ctrl+c) use press_hotkey instead
    (desktop only).
    """
    if not _session:
        return 'Error: No session active.'
    try:
        key = Key(key_name.lower())
    except ValueError:
        valid_keys = ', '.join([k.value for k in Key])
        return f"Error: Invalid key '{key_name}'. Valid keys: {valid_keys}"

    debug = get_debug_logger(_session.protocol)
    step_dir = debug.log_step(ActionType.KEY, {'key': key_name}, _session)

    _session.key_event(key)

    _notify('key', {'key': key_name})
    debug.log_after(step_dir, _session)
    return f"Pressed key: {key_name} (Debug: {step_dir})"


# =========================================================================== #
# Desktop-only tools — mouse_click, mouse_move, mouse_scroll, press_hotkey
# =========================================================================== #

@mcp.tool()
def mouse_click(x: int, y: int, button: str = 'left') -> str:
    """Click at (x, y) with a specific mouse button.

    Coordinates are normalized (0-1000). (0,0) is top-left, (1000,1000) is bottom-right.
    Desktop only.  Use ``tap`` for a simple left-click or for mobile sessions.
    Supported buttons: left, middle, right.
    """
    if not _session:
        return 'Error: No session active.'
    if not isinstance(_session, DesktopSession):
        return 'Error: mouse_click is only available for desktop sessions. Use tap instead.'
    try:
        btn = MouseButton(button.lower())
    except ValueError:
        return f"Error: Invalid button '{button}'. Use 'left', 'middle', or 'right'."

    nx, ny = _denormalize_coords(x, y)
    debug = get_debug_logger(_session.protocol)
    step_dir = debug.log_step(
        ActionType.CLICK, {
            'x': x, 'y': y, 'button': button,
            'actual_x': nx, 'actual_y': ny,
        }, _session,
    )

    _session.click(nx, ny, btn)

    _notify(
        'click', {
            'x': x, 'y': y, 'button': button,
            'actual_x': nx, 'actual_y': ny,
        },
    )
    debug.log_after(step_dir, _session)
    return f"Clicked {button} at ({x}, {y}) [scaled to ({nx}, {ny})] (Debug: {step_dir})"


@mcp.tool()
def mouse_move(x: int, y: int) -> str:
    """Move the mouse cursor to (x, y).

    Coordinates are normalized (0-1000). (0,0) is top-left, (1000,1000) is bottom-right.
    Desktop only.
    """
    if not _session:
        return 'Error: No session active.'
    if not isinstance(_session, DesktopSession):
        return 'Error: mouse_move is only available for desktop sessions.'

    nx, ny = _denormalize_coords(x, y)
    debug = get_debug_logger(_session.protocol)
    step_dir = debug.log_step(
        ActionType.MOVE, {
            'x': x, 'y': y,
            'actual_x': nx, 'actual_y': ny,
        }, _session,
    )

    _session.move(nx, ny)

    _notify('move', {'x': x, 'y': y, 'actual_x': nx, 'actual_y': ny})
    debug.log_after(step_dir, _session)
    return f"Moved mouse to ({x}, {y}) [scaled to ({nx}, {ny})] (Debug: {step_dir})"


@mcp.tool()
def mouse_scroll(clicks: int) -> str:
    """Scroll the mouse wheel. Positive for up, negative for down.  Desktop only.

    For mobile sessions use ``swipe`` instead.
    """
    if not _session:
        return 'Error: No session active.'
    if not isinstance(_session, DesktopSession):
        return 'Error: mouse_scroll is only available for desktop sessions. Use swipe instead.'

    debug = get_debug_logger(_session.protocol)
    step_dir = debug.log_step(ActionType.SCROLL, {'clicks': clicks}, _session)

    _session.scroll(clicks)

    _notify('scroll', {'clicks': clicks})
    debug.log_after(step_dir, _session)
    return f"Scrolled {clicks} clicks (Debug: {step_dir})"


@mcp.tool()
def press_hotkey(keys: str) -> str:
    """Press a key combination simultaneously, e.g. 'ctrl+c', 'cmd+space', 'ctrl+shift+t'.

    Desktop only.  Separate keys with '+'.
    """
    if not _session:
        return 'Error: No session active.'
    if not isinstance(_session, DesktopSession):
        return 'Error: press_hotkey is only available for desktop sessions.'
    key_list = [k.strip() for k in keys.split('+') if k.strip()]
    if not key_list:
        return 'Error: No keys provided.'

    debug = get_debug_logger(_session.protocol)
    step_dir = debug.log_step(ActionType.HOTKEY, {'keys': keys}, _session)

    _session.hotkey(*key_list)

    _notify('hotkey', {'keys': keys})
    debug.log_after(step_dir, _session)
    return f"Pressed hotkey: {keys} (Debug: {step_dir})"


# =========================================================================== #
# Clipboard / shared-drive tools — desktop sessions that support clipboard
# access (currently RDP only; gated via DesktopSession.supports_clipboard)
# =========================================================================== #

@mcp.tool()
def clipboard_read() -> str:
    """Read text from the clipboard of the active remote desktop session."""
    if not _session:
        return 'Error: No session active.'
    if not isinstance(_session, DesktopSession) or not _session.supports_clipboard:
        return 'Error: Clipboard is not supported by the active session.'
    session = cast(RDPSession, _session)

    try:
        text = session.read_clipboard()
    except ClipboardError as exc:
        return f"Error: {exc}"

    _notify('clipboard_read', {'length': len(text)})
    return text


@mcp.tool()
def clipboard_write(text: str) -> str:
    """Write text to the clipboard of the active remote desktop session."""
    if not _session:
        return 'Error: No session active.'
    if not isinstance(_session, DesktopSession) or not _session.supports_clipboard:
        return 'Error: Clipboard is not supported by the active session.'
    session = cast(RDPSession, _session)

    try:
        session.write_clipboard(text)
    except ClipboardError as exc:
        return f"Error: {exc}"

    _notify('clipboard_write', {'length': len(text)})
    return 'Clipboard updated.'


@mcp.tool()
def shared_drive_info() -> dict:
    """Report the active RDP session's shared-drive configuration."""
    if not isinstance(_session, DesktopSession):
        return {'enabled': False}

    shared_dir = getattr(_session, 'shared_dir', None)
    if not shared_dir:
        return {'enabled': False}

    shared_name = getattr(_session, 'shared_name', 'shared')
    info = {
        'enabled': True,
        'name': shared_name,
        'local_path': shared_dir,
        'windows_path': f"\\\\tsclient\\{shared_name}",
    }
    _notify('shared_drive_info', info)
    return info


# =========================================================================== #
# Mobile-only tools — swipe, long_press
# =========================================================================== #

@mcp.tool()
def swipe(
    x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300,
) -> str:
    """Swipe from (x1, y1) to (x2, y2) over *duration_ms* milliseconds.

    Coordinates are normalized (0-1000). (0,0) is top-left, (1000,1000) is bottom-right.
    Mobile only.  For desktop sessions use ``mouse_scroll`` instead.
    """
    if not _session:
        return 'Error: No session active.'
    if not isinstance(_session, MobileSession):
        return 'Error: swipe is only available for mobile sessions. Use mouse_scroll instead.'

    nx1, ny1 = _denormalize_coords(x1, y1)
    nx2, ny2 = _denormalize_coords(x2, y2)
    debug = get_debug_logger(_session.protocol)
    step_dir = debug.log_step(
        ActionType.SWIPE,
        {
            'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
            'duration_ms': duration_ms,
            'actual_x1': nx1, 'actual_y1': ny1,
            'actual_x2': nx2, 'actual_y2': ny2,
        },
        _session,
    )

    _session.swipe(nx1, ny1, nx2, ny2, duration_ms)

    _notify(
        'swipe', {
            'x1': x1, 'y1': y1, 'x2': x2,
            'y2': y2, 'duration_ms': duration_ms,
            'actual_x1': nx1, 'actual_y1': ny1,
            'actual_x2': nx2, 'actual_y2': ny2,
        },
    )
    debug.log_after(step_dir, _session)
    return f"Swiped ({x1},{y1}) -> ({x2},{y2}) [scaled to ({nx1},{ny1}) -> ({nx2},{ny2})] in {duration_ms}ms (Debug: {step_dir})"


@mcp.tool()
def long_press(x: int, y: int, duration_ms: int = 500) -> str:
    """Long-press at (x, y) for *duration_ms* milliseconds.

    Coordinates are normalized (0-1000). (0,0) is top-left, (1000,1000) is bottom-right.
    Mobile only.
    """
    if not _session:
        return 'Error: No session active.'
    if not isinstance(_session, MobileSession):
        return 'Error: long_press is only available for mobile sessions.'

    nx, ny = _denormalize_coords(x, y)
    debug = get_debug_logger(_session.protocol)
    step_dir = debug.log_step(
        ActionType.LONG_PRESS,
        {'x': x, 'y': y, 'duration_ms': duration_ms, 'actual_x': nx, 'actual_y': ny},
        _session,
    )

    _session.long_press(nx, ny, duration_ms)

    _notify(
        'long_press', {
            'x': x, 'y': y, 'duration_ms': duration_ms, 'actual_x': nx, 'actual_y': ny,
        },
    )
    debug.log_after(step_dir, _session)
    return f"Long-pressed at ({x}, {y}) [scaled to ({nx}, {ny})] for {duration_ms}ms (Debug: {step_dir})"


# =========================================================================== #
# Recording tools
# =========================================================================== #

@mcp.tool()
def start_recording(output_path: str = 'recording.mp4', fps: int = 5, segment_seconds: int = 60) -> str:
    """Start a continuous screen recording of the remote desktop session.

    Recording is split into segment files (e.g. recording_0000.mp4,
    recording_0001.mp4, ...) so that data is written to disk incrementally
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
            f"Recording started -> {Path(output_path).parent}/  "
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
