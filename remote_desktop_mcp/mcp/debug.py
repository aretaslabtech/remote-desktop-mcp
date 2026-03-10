import json
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
    def __init__(self, log_dir: str = 'debug_logs') -> None:
        self.log_root = Path(log_dir)
        self.session_id = time.strftime('%Y%m%d_%H%M%S')
        self.session_dir = self.log_root / self.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.step_count = 0
        logger.info(
            'debug_logger_initialized',
            session_dir=str(self.session_dir),
        )

    def _get_next_step_dir(self, action_type: ActionType) -> Path:
        self.step_count += 1
        step_name = f"step_{self.step_count:03d}_{action_type.value}"
        step_dir = self.session_dir / step_name
        step_dir.mkdir(parents=True, exist_ok=True)
        return step_dir

    def log_step(self, action_type: ActionType, params: dict, session, before: bool = True):
        """Log a single step with screenshots and metadata."""
        step_dir = self._get_next_step_dir(action_type)

        # 1. Metadata
        metadata = {
            'timestamp': time.time(),
            'action': action_type.value,
            'params': params,
            'step': self.step_count,
        }
        with open(step_dir / 'metadata.json', 'w') as f:
            json.dump(metadata, f, indent=2)

        # 2. Before screenshot
        before_path = step_dir / 'before.png'
        session.take_screenshot(str(before_path))

        # 3. If it's a click, mark the location on a copy of the 'before' image
        if action_type == ActionType.CLICK and 'x' in params and 'y' in params:
            self._mark_click(
                before_path, params['x'], params['y'], params.get(
                    'button', 'left',
                ), step_dir / 'action_marked.png',
            )

        return step_dir

    def log_after(self, step_dir: Path, session):
        """Take an 'after' screenshot for a step."""
        after_path = step_dir / 'after.png'
        session.take_screenshot(str(after_path))

    def _mark_click(self, img_path: Path, x: int, y: int, button: str, output_path: Path):
        try:
            with Image.open(img_path) as img:
                draw = ImageDraw.Draw(img)
                color = 'red' if button == 'left' else 'blue' if button == 'right' else 'green'
                radius = 10
                # Draw a circle at the click location
                draw.ellipse(
                    (
                        x - radius, y - radius, x + radius,
                        y + radius,
                    ), outline=color, width=3,
                )
                # Draw a crosshair
                draw.line(
                    (x - radius * 2, y, x + radius * 2, y),
                    fill=color, width=2,
                )
                draw.line(
                    (x, y - radius * 2, x, y + radius * 2),
                    fill=color, width=2,
                )
                img.save(output_path)
        except Exception as e:
            logger.error(
                'failed_to_mark_click',
                error=str(e), path=str(img_path),
            )


# Global debug logger instance (lazy initialization)
_debug_logger: DebugLogger | None = None


def get_debug_logger() -> DebugLogger:
    global _debug_logger
    if _debug_logger is None:
        _debug_logger = DebugLogger()
    return _debug_logger
