"""Post-process a raw screen recording with action annotations from a trace file.

Features
--------
* Accepts a single segment file **or** a segment directory produced by the
  segmented recorder (``recording_0000.mp4``, ``recording_0001.mp4``, …).
* **Idle acceleration**: stretches with no agent activity are played at
  ``--idle-speed`` × normal speed (default 8×) to keep the video concise.
* **HUD bar**: a 2-line bar appended below each frame shows session metadata
  (start UTC, total duration, actions, FPS) on the top row and the live
  elapsed/wall-clock UTC time + speedup badge on the bottom row.
* Action annotations: click ripples, move crosshairs, scroll arrows, text
  banners (same as before).

Usage::

    remote-desktop-mcp annotate \\
        --video  .logs/sessions/20260310_233748_rdp/ \\
        --trace  .logs/sessions/20260310_233748_rdp/trace.jsonl \\
        --output annotated.mp4
"""
from __future__ import annotations

import bisect
import json
from datetime import datetime
from datetime import timezone
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

_DEFAULT_TTL: float = 1.5
_DEFAULT_IDLE_SECONDS: float = 0.3   # each idle span → 0.3 s in output
_ACTIVE_PRE: float = 0.2   # seconds before a UI action shown at normal speed
_ACTIVE_POST: float = 1.0  # seconds after  a UI action shown at normal speed
_HUD_H: int = 66           # height of 3-line HUD bar appended below the frame

# Only these action types are considered real UI interactions that pause fast-forward.
_UI_ACTIONS: frozenset[str] = frozenset({
    'tap', 'click', 'type', 'key', 'hotkey', 'scroll', 'move',
    'swipe', 'long_press',
})


# =========================================================================== #
# CLI entry point
# =========================================================================== #

@app.command()
def annotate(
    video: Annotated[
        Path,
        typer.Option(help='Raw recording file or segment directory.'),
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
        typer.Option(help='Seconds each annotation stays visible.'),
    ] = _DEFAULT_TTL,
    idle_seconds: Annotated[
        float,
        typer.Option(
            help='Each idle gap between actions is collapsed to this many seconds in the output.',
        ),
    ] = _DEFAULT_IDLE_SECONDS,
    speed: Annotated[
        float,
        typer.Option(
            help='Global playback speedup factor applied on top of idle collapsing (e.g. 2.0 = 2× faster overall).',
        ),
    ] = 1.0,
) -> None:
    """Combine a raw screen recording with a JSONL trace to produce an annotated video."""
    if not video.exists():
        typer.echo(f'Error: video path not found: {video}', err=True)
        raise typer.Exit(1)
    if not trace.exists():
        typer.echo(f'Error: trace file not found: {trace}', err=True)
        raise typer.Exit(1)

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

    session_start, session_end, fps_hint, actions, session_meta = _load_trace(
        trace,
    )
    segments = _collect_segments(video, fps_hint)
    if not segments:
        typer.echo('Error: no video segments found.', err=True)
        raise typer.Exit(1)

    fps = segments[0][1].get('fps', fps_hint)
    total_segments = len(segments)
    speed = max(1.0, speed)   # guard: must be >= 1
    global_step = max(1, round(speed))   # keep every Nth frame
    typer.echo(
        f'segments={total_segments}  fps={fps}  '
        f'actions={len(actions)}  idle_seconds={idle_seconds}s  speed={speed:.1f}×',
    )

    active_intervals = _build_active_intervals(
        [a for a in actions if a.get('action') in _UI_ACTIONS],
        _ACTIVE_PRE, _ACTIVE_POST + ttl,
    )

    first_reader: Any = imageio.get_reader(str(segments[0][0]))
    first_frame = next(iter(first_reader))
    first_reader.close()
    import numpy as np  # noqa: F811
    fh, fw = np.asarray(first_frame).shape[:2]
    fw = fw - fw % 2
    fh = fh - fh % 2
    frame_size = (fw, fh)

    dur_s = (session_end - session_start) if session_end else \
            (actions[-1]['timestamp'] - session_start if actions else 0.0)

    # Upper bound for the last idle span (after final active window)
    wall_end = session_end or \
        (
            actions[-1]['timestamp'] + _ACTIVE_POST +
            ttl if actions else session_start + 1.0
        )

    # ------------------------------------------------------------------ #
    # Timing + size stats
    # ------------------------------------------------------------------ #
    import time as _time
    t_start = _time.monotonic()
    input_size = _total_size(video)

    output.parent.mkdir(parents=True, exist_ok=True)
    writer: Any = imageio.get_writer(
        str(output), fps=fps, macro_block_size=None,
    )

    _SKIP_META_KEYS = {
        'timestamp', 'duration', 'fps',
        'segments', 'actions', 'idle_seconds', 'type',
    }
    extra_fields = [
        f'{k}: {v}'
        for k, v in session_meta.items()
        if k not in _SKIP_META_KEYS and isinstance(v, (str, int, float, bool))
    ]
    action_timestamps = [a['timestamp'] for a in actions]

    hud_meta = {
        'start_str': datetime.fromtimestamp(
            session_meta.get('timestamp', session_start), tz=timezone.utc,
        ).strftime('%Y-%m-%d %H:%M:%S UTC') if session_meta.get('timestamp', session_start) else 'unknown',
        'dur_str': _fmt_duration(dur_s),
        'total_dur': dur_s,
        'total_actions': len(actions),
        'fps': fps,
        'segments': total_segments,
        'extra_fields': extra_fields,
        'action_list': actions,
        'action_timestamps': action_timestamps,
    }

    try:
        for seg_idx, (seg_path, seg_meta) in enumerate(segments):
            seg_start: float = seg_meta.get('start_time', session_start)
            typer.echo(
                f'  segment {seg_idx + 1}/{total_segments}: {seg_path.name}',
            )
            reader: Any = imageio.get_reader(str(seg_path))

            for frame_idx, frame_array in enumerate(reader):
                # Global speed: skip frames that don't fall on the step boundary
                if global_step > 1 and (frame_idx % global_step) != 0:
                    continue

                frame_ts = seg_start + frame_idx / fps
                elapsed = frame_ts - session_start
                is_active = _in_active_window(frame_ts, active_intervals)

                speed_label = ''
                if not is_active:
                    include, speed_label = _idle_frame_decision(
                        frame_ts, active_intervals, session_start, wall_end, fps, idle_seconds,
                    )
                    if not include:
                        continue

                active_anns = [
                    (a, frame_ts - a['timestamp'])
                    for a in actions
                    if 0.0 <= frame_ts - a['timestamp'] <= ttl
                ]

                img = Image.fromarray(np.asarray(frame_array)).convert('RGB')
                if img.size != frame_size:
                    img = img.resize(frame_size, Image.Resampling.LANCZOS)

                if active_anns:
                    img = _render_annotations(img, active_anns, ttl)

                img = _draw_hud(img, elapsed, frame_ts, speed_label, hud_meta)
                img = _crop_even(img)
                writer.append_data(np.asarray(img))

            reader.close()
    finally:
        writer.close()

    t_elapsed = _time.monotonic() - t_start
    output_size = output.stat().st_size if output.exists() else 0
    typer.echo(
        f'Annotated video saved to: {output}\n'
        f'  Input size:  {_fmt_size(input_size)}',
    )
    typer.echo(
        f'  Output size: {_fmt_size(output_size)}'
        f'  ({output_size / max(input_size, 1) * 100:.1f}% of input)',
    )
    typer.echo(
        f'  Source duration: {_fmt_duration(dur_s)}'
        f'  →  Output duration: ~{_fmt_duration(_estimate_output_duration(dur_s, active_intervals, idle_seconds) / speed)}',
    )
    typer.echo(f'  Processing time: {_fmt_duration(t_elapsed)}')


# =========================================================================== #
# Segment collection
# =========================================================================== #

def _collect_segments(video: Path, fallback_fps: int) -> list[tuple[Path, dict]]:
    if video.is_dir():
        files = sorted(video.glob('*_????.mp4')) or sorted(video.glob('*.mp4'))
    else:
        files = [video]

    result = []
    for f in files:
        meta_path = f.with_suffix('.meta.json')
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding='utf-8'))
            except Exception:
                meta = {'fps': fallback_fps}
        else:
            meta = {'fps': fallback_fps}
        result.append((f, meta))
    return result


# =========================================================================== #
# Trace loading
# =========================================================================== #

def _load_trace(path: Path) -> tuple[float, float | None, int, list[dict], dict]:
    session_start: float = 0.0
    session_end: float | None = None
    fps: int = 5
    actions: list[dict] = []
    meta: dict = {}

    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = rec.get('type')
            if t == 'session_start':
                session_start = float(rec.get('timestamp', 0.0))
                fps = int(rec.get('fps', 5))
                meta = {k: v for k, v in rec.items() if k not in ('type', 'fps')}
            elif t == 'action':
                actions.append(rec)
            elif t == 'session_end':
                session_end = float(rec.get('timestamp', 0.0))

    return session_start, session_end, fps, actions, meta


# =========================================================================== #
# Active-window helpers
# =========================================================================== #

def _build_active_intervals(actions: list[dict], pre: float, post: float) -> list[tuple[float, float]]:
    if not actions:
        return []
    intervals = sorted(
        (a['timestamp'] - pre, a['timestamp'] + post)
        for a in actions
    )
    merged: list[tuple[float, float]] = [intervals[0]]
    for start, end in intervals[1:]:
        ps, pe = merged[-1]
        if start <= pe:
            merged[-1] = (ps, max(pe, end))
        else:
            merged.append((start, end))
    return merged


def _in_active_window(ts: float, intervals: list[tuple[float, float]]) -> bool:
    if not intervals:
        return False
    starts = [s for s, _ in intervals]
    idx = bisect.bisect_right(starts, ts) - 1
    return idx >= 0 and intervals[idx][0] <= ts <= intervals[idx][1]


def _find_idle_span(
    ts: float,
    intervals: list[tuple[float, float]],
    session_start: float,
    session_end: float,
) -> tuple[float, float]:
    """Return the idle (start, end) span that contains *ts*.

    Assumes *ts* is not inside any active interval.
    """
    if not intervals:
        return (session_start, session_end)
    starts = [s for s, _ in intervals]
    idx = bisect.bisect_right(starts, ts) - 1
    if idx < 0:
        return (session_start, intervals[0][0])
    if ts > intervals[-1][1]:
        return (intervals[-1][1], session_end)
    # between intervals[idx] and intervals[idx+1]
    return (intervals[idx][1], intervals[idx + 1][0])


def _idle_frame_decision(
    ts: float,
    intervals: list[tuple[float, float]],
    session_start: float,
    session_end: float,
    fps: int,
    idle_seconds: float,
) -> tuple[bool, str]:
    """Decide whether to include an idle frame and compute its HUD speed label.

    Each idle span is collapsed to *idle_seconds* in the output regardless of
    its actual duration, so the effective speedup varies per span.
    """
    span_start, span_end = _find_idle_span(
        ts, intervals, session_start, session_end,
    )
    span_duration = max(span_end - span_start, 1.0 / fps)
    span_frames = max(1, round(span_duration * fps))
    target_frames = max(1, round(idle_seconds * fps))
    step = max(1, round(span_frames / target_frames))

    frame_offset = round((ts - span_start) * fps)
    include = (frame_offset % step == 0)

    speedup = span_duration / max(idle_seconds, 1.0 / fps)
    speed_label = f'\u23e9 {speedup:.0f}\u00d7' if speedup >= 1.5 else ''
    return include, speed_label


# =========================================================================== #
# HUD overlay
# =========================================================================== #

def _draw_hud(
    img: Image.Image,
    elapsed: float,
    frame_ts: float,
    speed_label: str,
    hud_meta: dict,
) -> Image.Image:
    """Append a 3-line black HUD bar *below* the frame (canvas grows downward).

    Line 1 — static session metadata (start UTC, duration, FPS, extra fields).
    Line 2 — live position: elapsed, UTC wall clock, progress %, speedup badge.
    Line 3 — action context: last completed action + next upcoming action.
    """
    w, h = img.size
    canvas = Image.new('RGB', (w, h + _HUD_H), (0, 0, 0))
    canvas.paste(img, (0, 0))
    draw = ImageDraw.Draw(canvas)
    font = _load_font(12)
    line_h = _HUD_H // 3   # height per HUD line (~22 px)

    # Separator line between video and HUD
    draw.line([(0, h), (w, h)], fill=(40, 40, 60), width=1)

    # ---- Line 1: static session metadata ---------------------------------- #
    segs = hud_meta.get('segments', 1)
    seg_part = f'  │  {segs} seg' + \
        ('s' if segs != 1 else '') if segs > 1 else ''
    extra = ''.join(f'  │  {e}' for e in hud_meta.get('extra_fields', []))
    meta_line = (
        f"⏺  {hud_meta.get('start_str', '?')}"
        f"  │  {hud_meta.get('dur_str', '?')}"
        f"  │  {hud_meta.get('total_actions', '?')} actions"
        f"  │  {hud_meta.get('fps', '?')} fps"
        f"{seg_part}{extra}"
    )
    draw.text((8, h + 3), meta_line, fill=(130, 155, 200), font=font)

    # ---- Line 2: live position + progress --------------------------------- #
    wall_utc = datetime.fromtimestamp(
        frame_ts, tz=timezone.utc,
    ).strftime('%Y-%m-%d %H:%M:%S')
    elapsed_str = _fmt_duration(elapsed)
    total_dur = hud_meta.get('total_dur', 1.0)
    pct = min(100.0, elapsed / max(total_dur, 0.001) * 100)
    pos_line = f'⏱  +{elapsed_str}  │  {wall_utc} UTC  │  {pct:.1f}%'
    draw.text((8, h + line_h + 3), pos_line, fill=(200, 220, 255), font=font)
    if speed_label:
        draw.text(
            (w - 90, h + line_h + 3), speed_label,
            fill=(255, 200, 60), font=font,
        )

    # ---- Line 3: last / next action --------------------------------------- #
    action_list: list[dict] = hud_meta.get('action_list', [])
    action_ts: list[float] = hud_meta.get('action_timestamps', [])
    if action_list and action_ts:
        idx = bisect.bisect_right(action_ts, frame_ts) - 1
        last_str = f'◄ {_fmt_action_short(action_list[idx])}' if idx >= 0 else '◄ —'
        if idx + 1 < len(action_list):
            nxt = action_list[idx + 1]
            delay = nxt['timestamp'] - frame_ts
            next_str = f'► {_fmt_action_short(nxt)}  (in {delay:.1f}s)'
        else:
            next_str = '► —'
        act_line = f'{last_str}  │  {next_str}'
    else:
        act_line = ''
    draw.text(
        (8, h + 2 * line_h + 3), act_line,
        fill=(170, 210, 140), font=font,
    )

    return canvas


# =========================================================================== #
# Annotation rendering
# =========================================================================== #

def _render_annotations(img: Image.Image, active: list[tuple[dict, float]], ttl: float) -> Image.Image:
    rgba = img.convert('RGBA')
    overlay = Image.new('RGBA', rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for rec, elapsed in active:
        alpha_f = max(0.0, 1.0 - elapsed / ttl)
        alpha = int(alpha_f * 255)
        action = rec.get('action', '')
        params = rec.get('params', {})
        if action in ('click', 'tap', 'long_press'):
            _draw_click(draw, params, alpha, alpha_f)
        elif action == 'move':
            _draw_move(draw, params, alpha)
        elif action == 'scroll':
            _draw_scroll(draw, img.size, params, alpha)
        elif action == 'swipe':
            _draw_swipe(draw, params, alpha)

    img = Image.alpha_composite(rgba, overlay).convert('RGB')

    for rec, elapsed in active:
        alpha_f = max(0.0, 1.0 - elapsed / ttl)
        action = rec.get('action', '')
        params = rec.get('params', {})
        if action in ('type', 'key', 'hotkey', 'long_press'):
            img = _draw_text_banner(img, action, params, alpha_f)

    return img


def _draw_click(draw: ImageDraw.ImageDraw, params: dict, alpha: int, alpha_f: float) -> None:
    x, y = params.get('x', 0), params.get('y', 0)
    button = params.get('button', 'left')
    color = {
        'left': (255, 50, 50, alpha),
        'right': (50, 50, 255, alpha),
        'middle': (50, 220, 50, alpha),
    }.get(button, (255, 50, 50, alpha))
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


def _draw_scroll(draw: ImageDraw.ImageDraw, size: tuple[int, int], params: dict, alpha: int) -> None:
    w, h = size
    cx, cy = w - 60, 60
    clicks = params.get('clicks', 0)
    c = (220, 100, 255, alpha)
    if clicks > 0:
        draw.polygon([(cx, cy - 20), (cx - 12, cy), (cx + 12, cy)], fill=c)
        draw.rectangle([cx - 4, cy, cx + 4, cy + 14], fill=c)
    else:
        draw.polygon([(cx, cy + 20), (cx - 12, cy), (cx + 12, cy)], fill=c)
        draw.rectangle([cx - 4, cy - 14, cx + 4, cy], fill=c)


def _draw_swipe(draw: ImageDraw.ImageDraw, params: dict, alpha: int) -> None:
    x1, y1 = params.get('x1', 0), params.get('y1', 0)
    x2, y2 = params.get('x2', 0), params.get('y2', 0)
    c = (50, 220, 220, alpha)
    # Start dot
    draw.ellipse((x1 - 6, y1 - 6, x1 + 6, y1 + 6), fill=c)
    # Arrow line
    draw.line((x1, y1, x2, y2), fill=c, width=3)
    # End dot
    draw.ellipse(
        (x2 - 4, y2 - 4, x2 + 4, y2 + 4),
        fill=c, outline=(255, 255, 255, alpha),
    )


def _draw_text_banner(img: Image.Image, action: str, params: dict, alpha_f: float) -> Image.Image:
    w, h = img.size
    banner_h = 42
    if action == 'type':
        text = f'\u2328  Typing:  {repr(params.get("text", ""))}'
        bg, fg = (0, 50, 0), (80, 255, 80)
    elif action == 'key':
        text = f'\u2328  Key:  [ {params.get("key", "").upper()} ]'
        bg, fg = (0, 35, 55), (80, 220, 255)
    elif action == 'hotkey':
        text = f'\u2328  Hotkey:  [ {params.get("keys", "").upper()} ]'
        bg, fg = (40, 20, 55), (200, 150, 255)
    elif action == 'long_press':
        text = f'\u261e  Long press ({params.get("x", 0)}, {params.get("y", 0)}) {params.get("duration_ms", 500)}ms'
        bg, fg = (50, 30, 0), (255, 180, 50)
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


# =========================================================================== #
# Utilities
# =========================================================================== #

def _fmt_action_short(rec: dict) -> str:
    """One-line summary of a trace action record."""
    action = rec.get('action', '?')
    params = rec.get('params', {})
    if action == 'tap':
        return f'tap ({params.get("x", 0)}, {params.get("y", 0)})'
    if action == 'click':
        btn = params.get('button', 'left')
        btn_sym = {
            'left': '\u2190', 'right': '\u2192',
            'middle': '\u2194',
        }.get(btn, btn)
        return f'click {btn_sym} ({params.get("x", 0)}, {params.get("y", 0)})'
    if action == 'type':
        t = params.get('text', '')
        if len(t) > 24:
            t = t[:21] + '\u2026'
        return f'type {repr(t)}'
    if action == 'key':
        return f'key [{params.get("key", "?").upper()}]'
    if action == 'hotkey':
        return f'hotkey [{params.get("keys", "?").upper()}]'
    if action == 'scroll':
        direction = '\u2191' if params.get('clicks', 0) > 0 else '\u2193'
        return f'scroll {direction}{abs(params.get("clicks", 1))}'
    if action == 'move':
        return f'move ({params.get("x", 0)}, {params.get("y", 0)})'
    if action == 'swipe':
        return (
            f'swipe ({params.get("x1", 0)},{params.get("y1", 0)})'
            f'\u2192({params.get("x2", 0)},{params.get("y2", 0)})'
        )
    if action == 'long_press':
        return f'long press ({params.get("x", 0)}, {params.get("y", 0)})'
    if action == 'screenshot':
        return 'screenshot'
    return action


def _crop_even(img: Image.Image) -> Image.Image:
    w, h = img.size
    ew, eh = w - w % 2, h - h % 2
    return img.crop((0, 0, ew, eh)) if (ew, eh) != (w, h) else img


def _total_size(path: Path) -> int:
    """Total bytes of *path* (file) or all mp4s inside (directory)."""
    if path.is_dir():
        return sum(f.stat().st_size for f in path.glob('*.mp4') if f.is_file())
    return path.stat().st_size if path.exists() else 0


def _fmt_size(b: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if b < 1024:
            return f'{b:.1f} {unit}'
        b //= 1024  # type: ignore[assignment]
    return f'{b:.1f} GB'


def _estimate_output_duration(
    source_duration: float,
    active_intervals: list[tuple[float, float]],
    idle_seconds: float,
) -> float:
    """Rough estimate of annotated video duration (excluding splash)."""
    active_s = sum(e - s for s, e in active_intervals)
    # gaps between + before + after
    idle_gaps = max(0, len(active_intervals) + 1)
    return active_s + idle_gaps * idle_seconds


def _fmt_duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hh = int(seconds // 3600)
    mm = int((seconds % 3600) // 60)
    ss = seconds % 60
    if hh:
        return f'{hh}:{mm:02d}:{ss:05.2f}'
    return f'{mm:02d}:{ss:05.2f}'


def _load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
        '/System/Library/Fonts/Helvetica.ttc',
        '/System/Library/Fonts/SFNSDisplay.ttf',
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
