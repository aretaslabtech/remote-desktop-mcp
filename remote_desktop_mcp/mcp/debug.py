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
    CLICK = 'click'
    MOVE = 'move'
    SCROLL = 'scroll'
    TYPE = 'type'
    KEY = 'key'
    SCREENSHOT = 'screenshot'


class DebugLogger:
    def __init__(self, protocol: str = 'unknown', log_dir: str = '.logs') -> None:
        self.log_root = Path(log_dir)
        self.sessions_dir = self.log_root / 'sessions'

        # Session name: 20231027_103005_local
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        self.session_id = f"{timestamp}_{protocol}"
        self.session_dir = self.sessions_dir / self.session_id

        self.session_dir.mkdir(parents=True, exist_ok=True)
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

        if action_type == ActionType.CLICK:
            suffix = f"_x{params.get('x')}_y{params.get('y')}_{params.get('button')}"
        elif action_type == ActionType.MOVE:
            suffix = f"_x{params.get('x')}_y{params.get('y')}"
        elif action_type == ActionType.TYPE:
            text = str(params.get('text', ''))[:15].replace(' ', '_')
            suffix = f"_{text}"
        elif action_type == ActionType.KEY:
            suffix = f"_{params.get('key')}"
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
        step_dir = self.session_dir / step_name
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

        # 3. Mark action
        if action_type == ActionType.CLICK and 'x' in params and 'y' in params:
            self._mark_click(
                before_path, params['x'], params['y'], params.get(
                    'button', 'left',
                ), step_dir / 'marked.png',
            )
        elif action_type == ActionType.MOVE and 'x' in params and 'y' in params:
            self._mark_move(
                before_path, params['x'], params['y'], step_dir / 'marked.png',
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
                color = 'red' if button == 'left' else 'blue' if button == 'right' else 'green'
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


# Singleton logic with protocol support
_debug_loggers: dict[str, DebugLogger] = {}


def get_debug_logger(protocol: str = 'unknown') -> DebugLogger:
    if protocol not in _debug_loggers:
        _debug_loggers[protocol] = DebugLogger(protocol=protocol)
    return _debug_loggers[protocol]
