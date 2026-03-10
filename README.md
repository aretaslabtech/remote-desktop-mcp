# Remote Desktop MCP

A Model Context Protocol (MCP) server for remote desktop control, supporting Local, RDP, and VNC protocols. This server allows AI models (like Claude) to interact with your desktop or remote machines.

## Features

- **Protocol Support**: Local Desktop, RDP, and VNC.
- **Environment Variables**: Configure connection details via environment variables.
- **MCP Tools**:
  - `take_screenshot`: Capture the current screen.
  - `mouse_click`: Click at specific coordinates.
  - `mouse_move`: Move the cursor.
  - `mouse_scroll`: Scroll the mouse wheel.
  - `type_text`: Type text strings.
  - `press_key`: Press special keys (e.g., enter, backspace).

## Quick Start

### 1. Manual Configuration (Claude Desktop)

Add the following to your `claude_desktop_config.json`:

#### Local Desktop
```json
{
  "mcpServers": {
    "remote-desktop": {
      "command": "uvx",
      "args": ["remote-desktop-mcp", "mcp", "local"],
      "env": {
        "REMOTE_DESKTOP_DISPLAY": ":0"
      }
    }
  }
}
```

#### RDP
```json
{
  "mcpServers": {
    "remote-desktop-rdp": {
      "command": "uvx",
      "args": ["remote-desktop-mcp", "mcp", "rdp"],
      "env": {
        "REMOTE_DESKTOP_RDP_HOST": "your-host",
        "REMOTE_DESKTOP_RDP_USER": "your-user",
        "REMOTE_DESKTOP_RDP_PASSWORD": "your-password"
      }
    }
  }
}
```

#### VNC
```json
{
  "mcpServers": {
    "remote-desktop-vnc": {
      "command": "uvx",
      "args": ["remote-desktop-mcp", "mcp", "vnc"],
      "env": {
        "REMOTE_DESKTOP_VNC_HOST": "host:port",
        "REMOTE_DESKTOP_VNC_PASSWORD": "your-password"
      }
    }
  }
}
```

## Command Line Interface

You can run the server or debug tools directly using `uvx remote-desktop-mcp`.

### MCP Server
```bash
# Start MCP server for local desktop
uvx remote-desktop-mcp mcp local

# Start MCP server for RDP (using arguments)
uvx remote-desktop-mcp mcp rdp --host <host> --user <user> --password <pass>

# Start MCP server for VNC (using environment variables)
export REMOTE_DESKTOP_VNC_HOST="127.0.0.1:5900"
uvx remote-desktop-mcp mcp vnc
```

### Debug CLI
```bash
# Take a local screenshot
uvx remote-desktop-mcp cli local screenshot --output test.png

# Take a VNC screenshot
uvx remote-desktop-mcp cli vnc screenshot --host localhost:5900 --output vnc.png
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REMOTE_DESKTOP_DISPLAY` | Display number (Local/RDP) | `:99` (RDP), `None` (Local) |
| `REMOTE_DESKTOP_RDP_HOST` | RDP host address | - |
| `REMOTE_DESKTOP_RDP_USER` | RDP username | - |
| `REMOTE_DESKTOP_RDP_PASSWORD` | RDP password | - |
| `REMOTE_DESKTOP_VNC_HOST` | VNC host address (`host:port`) | - |
| `REMOTE_DESKTOP_VNC_PASSWORD` | VNC password | - |
| `REMOTE_DESKTOP_RESOLUTION` | Screen resolution (RDP) | `1280x720` |

## Requirements

- **Python**: 3.12+
- **System Dependencies**:
  - For RDP: `xfreerdp` and `Xvfb` must be installed.
  - For Local: Appropriate display permissions.

## License

MIT
