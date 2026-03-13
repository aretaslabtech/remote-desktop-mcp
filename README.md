# Remote Desktop MCP

A Model Context Protocol (MCP) server for remote desktop control (Local, RDP, VNC). This allows AI models like Claude to see and interact with your desktop.

![](./examples/recordings/demo.gif)

## Quick Start

The easiest way to install this server is via the Claude Desktop CLI:

```bash
# Local Desktop
claude mcp add remote-desktop -- uvx remote-desktop-mcp mcp local

# RDP
claude mcp add remote-desktop-rdp \
    -e REMOTE_DESKTOP_RDP_HOST=192.168.1.1 \
    -e REMOTE_DESKTOP_RDP_USER=ubuntu \
    -e REMOTE_DESKTOP_RDP_PASSWORD=ubuntu \
    -- uvx remote-desktop-mcp mcp rdp

# VNC
claude mcp add remote-desktop-vnc \
    -e REMOTE_DESKTOP_VNC_HOST=127.0.0.1:5900 \
    -e REMOTE_DESKTOP_VNC_PASSWORD=password \
    -- uvx remote-desktop-mcp mcp vnc
```

Quick test without mcp.

```bash
# Local Desktop
uvx remote-desktop-mcp cli local screenshot

# RDP
export REMOTE_DESKTOP_RDP_HOST=192.168.1.1
export REMOTE_DESKTOP_RDP_USER=ubuntu
export REMOTE_DESKTOP_RDP_PASSWORD=ubuntu
uvx remote-desktop-mcp cli rdp screenshot

# VNC
export REMOTE_DESKTOP_VNC_HOST=127.0.0.1:5900
export REMOTE_DESKTOP_VNC_PASSWORD=password
uvx remote-desktop-mcp cli vnc screenshot
```

## Demo

Connect your android devices.

```bash
claude mcp add remote-desktop-android -- uvx remote-desktop-mcp mcp adb
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REMOTE_DESKTOP_DISPLAY` | Display number (e.g., `:0`) | `:0` (local), `:99` (rdp) |
| `REMOTE_DESKTOP_RESOLUTION` | Resolution (e.g., `1280x720`) | `1280x720` |
| `REMOTE_DESKTOP_RDP_HOST` | RDP Host address | - |
| `REMOTE_DESKTOP_RDP_USER` | RDP Username | - |
| `REMOTE_DESKTOP_RDP_PASSWORD` | RDP Password | - |
| `REMOTE_DESKTOP_VNC_HOST` | VNC Host (`host:port`) | - |
| `REMOTE_DESKTOP_VNC_PASSWORD` | VNC Password | - |

## Features

- **Screenshots**: Let the AI "see" your screen.
- **Interactions**: Mouse clicks, movement, scrolling, and keyboard typing.
- **Protocols**: Native support for Local Desktop, RDP, and VNC.
- **Recording**: Capture desktop sessions as video for demos, debugging, and trace replay.

## Requirements

- Python 3.12+
- For RDP: `xfreerdp` and `Xvfb` must be installed if you are using ubuntu.
