import structlog
import typer

from .cli.__main__ import app as cli_app
from .mcp.__main__ import app as mcp_app

# Configure structlog
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt='iso'),
        structlog.processors.JSONRenderer(),
    ],
)

app = typer.Typer(
    help='Remote Desktop MCP - Manage and debug remote desktop connections via MCP or CLI.',
    no_args_is_help=True,
)

app.add_typer(mcp_app, name='mcp')
app.add_typer(cli_app, name='cli')

if __name__ == '__main__':
    app()
