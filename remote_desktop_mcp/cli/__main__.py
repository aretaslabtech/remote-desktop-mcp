from typing import Annotated
from typing import Any
from typing import cast

import structlog
import typer

from ..mcp.debug import ActionType
from ..mcp.debug import get_debug_logger
from ..mcp.trace import TraceLogger
from ..protocol.adb import ADBSession
from ..protocol.base import MouseButton
from ..protocol.local import LocalSession
from ..protocol.playwright import PlaywrightSession
from ..protocol.rdp import RDPSession
from ..protocol.vnc import VNCSession

logger = structlog.get_logger()

app = typer.Typer(
    help='Remote Desktop Debug CLI - Test desktop protocols and actions independently.',
    no_args_is_help=True,
)

# ADB Debug
debug_adb_app = typer.Typer(help='Debug ADB connection.')
app.add_typer(debug_adb_app, name='adb')


@debug_adb_app.command(name='screenshot')
def debug_adb_screenshot(
    serial: Annotated[
        str | None,
        typer.Option(help='ADB serial', envvar='REMOTE_DESKTOP_ADB_SERIAL'),
    ] = None,
    output: str = 'adb_screenshot.png',
):
    session = ADBSession(serial=serial)
    session.start()

    debug = get_debug_logger('adb')
    tracer = TraceLogger(debug.session_dir / 'trace.jsonl')

    step_dir = debug.log_step(
        ActionType.SCREENSHOT, {
            'serial': serial, 'output': output,
        }, session,
    )
    session.take_screenshot(output)
    tracer.log_action('screenshot', {'output_path': output})
    debug.log_after(step_dir, session)

    tracer.close()
    session.stop()
    print(f"Screenshot saved to {output} (Debug: {step_dir})")


@debug_adb_app.command(name='click')
def debug_adb_click(
    x: int, y: int,
    serial: Annotated[
        str | None,
        typer.Option(help='ADB serial', envvar='REMOTE_DESKTOP_ADB_SERIAL'),
    ] = None,
):
    session = ADBSession(serial=serial)
    session.start()

    debug = get_debug_logger('adb')
    tracer = TraceLogger(debug.session_dir / 'trace.jsonl')

    step_dir = debug.log_step(
        ActionType.CLICK, {'x': x, 'y': y}, session,
    )
    session.click(x, y)
    tracer.log_action('click', {'x': x, 'y': y})
    debug.log_after(step_dir, session)

    tracer.close()
    session.stop()
    print(f"Clicked at ({x}, {y}) (Debug: {step_dir})")


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
    session.stop()
    print(f"Screenshot saved to {output} (Debug: {step_dir})")


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
    tracer = TraceLogger(debug.session_dir / 'trace.jsonl')

    step_dir = debug.log_step(
        ActionType.CLICK, {'x': x, 'y': y, 'button': button.value}, session,
    )
    session.click(x, y, button)
    tracer.log_action('click', {'x': x, 'y': y, 'button': button.value})
    debug.log_after(step_dir, session)

    tracer.close()
    session.stop()
    print(f"Clicked {button.value} at ({x}, {y}) (Debug: {step_dir})")


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
    session.stop()
    print(f"Screenshot saved to {output} (Debug: {step_dir})")


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
    session.stop()
    print(f"Screenshot saved to {output} (Debug: {step_dir})")


# Playwright Debug
debug_playwright_app = typer.Typer(help='Debug Playwright browser.')
app.add_typer(debug_playwright_app, name='playwright')


@debug_playwright_app.command(name='screenshot')
def debug_playwright_screenshot(
    url: Annotated[
        str,
        typer.Option(help='Initial URL', envvar='REMOTE_DESKTOP_PLAYWRIGHT_URL'),
    ] = "https://www.google.com",
    resolution: Annotated[
        str,
        typer.Option(
            help='Resolution',
            envvar='REMOTE_DESKTOP_RESOLUTION',
        ),
    ] = '1280x720',
    output: str = 'playwright_screenshot.png',
):
    session = PlaywrightSession(url=url, resolution=resolution)
    session.start()

    debug = get_debug_logger('playwright')
    tracer = TraceLogger(debug.session_dir / 'trace.jsonl')

    step_dir = debug.log_step(
        ActionType.SCREENSHOT, {
            'url': url, 'output': output,
        }, session,
    )
    session.take_screenshot(output)
    tracer.log_action('screenshot', {'output_path': output})
    debug.log_after(step_dir, session)

    tracer.close()
    session.stop()
    print(f"Screenshot saved to {output} (Debug: {step_dir})")


@debug_playwright_app.command(name='click')
def debug_playwright_click(
    x: int, y: int,
    url: Annotated[
        str,
        typer.Option(help='Initial URL', envvar='REMOTE_DESKTOP_PLAYWRIGHT_URL'),
    ] = "https://www.google.com",
    button: MouseButton = MouseButton.LEFT,
):
    session = PlaywrightSession(url=url)
    session.start()

    debug = get_debug_logger('playwright')
    tracer = TraceLogger(debug.session_dir / 'trace.jsonl')

    step_dir = debug.log_step(
        ActionType.CLICK, {'x': x, 'y': y, 'button': button.value}, session,
    )
    session.click(x, y, button)
    tracer.log_action('click', {'x': x, 'y': y, 'button': button.value})
    debug.log_after(step_dir, session)

    tracer.close()
    session.stop()
    print(f"Clicked {button.value} at ({x}, {y}) (Debug: {step_dir})")


@debug_playwright_app.command(name='type')
def debug_playwright_type(
    text: str,
    url: Annotated[
        str,
        typer.Option(help='Initial URL', envvar='REMOTE_DESKTOP_PLAYWRIGHT_URL'),
    ] = "https://www.google.com",
):
    session = PlaywrightSession(url=url)
    session.start()

    debug = get_debug_logger('playwright')
    tracer = TraceLogger(debug.session_dir / 'trace.jsonl')

    step_dir = debug.log_step(
        ActionType.TYPE, {'text': text}, session,
    )
    session.type_text(text)
    tracer.log_action('type', {'text': text})
    debug.log_after(step_dir, session)

    tracer.close()
    session.stop()
    print(f"Typed '{text}' (Debug: {step_dir})")


if __name__ == '__main__':
    app()
