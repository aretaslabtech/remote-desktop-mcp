from typing import Annotated
from typing import Any
from typing import cast

import structlog
import typer

from ..protocol.local import LocalSession
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


@app.command(name='local')
def mcp_local(
    display: Annotated[
        str | None,
        typer.Option(
            help='Display number (e.g. :0).',
            envvar='REMOTE_DESKTOP_DISPLAY',
        ),
    ] = None,
):
    """Start MCP server for the local desktop."""
    logger.info('starting_local_mcp_server', display=display)
    session = LocalSession(display_num=display)
    set_session(session)
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
):
    """Start MCP server for an RDP connection."""
    logger.info(
        'starting_rdp_mcp_server', host=host,
        user=user, display=display,
    )
    session = RDPSession(
        host=host, user=user, password=password,
        display_num=display, resolution=resolution,
    )
    set_session(session)
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
):
    """Start MCP server for a VNC connection."""
    logger.info('starting_vnc_mcp_server', host=host)
    session = VNCSession(host=host, password=password)
    set_session(session)
    try:
        mcp.run()
    finally:
        teardown()
        session.stop()


if __name__ == '__main__':
    app()
