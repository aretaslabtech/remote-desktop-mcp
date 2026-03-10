"""Continuous screen recorder for MCP remote-desktop sessions.

Records the remote desktop as a continuous video stream.  A background thread
captures screenshots at a configurable frame-rate and overlays transient
annotations that visually highlight each agent action:

- **Click** (left / right / middle): animated shrinking ripple circles.
- **Mouse move**: crosshair at the destination.
- **Type / key-press**: semi-transparent bottom banner with the text content.

Output: MP4 via ``imageio`` + ``imageio-ffmpeg`` (primary),
        animated GIF via ``Pillow`` (fallback when ffmpeg is unavailable).

Usage::

    recorder = ScreenRecorder()
    recorder.start(session, output_path="replay.mp4", fps=5)

    # Notify the recorder whenever an action is performed:
    recorder.notify_action("click", {"x": 300, "y": 200, "button": "left"})

    path = recorder.stop()   # blocks until the video is fully written
"""
from __future__ import annotations

import logging
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

from ..protocol.base import GUISession

logger = logging.getLogger(__name__)

# How long (seconds) each action annotation stays on screen before fading out.
_ANNOTATION_TTL: float = 1.5


# --------------------------------------------------------------------------- #
# Annotation data class
# --------------------------------------------------------------------------- #

class _Annotation:
    """A transient per-action overlay drawn on top of live video frames."""

    __slots__ = ('action_type', 'params', '_created', 'ttl')

    def __init__(self, action_type: str, params: dict, ttl: float = _ANNOTATION_TTL) -> None:
        self.action_type = action_type
        self.params = params
        self._created = time.monotonic()
        self.ttl = ttl

    @property
    def age(self) -> float:
        return time.monotonic() - self._created

    @property
    def alpha(self) -> float:
        """Normalised opacity [0, 1]; fades linearly over *ttl* seconds."""
        return max(0.0, 1.0 - self.age / self.ttl)

    @property
    def expired(self) -> bool:
        return self.age >= self.ttl


# --------------------------------------------------------------------------- #
# Main recorder
# --------------------------------------------------------------------------- #

class ScreenRecorder:
    """Continuously records the remote desktop as an annotated MP4 video.

    Call :meth:`start` to begin recording, :meth:`notify_action` whenever the
    agent performs an action, and :meth:`stop` when the session ends.
    """

    DEFAULT_FPS: int = 5

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._running = False
        self._session: GUISession | None = None
        self._fps: int = self.DEFAULT_FPS
        self._output_path: Path | None = None

        self._annotations: list[_Annotation] = []
        self._lock = threading.Lock()

        self._tmp_dir: tempfile.TemporaryDirectory[str] | None = None
        self._frame_paths: list[Path] = []
        self._frame_size: tuple[int, int] | None = None

    # ----------------------------------------------------------------------- #
    # Public API
    # ----------------------------------------------------------------------- #

    def start(
        self,
        session: GUISession,
        output_path: str = 'recording.mp4',
        fps: int = DEFAULT_FPS,
    ) -> None:
        """Start background screen recording."""
        if self._running:
            raise RuntimeError('ScreenRecorder is already running.')

        self._session = session
        self._output_path = Path(output_path)
        self._fps = fps
        self._running = True
        self._annotations = []
        self._frame_paths = []
        self._frame_size = None
        self._tmp_dir = tempfile.TemporaryDirectory(prefix='mcp_rec_')

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(
            'screen_recording_started output=%s fps=%d',
            output_path, fps,
        )

    def notify_action(self, action_type: str, params: dict) -> None:
        """Register an agent action so it is drawn as an annotation overlay.

        Safe to call from any thread; silently ignored if not recording.
        """
        if not self._running:
            return
        with self._lock:
            self._annotations.append(_Annotation(action_type, params))

    def stop(self) -> Path:
        """Stop recording, encode the video, and return the output path."""
        if not self._running:
            raise RuntimeError('ScreenRecorder is not running.')

        self._running = False
        if self._thread:
            self._thread.join(timeout=15)

        try:
            path = self._encode()
        finally:
            if self._tmp_dir:
                self._tmp_dir.cleanup()
                self._tmp_dir = None

        logger.info('screen_recording_saved path=%s', path)
        return path

    @property
    def is_running(self) -> bool:
        return self._running

    # ----------------------------------------------------------------------- #
    # Capture loop (background thread)
    # ----------------------------------------------------------------------- #

    def _capture_loop(self) -> None:
        interval = 1.0 / self._fps
        frame_num = 0

        while self._running:
            t0 = time.monotonic()
            try:
                assert self._tmp_dir is not None
                assert self._session is not None
                tmp_path = Path(self._tmp_dir.name) / \
                    f'frame_{frame_num:06d}.png'
                self._session.take_screenshot(str(tmp_path))

                img = Image.open(tmp_path).convert('RGB')
                img = self._annotate(img)

                if self._frame_size is None:
                    self._frame_size = _even(img.size)

                if img.size != self._frame_size:
                    img = img.resize(
                        self._frame_size,
                        Image.Resampling.LANCZOS,
                    )

                img.save(str(tmp_path))
                self._frame_paths.append(tmp_path)
                frame_num += 1

            except Exception as exc:
                logger.warning(
                    'capture_frame_failed frame=%d error=%s', frame_num, exc,
                )

            elapsed = time.monotonic() - t0
            remaining = interval - elapsed
            if remaining > 0:
                time.sleep(remaining)

    # ----------------------------------------------------------------------- #
    # Frame annotation
    # ----------------------------------------------------------------------- #

    def _annotate(self, img: Image.Image) -> Image.Image:
        with self._lock:
            self._annotations = [a for a in self._annotations if not a.expired]
            active = list(self._annotations)

        if not active:
            return img

        rgba = img.convert('RGBA')
        overlay = Image.new('RGBA', rgba.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        for ann in active:
            a = int(ann.alpha * 255)
            self._draw_overlay(draw, ann, a)

        img = Image.alpha_composite(rgba, overlay).convert('RGB')

        # Text banners are composited on top after alpha-blending
        for ann in active:
            if ann.action_type in ('type', 'key'):
                img = _draw_text_banner(img, ann)

        return img

    def _draw_overlay(
        self,
        draw: ImageDraw.ImageDraw,
        ann: _Annotation,
        alpha: int,
    ) -> None:
        p = ann.params
        if ann.action_type == 'click':
            x, y = p.get('x', 0), p.get('y', 0)
            button = p.get('button', 'left')
            if button == 'right':
                color = (50, 50, 255, alpha)
            elif button == 'middle':
                color = (50, 220, 50, alpha)
            else:
                color = (255, 50, 50, alpha)  # left click = red
            # Shrinking radius: large at first, shrinks as annotation ages
            r = max(6, int(36 * ann.alpha))
            draw.ellipse((x - r, y - r, x + r, y + r), outline=color, width=3)
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color)
            arm = r + 10
            draw.line((x - arm, y, x - r - 2, y), fill=color, width=2)
            draw.line((x + r + 2, y, x + arm, y), fill=color, width=2)
            draw.line((x, y - arm, x, y - r - 2), fill=color, width=2)
            draw.line((x, y + r + 2, x, y + arm), fill=color, width=2)

        elif ann.action_type == 'move':
            x, y = p.get('x', 0), p.get('y', 0)
            c = (255, 220, 50, alpha)
            r = 12
            draw.line((x - r, y, x + r, y), fill=c, width=2)
            draw.line((x, y - r, x, y + r), fill=c, width=2)
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=c)

    # ----------------------------------------------------------------------- #
    # Encoding
    # ----------------------------------------------------------------------- #

    def _encode(self) -> Path:
        if not self._frame_paths:
            raise ValueError('No frames were captured — nothing to encode.')

        assert self._output_path is not None
        output = self._output_path
        output.parent.mkdir(parents=True, exist_ok=True)

        try:
            import numpy as np
            import imageio  # type: ignore[import-untyped]

            writer: Any = imageio.get_writer(
                str(output),
                fps=self._fps,
                macro_block_size=None,
            )
            with writer:
                for fp in self._frame_paths:
                    if fp.exists():
                        img = Image.open(fp).convert('RGB')
                        w, h = img.size
                        ew, eh = w - w % 2, h - h % 2
                        if (ew, eh) != (w, h):
                            img = img.crop((0, 0, ew, eh))
                        writer.append_data(np.asarray(img))

            return output

        except Exception as exc:
            logger.warning(
                'mp4_encode_failed falling_back_to_gif error=%s', exc,
            )
            gif_path = output.with_suffix('.gif')
            frames = [
                Image.open(fp)
                for fp in self._frame_paths if fp.exists()
            ]
            if frames:
                duration_ms = max(100, 1000 // self._fps)
                frames[0].save(
                    str(gif_path),
                    format='GIF',
                    append_images=frames[1:],
                    save_all=True,
                    duration=duration_ms,
                    loop=0,
                    optimize=False,
                )
            return gif_path


# --------------------------------------------------------------------------- #
# Module-level helpers
# --------------------------------------------------------------------------- #

def _even(size: tuple[int, int]) -> tuple[int, int]:
    """Return nearest even (w, h) ≤ size (required by libx264)."""
    w, h = size
    return w - w % 2, h - h % 2


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


def _draw_text_banner(img: Image.Image, ann: _Annotation) -> Image.Image:
    """Draw a semi-transparent bottom banner for type / key-press events."""
    w, h = img.size
    banner_h = 42

    if ann.action_type == 'type':
        text = f'\u2328  Typing:  {repr(ann.params.get("text", ""))}'
        bg = (0, 50, 0)
        fg = (80, 255, 80)
    elif ann.action_type == 'key':
        text = f'\u2328  Key:  [ {ann.params.get("key", "").upper()} ]'
        bg = (0, 35, 55)
        fg = (80, 220, 255)
    else:
        return img

    if len(text) > 90:
        text = text[:87] + '...'

    a = int(ann.alpha * 200)
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
