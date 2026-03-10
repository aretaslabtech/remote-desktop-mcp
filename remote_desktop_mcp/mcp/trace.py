"""JSONL action trace logger for MCP remote-desktop sessions.

Every agent action is written as a JSON line so that the full interaction
history can be replayed or post-processed by external tools (e.g. the
``annotate`` command that overlays the trace onto the raw screen recording).

Format::

    {"type": "session_start", "timestamp": 1741234567.123, "fps": 5}
    {"type": "action",        "timestamp": 1741234568.456,
     "action": "click", "params": {"x": 100, "y": 200, "button": "left"}}
    {"type": "action",        "timestamp": 1741234569.789,
     "action": "type",  "params": {"text": "hello"}}
    {"type": "session_end",   "timestamp": 1741234600.000}

The ``session_start.timestamp`` is the authoritative recording start time
used by the annotator to align trace events with video frames.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path


class TraceLogger:
    """Thread-safe JSONL trace writer."""

    def __init__(self, path: Path, fps: int = 5) -> None:
        self.path = path
        self.fps = fps
        self.start_time: float = time.time()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._file = open(path, 'w', encoding='utf-8')
        self._write({
            'type': 'session_start',
            'timestamp': self.start_time,
            'fps': fps,
        })

    def log_action(self, action_type: str, params: dict) -> None:
        """Record an agent action.  Thread-safe."""
        self._write({
            'type': 'action',
            'timestamp': time.time(),
            'action': action_type,
            'params': params,
        })

    def close(self) -> None:
        """Flush, write session_end, and close the file."""
        self._write({'type': 'session_end', 'timestamp': time.time()})
        with self._lock:
            self._file.close()

    # ----------------------------------------------------------------------- #

    def _write(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False) + '\n'
        with self._lock:
            self._file.write(line)
            self._file.flush()
