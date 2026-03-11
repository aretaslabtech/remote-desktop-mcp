from typing import Annotated
from typing import Any
from typing import cast

import structlog
import typer

from ..protocol.adb import ADBSession
from ..protocol.local import LocalSession
from ..protocol.playwright import PlaywrightSession
from ..protocol.rdp import RDPSession
from ..protocol.vnc import VNCSession
from .server import mcp
from .server import set_session
from .server import teardown

logger = structlog.get_logger()

app = typer.Typer(
    help='Start the MCP server for various protocols.',
    no_args_is_help=True,
)


@app.command(name='adb')
def mcp_adb(
    serial: Annotated[
        str | None,
        typer.Option(
            help='ADB device serial number.',
            envvar='REMOTE_DESKTOP_ADB_SERIAL',
        ),
    ] = None,
    record: Annotated[
        bool,
        typer.Option(
            help='Enable continuous screen recording for the whole session.',
        ),
    ] = False,
):
    """Start MCP server for an Android device via ADB."""
    logger.info('starting_adb_mcp_server', serial=serial, record=record)
    session = ADBSession(serial=serial)
    set_session(session, record=record)
    try:
        mcp.run()
    finally:
        teardown()
        session.stop()


@app.command(name='local')
def mcp_local(
    display: Annotated[
        str | None,
        typer.Option(
            help='Display number (e.g. :0).',
            envvar='REMOTE_DESKTOP_DISPLAY',
        ),
    ] = None,
    record: Annotated[
        bool,
        typer.Option(
            help='Enable continuous screen recording for the whole session.',
        ),
    ] = False,
):
    """Start MCP server for the local desktop."""
    logger.info('starting_local_mcp_server', display=display, record=record)
    session = LocalSession(display_num=display)
    set_session(session, record=record)
    try:
        mcp.run()
    finally:
        teardown()
        session.stop()


@app.command(name='rdp')
def mcp_rdp(
    host: Annotated[
        str,
        typer.Option(
            help='RDP remote host address',
            envvar='REMOTE_DESKTOP_RDP_HOST',
        ),
    ] = cast(Any, ...),
    user: Annotated[
        str,
        typer.Option(help='RDP username', envvar='REMOTE_DESKTOP_RDP_USER'),
    ] = cast(Any, ...),
    password: Annotated[
        str,
        typer.Option(
            help='RDP password',
            envvar='REMOTE_DESKTOP_RDP_PASSWORD',
        ),
    ] = cast(Any, ...),
    display: Annotated[
        str,
        typer.Option(
            help='Local Xvfb display number.',
            envvar='REMOTE_DESKTOP_DISPLAY',
        ),
    ] = ':99',
    resolution: Annotated[
        str,
        typer.Option(
            help='Screen resolution.',
            envvar='REMOTE_DESKTOP_RESOLUTION',
        ),
    ] = '1280x720',
    record: Annotated[
        bool,
        typer.Option(
            help='Enable continuous screen recording for the whole session.',
        ),
    ] = False,
):
    """Start MCP server for an RDP connection."""
    logger.info(
        'starting_rdp_mcp_server', host=host,
        user=user, display=display, record=record,
    )
    session = RDPSession(
        host=host, user=user, password=password,
        display_num=display, resolution=resolution,
    )
    set_session(session, record=record)
    try:
        mcp.run()
    finally:
        teardown()
        session.stop()


@app.command(name='vnc')
def mcp_vnc(
    host: Annotated[
        str,
        typer.Option(
            help='VNC remote host address (host:port)',
            envvar='REMOTE_DESKTOP_VNC_HOST',
        ),
    ] = cast(Any, ...),
    password: Annotated[
        str | None,
        typer.Option(
            help='VNC password',
            envvar='REMOTE_DESKTOP_VNC_PASSWORD',
        ),
    ] = None,
    record: Annotated[
        bool,
        typer.Option(
            help='Enable continuous screen recording for the whole session.',
        ),
    ] = False,
):
    """Start MCP server for a VNC connection."""
    logger.info('starting_vnc_mcp_server', host=host, record=record)
    session = VNCSession(host=host, password=password)
    set_session(session, record=record)
    try:
        mcp.run()
    finally:
        teardown()
        session.stop()


@app.command(name='playwright')
def mcp_playwright(
    url: Annotated[
        str,
        typer.Option(
            help='Initial URL to open.',
            envvar='REMOTE_DESKTOP_PLAYWRIGHT_URL',
        ),
    ] = 'https://www.google.com',
    resolution: Annotated[
        str,
        typer.Option(
            help='Screen resolution (e.g. 1280x720).',
            envvar='REMOTE_DESKTOP_RESOLUTION',
        ),
    ] = '1280x720',
    headless: Annotated[
        bool,
        typer.Option(
            help='Run browser in headless mode.',
            envvar='REMOTE_DESKTOP_PLAYWRIGHT_HEADLESS',
        ),
    ] = False,
    user_data_dir: Annotated[
        str | None,
        typer.Option(
            help='Path to a user data directory for persistent session.',
            envvar='REMOTE_DESKTOP_PLAYWRIGHT_USER_DATA_DIR',
        ),
    ] = None,
    record: Annotated[
        bool,
        typer.Option(
            help='Enable continuous screen recording for the whole session.',
        ),
    ] = False,
):
    """Start MCP server for a Playwright browser session."""
    logger.info(
        'starting_playwright_mcp_server',
        url=url, resolution=resolution, headless=headless, record=record,
    )
    session = PlaywrightSession(
        url=url, resolution=resolution,
        headless=headless, user_data_dir=user_data_dir,
    )
    set_session(session, record=record)
    try:
        mcp.run()
    finally:
        teardown()
        session.stop()


if __name__ == '__main__':
    app()
