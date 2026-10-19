# Remote Desktop MCP

A Model Context Protocol (MCP) server for remote desktop control (Local, RDP, VNC, ADB). This allows AI models like Claude to see and interact with your desktop.

![](./examples/recordings/demo.gif)

## Features

- **Screenshots**: Let the AI "see" your screen.
- **Interactions**: Mouse clicks, movement, scrolling, and keyboard typing.
- **Protocols**: Native support for Local Desktop, RDP, VNC, and Android Devices via ADB.
- **Recording**: Capture desktop sessions as video for demos, debugging, and trace replay.

## Quick Start

The easiest way to install this server is via the Gemini CLI:

```bash
# Local Desktop
gemini mcp add remote-desktop uvx remote-desktop-mcp mcp local

# Android (ADB)
gemini mcp add remote-desktop-vnc uvx remote-desktop-mcp mcp adb

# RDP
gemini mcp add remote-desktop-rdp \
    -e REMOTE_DESKTOP_RDP_HOST=10.134.179.153 \
    -e REMOTE_DESKTOP_RDP_USER=ubuntu \
    -e REMOTE_DESKTOP_RDP_PASSWORD=ubuntu \
    uvx remote-desktop-mcp mcp rdp

# VNC
gemini mcp add remote-desktop-vnc \
    -e REMOTE_DESKTOP_VNC_HOST=127.0.0.1:5900 \
    -e REMOTE_DESKTOP_VNC_PASSWORD=password \
    uvx remote-desktop-mcp mcp vnc
```

You can enable video record via adding `--record`, then check `.logs/session/` folder after the agent stopped.

```bash
gemini mcp add remote-desktop-rdp \
    -e REMOTE_DESKTOP_RDP_HOST=10.134.179.153 \
    -e REMOTE_DESKTOP_RDP_USER=ubuntu \
    -e REMOTE_DESKTOP_RDP_PASSWORD=ubuntu \
    uvx remote-desktop-mcp mcp rdp --record
```

## RDP clipboard and shared directory

The RDP backend exposes FreeRDP's clipboard channel as `clipboard_read`/`clipboard_write` MCP
tools, and an optional local Linux directory as a read/write drive inside the Windows session.
Neither requires installing anything on the Windows side.

```bash
export REMOTE_DESKTOP_RDP_SHARED_DIR="$HOME/rdp-share"
export REMOTE_DESKTOP_RDP_SHARED_NAME="shared"

uvx remote-desktop-mcp mcp rdp
```

(or the equivalent `--shared-dir`/`--shared-name` CLI flags, which take precedence over the
env vars above.) The directory must already exist; it is never created automatically, and it can
never be `/`, your home directory, the current working directory, `/tmp`, or a known
credential-holding directory such as `~/.ssh`.

Once connected, Windows sees the shared directory as a network drive at:

```text
\\tsclient\shared
```

(or `\\tsclient\<REMOTE_DESKTOP_RDP_SHARED_NAME>` if you set a different name). Anything copied
into that path from Windows appears immediately under the local directory on Linux, and vice
versa. `shared_drive_info()` reports the current configuration (or `{"enabled": false}` when no
shared directory is set).

If neither `REMOTE_DESKTOP_RDP_SHARED_DIR` nor `--shared-dir` is set, the RDP backend behaves
exactly as before — no drive is shared, and `clipboard_read`/`clipboard_write` still work over
FreeRDP's existing `+clipboard` channel as long as `xclip` is installed on the Linux side (the RDP
session still connects normally if it isn't; the clipboard tools simply report it as unavailable).
