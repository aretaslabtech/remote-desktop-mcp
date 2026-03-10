from typing import Annotated

import structlog
import typer

from ..protocol.local import LocalSession
from ..protocol.rdp import RDPSession
from ..protocol.vnc import VNCSession
from .server import mcp
from .server import set_session

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
    help='Remote Desktop MCP Server - Start the MCP server for various protocols.',
    no_args_is_help=True,
)


@app.command(name='local')
def mcp_local(
    display: Annotated[
        str | None, typer.Option(
        help='Display number (e.g. :0).',
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
        session.stop()


@app.command(name='rdp')
def mcp_rdp(
    host: Annotated[str, typer.Argument(help='RDP remote host address')],
    user: Annotated[str, typer.Argument(help='RDP username')],
    password: Annotated[str, typer.Argument(help='RDP password')],
    display: Annotated[
        str, typer.Option(
        help='Local Xvfb display number.',
        ),
    ] = ':99',
    resolution: Annotated[
        str, typer.Option(
        help='Screen resolution.',
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
        session.stop()


@app.command(name='vnc')
def mcp_vnc(
    host: Annotated[str, typer.Argument(help='VNC remote host address (host:port)')],
    password: Annotated[str | None, typer.Option(help='VNC password')] = None,
):
    """Start MCP server for a VNC connection."""
    logger.info('starting_vnc_mcp_server', host=host)
    session = VNCSession(host=host, password=password)
    set_session(session)
    try:
        mcp.run()
    finally:
        session.stop()


if __name__ == '__main__':
    app()
