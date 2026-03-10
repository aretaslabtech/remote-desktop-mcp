"""Raw screen recorder for MCP remote-desktop sessions.

Captures the live screen as a continuous MP4 (or GIF) video with **no**
overlaid annotations.  All interaction metadata is written separately to a
JSONL trace file (see :mod:`remote_desktop_mcp.mcp.trace`).  Use the
``remote-desktop-mcp annotate`` command to combine the raw recording with the
trace file and produce an annotated replay video.

Usage::

    recorder = ScreenRecorder()
    recorder.start(session, output_path="recording.mp4", fps=5)
    # ... session runs ...
    path = recorder.stop()   # blocks until encoding is done
"""
from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from PIL import Image

from ..protocol.base import GUISession

logger = logging.getLogger(__name__)


class ScreenRecorder:
    """Captures the remote desktop as a raw, annotation-free MP4 video."""

    DEFAULT_FPS: int = 5

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._running = False
        self._session: GUISession | None = None
        self._fps: int = self.DEFAULT_FPS
        self._output_path: Path | None = None
        self.start_time: float = 0.0

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
        self._frame_paths = []
        self._frame_size = None
        self._tmp_dir = tempfile.TemporaryDirectory(prefix='mcp_rec_')
        self.start_time = time.time()

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(
            'screen_recording_started output=%s fps=%d',
            output_path, fps,
        )

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
    # Encoding + metadata sidecar
    # ----------------------------------------------------------------------- #

    def _encode(self) -> Path:
        if not self._frame_paths:
            raise ValueError('No frames were captured — nothing to encode.')

        assert self._output_path is not None
        output = self._output_path
        output.parent.mkdir(parents=True, exist_ok=True)

        # Write sidecar metadata so the annotator can align trace timestamps.
        meta_path = output.with_suffix('.meta.json')
        meta_path.write_text(
            json.dumps(
                {
                    'start_time': self.start_time,
                    'fps': self._fps,
                }, indent=2,
            ),
            encoding='utf-8',
        )

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
            meta_path.rename(gif_path.with_suffix('.meta.json'))
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

def _even(size: tuple[int, int]) -> tuple[int, int]:
    """Return nearest even (w, h) ≤ size (required by libx264)."""
    w, h = size
    return w - w % 2, h - h % 2
