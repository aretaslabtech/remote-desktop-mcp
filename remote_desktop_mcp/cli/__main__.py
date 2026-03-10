from typing import Annotated
from typing import Any
from typing import cast

import structlog
import typer

from ..mcp.debug import ActionType
from ..mcp.debug import get_debug_logger
from ..mcp.recorder import ScreenRecorder
from ..mcp.trace import TraceLogger
from ..protocol.base import MouseButton
from ..protocol.local import LocalSession
from ..protocol.rdp import RDPSession
from ..protocol.vnc import VNCSession

logger = structlog.get_logger()

app = typer.Typer(
    help='Remote Desktop Debug CLI - Test desktop protocols and actions independently.',
    no_args_is_help=True,
)

# Local Debug
debug_local_app = typer.Typer(help='Debug local desktop.')
app.add_typer(debug_local_app, name='local')


@debug_local_app.command(name='screenshot')
def debug_local_screenshot(
    output: Annotated[
        str, typer.Option(
        help='Output path',
        ),
    ] = 'screenshot.png',
    display: Annotated[
        str | None,
        typer.Option(help='Display number', envvar='REMOTE_DESKTOP_DISPLAY'),
    ] = None,
):
    session = LocalSession(display_num=display)
    session.start()

    debug = get_debug_logger('local')
    recorder = ScreenRecorder()
    recorder.start(
        session, output_path=str(
            debug.session_dir / 'recording.mp4',
        ),
    )
    tracer = TraceLogger(debug.session_dir / 'trace.jsonl')

    step_dir = debug.log_step(
        ActionType.SCREENSHOT, {
            'output': output,
        }, session,
    )
    session.take_screenshot(output)
    tracer.log_action('screenshot', {'output_path': output})
    debug.log_after(step_dir, session)

    tracer.close()
    rec_path = recorder.stop()
    session.stop()
    print(f"Screenshot saved to {output} (Debug: {step_dir})")
    print(f"Recording: {rec_path}  Trace: {tracer.path}")


@debug_local_app.command(name='click')
def debug_local_click(
    x: int, y: int,
    button: MouseButton = MouseButton.LEFT,
    display: Annotated[
        str | None,
        typer.Option(help='Display number', envvar='REMOTE_DESKTOP_DISPLAY'),
    ] = None,
):
    session = LocalSession(display_num=display)
    session.start()

    debug = get_debug_logger('local')
    recorder = ScreenRecorder()
    recorder.start(
        session, output_path=str(
            debug.session_dir / 'recording.mp4',
        ),
    )
    tracer = TraceLogger(debug.session_dir / 'trace.jsonl')

    step_dir = debug.log_step(
        ActionType.CLICK, {'x': x, 'y': y, 'button': button.value}, session,
    )
    session.click(x, y, button)
    tracer.log_action('click', {'x': x, 'y': y, 'button': button.value})
    debug.log_after(step_dir, session)

    tracer.close()
    rec_path = recorder.stop()
    session.stop()
    print(f"Clicked {button.value} at ({x}, {y}) (Debug: {step_dir})")
    print(f"Recording: {rec_path}  Trace: {tracer.path}")


# VNC Debug
debug_vnc_app = typer.Typer(help='Debug VNC connection.')
app.add_typer(debug_vnc_app, name='vnc')


@debug_vnc_app.command(name='screenshot')
def debug_vnc_screenshot(
    host: Annotated[
        str,
        typer.Option(help='VNC host', envvar='REMOTE_DESKTOP_VNC_HOST'),
    ] = cast(Any, ...),
    password: Annotated[
        str | None,
        typer.Option(
            help='VNC password',
            envvar='REMOTE_DESKTOP_VNC_PASSWORD',
        ),
    ] = None,
    output: str = 'vnc_screenshot.png',
):
    session = VNCSession(host=host, password=password)
    session.start()

    debug = get_debug_logger('vnc')
    recorder = ScreenRecorder()
    recorder.start(
        session, output_path=str(
            debug.session_dir / 'recording.mp4',
        ),
    )
    tracer = TraceLogger(debug.session_dir / 'trace.jsonl')

    step_dir = debug.log_step(
        ActionType.SCREENSHOT, {
            'host': host, 'output': output,
        }, session,
    )
    session.take_screenshot(output)
    tracer.log_action('screenshot', {'output_path': output})
    debug.log_after(step_dir, session)

    tracer.close()
    rec_path = recorder.stop()
    session.stop()
    print(f"Screenshot saved to {output} (Debug: {step_dir})")
    print(f"Recording: {rec_path}  Trace: {tracer.path}")


# RDP Debug
debug_rdp_app = typer.Typer(help='Debug RDP connection.')
app.add_typer(debug_rdp_app, name='rdp')


@debug_rdp_app.command(name='screenshot')
def debug_rdp_screenshot(
    host: Annotated[
        str,
        typer.Option(help='RDP host', envvar='REMOTE_DESKTOP_RDP_HOST'),
    ] = cast(Any, ...),
    user: Annotated[
        str,
        typer.Option(help='RDP user', envvar='REMOTE_DESKTOP_RDP_USER'),
    ] = cast(Any, ...),
    password: Annotated[
        str,
        typer.Option(
            help='RDP password',
            envvar='REMOTE_DESKTOP_RDP_PASSWORD',
        ),
    ] = cast(Any, ...),
    output: str = 'rdp_screenshot.png',
    display: Annotated[
        str,
        typer.Option(help='Display number', envvar='REMOTE_DESKTOP_DISPLAY'),
    ] = ':99',
    resolution: Annotated[
        str,
        typer.Option(help='Resolution', envvar='REMOTE_DESKTOP_RESOLUTION'),
    ] = '1280x720',
):
    session = RDPSession(
        host, user, password,
        display_num=display, resolution=resolution,
    )
    session.start()

    debug = get_debug_logger('rdp')
    recorder = ScreenRecorder()
    recorder.start(
        session, output_path=str(
            debug.session_dir / 'recording.mp4',
        ),
    )
    tracer = TraceLogger(debug.session_dir / 'trace.jsonl')

    step_dir = debug.log_step(
        ActionType.SCREENSHOT, {
            'host': host, 'output': output,
        }, session,
    )
    session.take_screenshot(output)
    tracer.log_action('screenshot', {'output_path': output})
    debug.log_after(step_dir, session)

    tracer.close()
    rec_path = recorder.stop()
    session.stop()
    print(f"Screenshot saved to {output} (Debug: {step_dir})")
    print(f"Recording: {rec_path}  Trace: {tracer.path}")


if __name__ == '__main__':
    app()
