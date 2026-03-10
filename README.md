# Remote Desktop MCP

A Model Context Protocol (MCP) server for remote desktop control (Local, RDP, VNC). This allows AI models like Claude to see and interact with your desktop.

## Quick Start

```
claude mcp add --transport stdio remote-desktop-mcp -- uvx remote-desktop-mcp
```
## Environment Variables

| Variable | Description |
|----------|-------------|
| `REMOTE_DESKTOP_DISPLAY` | Display number (e.g., `:0`) |
| `REMOTE_DESKTOP_RDP_HOST` | RDP Host address |
| `REMOTE_DESKTOP_RDP_USER` | RDP Username |
| `REMOTE_DESKTOP_RDP_PASSWORD` | RDP Password |
| `REMOTE_DESKTOP_VNC_HOST` | VNC Host (`host:port`) |
| `REMOTE_DESKTOP_VNC_PASSWORD` | VNC Password |

## Features

- **Screenshots**: Let the AI "see" your screen.
- **Interactions**: Mouse clicks, movement, scrolling, and keyboard typing.
- **Protocols**: Native support for Local Desktop, RDP, and VNC.

## Requirements

- Python 3.12+
- For RDP: `xfreerdp` and `Xvfb` must be installed on the host.

## License

MIT
