import json
import os
import time
from enum import Enum
from pathlib import Path

import structlog
from PIL import Image
from PIL import ImageDraw

logger = structlog.get_logger()


class ActionType(Enum):
    # Common
    TAP = 'tap'
    TYPE = 'type'
    KEY = 'key'
    SCREENSHOT = 'screenshot'
    # Desktop
    CLICK = 'click'
    MOVE = 'move'
    SCROLL = 'scroll'
    HOTKEY = 'hotkey'
    # Mobile
    SWIPE = 'swipe'
    LONG_PRESS = 'long_press'


class DebugLogger:
    def __init__(self, protocol: str = 'unknown', log_dir: str = '.logs') -> None:
        self.log_root = Path(log_dir)
        self.sessions_dir = self.log_root / 'sessions'

        # Session name: 20231027_103005_local
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        self.session_id = f"{timestamp}_{protocol}"
        self.session_dir = self.sessions_dir / self.session_id

        # New structured layout
        self.steps_dir = self.session_dir / 'steps'
        self.recordings_dir = self.session_dir / 'recordings'

        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.steps_dir.mkdir(parents=True, exist_ok=True)
        self.recordings_dir.mkdir(parents=True, exist_ok=True)

        self.step_count = 0

        self._update_latest_link()
        logger.info('debug_logger_ready', session_dir=str(self.session_dir))

    def _update_latest_link(self):
        """Create a 'latest' symlink pointing to the current session."""
        latest_link = self.log_root / 'latest'
        try:
            if latest_link.exists() or latest_link.is_symlink():
                latest_link.unlink()
            # Use relative path for the symlink to be portable
            rel_path = os.path.relpath(self.session_dir, self.log_root)
            os.symlink(rel_path, latest_link)
        except Exception:
            # Fallback for systems that don't support symlinks (like some Windows configs)
            pass

    def _get_step_name(self, action_type: ActionType, params: dict) -> str:
        """Create a descriptive folder name for the step."""
        self.step_count += 1
        base = f"{self.step_count:03d}_{action_type.value}"

        if action_type in (ActionType.CLICK, ActionType.TAP):
            suffix = f"_x{params.get('x')}_y{params.get('y')}"
            if action_type == ActionType.CLICK:
                suffix += f"_{params.get('button', 'left')}"
        elif action_type in (ActionType.MOVE, ActionType.LONG_PRESS):
            suffix = f"_x{params.get('x')}_y{params.get('y')}"
        elif action_type == ActionType.SWIPE:
            suffix = (
                f"_x{params.get('x1')}_y{params.get('y1')}"
                f"_to_x{params.get('x2')}_y{params.get('y2')}"
            )
        elif action_type == ActionType.TYPE:
            text = str(params.get('text', ''))[:15].replace(' ', '_')
            suffix = f"_{text}"
        elif action_type in (ActionType.KEY, ActionType.HOTKEY):
            key_str = params.get('key', params.get('keys', ''))
            suffix = f"_{key_str}"
        elif action_type == ActionType.SCROLL:
            suffix = f"_{params.get('clicks')}"
        else:
            suffix = ''

        # Clean suffix from invalid filename chars
        suffix = ''.join([c for c in suffix if c.isalnum() or c in '_-'])
        return f"{base}{suffix}"

    def log_step(self, action_type: ActionType, params: dict, session):
        """Log a single step with screenshots and metadata."""
        step_name = self._get_step_name(action_type, params)
        step_dir = self.steps_dir / step_name
        step_dir.mkdir(parents=True, exist_ok=True)

        # 1. Metadata
        metadata = {
            'timestamp': time.time(),
            'action': action_type.value,
            'params': params,
            'step': self.step_count,
        }
        with open(step_dir / 'meta.json', 'w') as f:
            json.dump(metadata, f, indent=2)

        # 2. Before screenshot
        before_path = step_dir / 'before.png'
        try:
            session.take_screenshot(str(before_path))
        except Exception as e:
            logger.error('debug_screenshot_failed', error=str(e))

        # 3. Mark action on the screenshot
        ax = params.get('actual_x', params.get('x'))
        ay = params.get('actual_y', params.get('y'))
        ax1 = params.get('actual_x1', params.get('x1'))
        ay1 = params.get('actual_y1', params.get('y1'))
        ax2 = params.get('actual_x2', params.get('x2'))
        ay2 = params.get('actual_y2', params.get('y2'))

        if action_type in (ActionType.CLICK, ActionType.TAP) and ax is not None and ay is not None:
            self._mark_click(
                before_path, ax, ay, params.get(
                    'button', 'left',
                ), step_dir / 'marked.png',
            )
        elif action_type == ActionType.MOVE and ax is not None and ay is not None:
            self._mark_move(
                before_path, ax, ay, step_dir / 'marked.png',
            )
        elif action_type == ActionType.LONG_PRESS and ax is not None and ay is not None:
            self._mark_click(
                before_path, ax, ay, 'long_press',
                step_dir / 'marked.png',
            )
        elif action_type == ActionType.SWIPE and ax1 is not None and ay1 is not None and ax2 is not None and ay2 is not None:
            self._mark_swipe(
                before_path, ax1, ay1, ax2, ay2,
                step_dir / 'marked.png',
            )

        return step_dir

    def log_after(self, step_dir: Path, session):
        """Take an 'after' screenshot."""
        after_path = step_dir / 'after.png'
        try:
            session.take_screenshot(str(after_path))
        except Exception:
            pass

    def _mark_click(self, img_path: Path, x: int, y: int, button: str, output_path: Path):
        try:
            if not img_path.exists():
                return
            with Image.open(img_path) as img:
                draw = ImageDraw.Draw(img)
                color = {
                    'left': 'red',
                    'right': 'blue',
                    'middle': 'green',
                    'long_press': 'orange',
                }.get(button, 'red')
                r = 15
                # Outer circle
                draw.ellipse(
                    (x - r, y - r, x + r, y + r),
                    outline=color, width=4,
                )
                # Inner dot
                draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=color)
                # Crosshair
                draw.line(
                    (x - int(r * 1.5), y, x + int(r * 1.5), y),
                    fill=color, width=2,
                )
                draw.line(
                    (x, y - int(r * 1.5), x, y + int(r * 1.5)),
                    fill=color, width=2,
                )
                img.save(output_path)
        except Exception:
            pass

    def _mark_move(self, img_path: Path, x: int, y: int, output_path: Path):
        try:
            if not img_path.exists():
                return
            with Image.open(img_path) as img:
                draw = ImageDraw.Draw(img)
                color = 'yellow'
                r = 10
                # Just a crosshair for move
                draw.line((x - r, y, x + r, y), fill=color, width=2)
                draw.line((x, y - r, x, y + r), fill=color, width=2)
                img.save(output_path)
        except Exception:
            pass

    def _mark_swipe(
        self, img_path: Path,
        x1: int, y1: int, x2: int, y2: int,
        output_path: Path,
    ):
        try:
            if not img_path.exists():
                return
            with Image.open(img_path) as img:
                draw = ImageDraw.Draw(img)
                color = 'cyan'
                # Start dot
                draw.ellipse((x1 - 6, y1 - 6, x1 + 6, y1 + 6), fill=color)
                # Arrow line
                draw.line((x1, y1, x2, y2), fill=color, width=3)
                # End arrow head (simple triangle)
                draw.ellipse(
                    (x2 - 4, y2 - 4, x2 + 4, y2 + 4),
                    fill=color, outline='white',
                )
                img.save(output_path)
        except Exception:
            pass


# Singleton logic with protocol support
_debug_loggers: dict[str, DebugLogger] = {}


def get_debug_logger(protocol: str = 'unknown') -> DebugLogger:
    if protocol not in _debug_loggers:
        _debug_loggers[protocol] = DebugLogger(protocol=protocol)
    return _debug_loggers[protocol]
