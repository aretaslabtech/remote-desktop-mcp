from typing import Annotated

import structlog
import typer

from ..protocol.base import MouseButton
from ..protocol.local import LocalSession
from ..protocol.rdp import RDPSession
from ..protocol.vnc import VNCSession

# Configure structlog
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt='iso'),
        structlog.processors.JSONRenderer(),
    ],
)
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
    display: Annotated[str | None, typer.Option(help='Display number')] = None,
):
    session = LocalSession(display_num=display)
    session.start()
    session.take_screenshot(output)
    print(f"Screenshot saved to {output}")
    session.stop()


@debug_local_app.command(name='click')
def debug_local_click(
    x: int, y: int,
    button: MouseButton = MouseButton.LEFT,
    display: Annotated[str | None, typer.Option(help='Display number')] = None,
):
    session = LocalSession(display_num=display)
    session.start()
    session.click(x, y, button)
    session.stop()


# VNC Debug
debug_vnc_app = typer.Typer(help='Debug VNC connection.')
app.add_typer(debug_vnc_app, name='vnc')


@debug_vnc_app.command(name='screenshot')
def debug_vnc_screenshot(
    host: str,
    password: str | None = None,
    output: str = 'vnc_screenshot.png',
):
    session = VNCSession(host=host, password=password)
    session.start()
    session.take_screenshot(output)
    print(f"Screenshot saved to {output}")
    session.stop()


# RDP Debug
debug_rdp_app = typer.Typer(help='Debug RDP connection.')
app.add_typer(debug_rdp_app, name='rdp')


@debug_rdp_app.command(name='screenshot')
def debug_rdp_screenshot(
    host: str, user: str, password: str,
    output: str = 'rdp_screenshot.png',
    display: str = ':99',
    resolution: str = '1280x720',
):
    session = RDPSession(
        host, user, password,
        display_num=display, resolution=resolution,
    )
    session.start()
    session.take_screenshot(output)
    print(f"Screenshot saved to {output}")
    session.stop()


if __name__ == '__main__':
    app()
