"""Post-process a raw screen recording with action annotations from a trace file.

Reads the raw MP4 output of :class:`~remote_desktop_mcp.mcp.recorder.ScreenRecorder`
and the JSONL trace produced by :class:`~remote_desktop_mcp.mcp.trace.TraceLogger`,
then renders a new annotated video where each agent action is highlighted:

- **Left click**:  red  shrinking ripple circle + crosshair
- **Right click**: blue shrinking ripple circle + crosshair
- **Mouse move**:  yellow crosshair at the destination
- **Scroll**:      purple directional arrow in the frame centre
- **Type / key**:  semi-transparent bottom banner with the text

Usage::

    remote-desktop-mcp annotate \\
        --video  .logs/sessions/20260310_233748_rdp/recording.mp4 \\
        --trace  .logs/sessions/20260310_233748_rdp/trace.jsonl \\
        --output annotated.mp4
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
from typing import Any

import typer
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

app = typer.Typer(
    help='Render an annotated replay from a raw recording + JSONL trace.',
    no_args_is_help=True,
)

# How long (seconds) each annotation is visible in the output video.
_DEFAULT_TTL: float = 1.5


@app.command()
def annotate(
    video: Annotated[
        Path,
        typer.Option(help='Raw recording MP4 (or GIF) path.'),
    ],
    trace: Annotated[
        Path,
        typer.Option(help='JSONL trace file path.'),
    ],
    output: Annotated[
        Path,
        typer.Option(help='Output annotated MP4 path.'),
    ] = Path('annotated.mp4'),
    ttl: Annotated[
        float,
        typer.Option(help='Seconds each annotation remains visible.'),
    ] = _DEFAULT_TTL,
) -> None:
    """Combine a raw screen recording with a JSONL trace to produce an annotated video."""
    if not video.exists():
        typer.echo(f"Error: video file not found: {video}", err=True)
        raise typer.Exit(1)
    if not trace.exists():
        typer.echo(f"Error: trace file not found: {trace}", err=True)
        raise typer.Exit(1)

    # ------------------------------------------------------------------ #
    # Load trace
    # ------------------------------------------------------------------ #
    session_start_time, fps_from_trace, actions = _load_trace(trace)

    # ------------------------------------------------------------------ #
    # Load video metadata sidecar (preferred) or fall back to trace fps
    # ------------------------------------------------------------------ #
    meta_path = video.with_suffix('.meta.json')
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        video_start_time: float = meta.get('start_time', session_start_time)
        fps: int = int(meta.get('fps', fps_from_trace))
    else:
        typer.echo(
            f"Warning: sidecar '{meta_path.name}' not found; "
            'using session_start timestamp from trace.',
            err=True,
        )
        video_start_time = session_start_time
        fps = fps_from_trace

    typer.echo(
        f"video_start={video_start_time:.3f}  fps={fps}  "
        f"actions={len(actions)}  ttl={ttl}s",
    )

    # ------------------------------------------------------------------ #
    # Read + annotate frames
    # ------------------------------------------------------------------ #
    try:
        import imageio  # type: ignore[import-untyped]
        import numpy as np
    except ImportError:
        typer.echo(
            'Error: imageio and numpy are required.  '
            'Run: uv add imageio imageio-ffmpeg numpy',
            err=True,
        )
        raise typer.Exit(1)

    reader: Any = imageio.get_reader(str(video))
    output.parent.mkdir(parents=True, exist_ok=True)
    writer: Any = imageio.get_writer(
        str(output), fps=fps, macro_block_size=None,
    )

    try:
        for frame_idx, frame_array in enumerate(reader):
            frame_ts = video_start_time + frame_idx / fps
            active = [
                (a, frame_ts - a['timestamp'])
                for a in actions
                if 0.0 <= frame_ts - a['timestamp'] <= ttl
            ]

            img = Image.fromarray(frame_array).convert('RGB')

            if active:
                img = _render_annotations(img, active, ttl)

            w, h = img.size
            ew, eh = w - w % 2, h - h % 2
            if (ew, eh) != (w, h):
                img = img.crop((0, 0, ew, eh))

            writer.append_data(np.asarray(img))
    finally:
        reader.close()
        writer.close()

    typer.echo(f"Annotated video saved to: {output}")


# --------------------------------------------------------------------------- #
# Trace loading
# --------------------------------------------------------------------------- #

def _load_trace(
    path: Path,
) -> tuple[float, int, list[dict]]:
    """Parse a JSONL trace file.

    Returns
    -------
    (session_start_timestamp, fps, list_of_action_records)
    """
    session_start_time: float = 0.0
    fps: int = 5
    actions: list[dict] = []

    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get('type') == 'session_start':
                session_start_time = float(rec.get('timestamp', 0.0))
                fps = int(rec.get('fps', 5))
            elif rec.get('type') == 'action':
                actions.append(rec)

    return session_start_time, fps, actions


# --------------------------------------------------------------------------- #
# Annotation rendering
# --------------------------------------------------------------------------- #

def _render_annotations(
    img: Image.Image,
    active: list[tuple[dict, float]],   # (action_record, elapsed_seconds)
    ttl: float,
) -> Image.Image:
    """Draw all active annotations onto *img* and return the result."""
    rgba = img.convert('RGBA')
    overlay = Image.new('RGBA', rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for rec, elapsed in active:
        alpha_f = max(0.0, 1.0 - elapsed / ttl)   # 1.0 = fresh, 0.0 = expired
        alpha = int(alpha_f * 255)
        action = rec.get('action', '')
        params = rec.get('params', {})

        if action == 'click':
            _draw_click(draw, params, alpha, alpha_f)
        elif action == 'move':
            _draw_move(draw, params, alpha)
        elif action == 'scroll':
            _draw_scroll(draw, img.size, params, alpha)

    img = Image.alpha_composite(rgba, overlay).convert('RGB')

    for rec, elapsed in active:
        alpha_f = max(0.0, 1.0 - elapsed / ttl)
        action = rec.get('action', '')
        params = rec.get('params', {})
        if action in ('type', 'key'):
            img = _draw_text_banner(img, action, params, alpha_f)

    return img


def _draw_click(
    draw: ImageDraw.ImageDraw,
    params: dict,
    alpha: int,
    alpha_f: float,
) -> None:
    x, y = params.get('x', 0), params.get('y', 0)
    button = params.get('button', 'left')
    if button == 'right':
        color = (50, 50, 255, alpha)
    elif button == 'middle':
        color = (50, 220, 50, alpha)
    else:
        color = (255, 50, 50, alpha)

    # Radius shrinks as the annotation ages (fresh = large, fading = small)
    r = max(6, int(36 * alpha_f))
    draw.ellipse((x - r, y - r, x + r, y + r), outline=color, width=3)
    draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color)
    arm = r + 10
    draw.line((x - arm, y, x - r - 2, y), fill=color, width=2)
    draw.line((x + r + 2, y, x + arm, y), fill=color, width=2)
    draw.line((x, y - arm, x, y - r - 2), fill=color, width=2)
    draw.line((x, y + r + 2, x, y + arm), fill=color, width=2)


def _draw_move(draw: ImageDraw.ImageDraw, params: dict, alpha: int) -> None:
    x, y = params.get('x', 0), params.get('y', 0)
    c = (255, 220, 50, alpha)
    r = 14
    draw.line((x - r, y, x + r, y), fill=c, width=2)
    draw.line((x, y - r, x, y + r), fill=c, width=2)
    draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=c)


def _draw_scroll(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    params: dict,
    alpha: int,
) -> None:
    w, h = size
    # Compact arrow in the top-right corner to avoid covering content
    cx, cy = w - 60, 60
    clicks = params.get('clicks', 0)
    c = (220, 100, 255, alpha)
    if clicks > 0:
        draw.polygon([(cx, cy - 20), (cx - 12, cy), (cx + 12, cy)], fill=c)
        draw.rectangle([cx - 4, cy, cx + 4, cy + 14], fill=c)
    else:
        draw.polygon([(cx, cy + 20), (cx - 12, cy), (cx + 12, cy)], fill=c)
        draw.rectangle([cx - 4, cy - 14, cx + 4, cy], fill=c)


def _draw_text_banner(
    img: Image.Image,
    action: str,
    params: dict,
    alpha_f: float,
) -> Image.Image:
    w, h = img.size
    banner_h = 42

    if action == 'type':
        text = f'\u2328  Typing:  {repr(params.get("text", ""))}'
        bg = (0, 50, 0)
        fg = (80, 255, 80)
    elif action == 'key':
        text = f'\u2328  Key:  [ {params.get("key", "").upper()} ]'
        bg = (0, 35, 55)
        fg = (80, 220, 255)
    else:
        return img

    if len(text) > 90:
        text = text[:87] + '...'

    a = int(alpha_f * 200)
    banner = Image.new('RGBA', (w, banner_h), (*bg, a))
    img_rgba = img.convert('RGBA')
    img_rgba.paste(banner, (0, h - banner_h), mask=banner)

    result = img_rgba.convert('RGB')
    draw = ImageDraw.Draw(result)
    font = _load_font(16)
    draw.text(
        (12, h - banner_h + (banner_h - 16) // 2),
        text, fill=fg, font=font,
    )
    return result


# --------------------------------------------------------------------------- #

def _load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
        '/System/Library/Fonts/Helvetica.ttc',
        'C:/Windows/Fonts/arial.ttf',
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()
