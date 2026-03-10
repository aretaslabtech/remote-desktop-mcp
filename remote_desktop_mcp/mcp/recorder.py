"""Raw screen recorder for MCP remote-desktop sessions.

Captures the live screen as a series of segmented MP4 files with **no**
overlaid annotations.  Frames are captured in a background thread; every
``segment_seconds`` (default 60 s) the accumulated frames are handed off to
a second background thread for encoding, so recording is never blocked by I/O.

Output layout::

    <output_dir>/
        recording_0000.mp4   recording_0000.meta.json
        recording_0001.mp4   recording_0001.meta.json
        ...

Each ``.meta.json`` sidecar contains ``{"start_time": <unix float>, "fps": N}``
so the ``remote-desktop-mcp annotate`` command can align trace timestamps.

Usage::

    recorder = ScreenRecorder()
    recorder.start(session, output_dir="recordings", fps=5, segment_seconds=60)
    # ... session runs ...
    out_dir = recorder.stop()   # waits for all pending encodes, returns Path
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
    """Captures the remote desktop as segmented, annotation-free MP4 files."""

    DEFAULT_FPS: int = 5
    DEFAULT_SEGMENT_SECONDS: int = 60

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._running = False
        self._session: GUISession | None = None
        self._fps: int = self.DEFAULT_FPS
        self._segment_seconds: int = self.DEFAULT_SEGMENT_SECONDS
        self._output_dir: Path | None = None
        self._stem: str = 'recording'
        self._suffix: str = '.mp4'
        self.start_time: float = 0.0

        self._tmp_dir: tempfile.TemporaryDirectory[str] | None = None
        self._frame_paths: list[Path] = []
        self._frame_size: tuple[int, int] | None = None
        self._segment_index: int = 0
        self._segment_start_time: float = 0.0
        self._encode_threads: list[threading.Thread] = []
        self._lock = threading.Lock()

    # ----------------------------------------------------------------------- #
    # Public API
    # ----------------------------------------------------------------------- #

    def start(
        self,
        session: GUISession,
        output_path: str = 'recording.mp4',
        fps: int = DEFAULT_FPS,
        segment_seconds: int = DEFAULT_SEGMENT_SECONDS,
    ) -> None:
        """Start background screen recording.

        Args:
            session: Active GUI session to capture.
            output_path: Template path such as ``recordings/recording.mp4``.
                Actual files will be ``recording_0000.mp4``, etc., placed in
                the same directory.
            fps: Capture frame-rate.
            segment_seconds: How many seconds of footage each segment holds
                before it is flushed to disk.  Lower values reduce data loss
                on abrupt exit at the cost of more files.
        """
        if self._running:
            raise RuntimeError('ScreenRecorder is already running.')

        p = Path(output_path)
        self._output_dir = p.parent
        self._stem = p.stem
        self._suffix = p.suffix or '.mp4'
        self._fps = fps
        self._segment_seconds = segment_seconds
        self._session = session
        self._running = True
        self._frame_paths = []
        self._frame_size = None
        self._segment_index = 0
        self._encode_threads = []
        self._tmp_dir = tempfile.TemporaryDirectory(prefix='mcp_rec_')
        self.start_time = time.time()
        self._segment_start_time = self.start_time

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(
            'screen_recording_started output_dir=%s fps=%d segment_seconds=%d',
            self._output_dir, fps, segment_seconds,
        )

    def stop(self) -> Path:
        """Stop recording, flush remaining frames, wait for encoding, return output dir."""
        if not self._running:
            raise RuntimeError('ScreenRecorder is not running.')

        self._running = False
        if self._thread:
            self._thread.join(timeout=15)

        # Flush whatever frames remain.
        self._flush_segment()

        # Wait for all segment encoding threads.
        for t in self._encode_threads:
            t.join(timeout=60)

        if self._tmp_dir:
            self._tmp_dir.cleanup()
            self._tmp_dir = None

        assert self._output_dir is not None
        logger.info('screen_recording_stopped output_dir=%s', self._output_dir)
        return self._output_dir

    @property
    def is_running(self) -> bool:
        return self._running

    # ----------------------------------------------------------------------- #
    # Capture loop (background thread)
    # ----------------------------------------------------------------------- #

    def _capture_loop(self) -> None:
        interval = 1.0 / self._fps
        frames_per_segment = self._fps * self._segment_seconds
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

                with self._lock:
                    self._frame_paths.append(tmp_path)
                    if len(self._frame_paths) >= frames_per_segment:
                        self._flush_segment_locked()

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
    # Segment flushing
    # ----------------------------------------------------------------------- #

    def _flush_segment(self) -> None:
        """Thread-safe wrapper — grabs the lock then flushes."""
        with self._lock:
            self._flush_segment_locked()

    def _flush_segment_locked(self) -> None:
        """Must be called with self._lock held."""
        if not self._frame_paths:
            return
        frames = self._frame_paths[:]
        self._frame_paths = []
        seg_start = self._segment_start_time
        self._segment_start_time += len(frames) / self._fps
        seg_idx = self._segment_index
        self._segment_index += 1

        t = threading.Thread(
            target=self._encode_segment,
            args=(frames, seg_idx, seg_start),
            daemon=True,
        )
        t.start()
        self._encode_threads.append(t)

    # ----------------------------------------------------------------------- #
    # Segment encoding (runs in its own thread per segment)
    # ----------------------------------------------------------------------- #

    def _encode_segment(
        self,
        frame_paths: list[Path],
        seg_idx: int,
        seg_start_time: float,
    ) -> None:
        assert self._output_dir is not None
        self._output_dir.mkdir(parents=True, exist_ok=True)
        output = self._output_dir / f'{self._stem}_{seg_idx:04d}{self._suffix}'

        meta_path = output.with_suffix('.meta.json')
        meta_path.write_text(
            json.dumps(
                {
                    'start_time': seg_start_time,
                    'fps': self._fps,
                }, indent=2,
            ),
            encoding='utf-8',
        )

        try:
            import imageio  # type: ignore[import-untyped]
            import numpy as np

            writer: Any = imageio.get_writer(
                str(output), fps=self._fps, macro_block_size=None,
            )
            with writer:
                for fp in frame_paths:
                    if fp.exists():
                        img = Image.open(fp).convert('RGB')
                        w, h = img.size
                        ew, eh = w - w % 2, h - h % 2
                        if (ew, eh) != (w, h):
                            img = img.crop((0, 0, ew, eh))
                        writer.append_data(np.asarray(img))
            logger.info('segment_saved seg=%d path=%s', seg_idx, output)

        except Exception as exc:
            logger.warning(
                'mp4_encode_failed seg=%d falling_back_to_gif error=%s', seg_idx, exc,
            )
            gif_path = output.with_suffix('.gif')
            meta_path.rename(gif_path.with_suffix('.meta.json'))
            frames_img = [Image.open(fp) for fp in frame_paths if fp.exists()]
            if frames_img:
                duration_ms = max(100, 1000 // self._fps)
                frames_img[0].save(
                    str(gif_path),
                    format='GIF',
                    append_images=frames_img[1:],
                    save_all=True,
                    duration=duration_ms,
                    loop=0,
                    optimize=False,
                )

        # Delete source frames after encoding to free tmp space.
        for fp in frame_paths:
            try:
                fp.unlink(missing_ok=True)
            except Exception:
                pass


# --------------------------------------------------------------------------- #

def _even(size: tuple[int, int]) -> tuple[int, int]:
    """Return nearest even (w, h) ≤ size (required by libx264)."""
    w, h = size
    return w - w % 2, h - h % 2
