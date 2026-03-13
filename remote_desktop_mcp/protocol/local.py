import os

import structlog
from mss import mss

from .base import DesktopSession
from .base import Key
from .base import MouseButton

logger = structlog.get_logger()


class LocalSession(DesktopSession):
    protocol = 'local'

    display_num: str | None

    def __init__(self, display_num: str | None = None) -> None:
        self.display_num = display_num

    def _set_display_env(self) -> None:
        if self.display_num:
            os.environ['DISPLAY'] = self.display_num
        elif 'DISPLAY' not in os.environ:
            os.environ['DISPLAY'] = ':0'

    def start(self) -> None:
        logger.info('local_session_ready', protocol='local')

    def stop(self) -> None:
        pass

    def take_screenshot(self, output_path: str) -> None:
        logger.info('screenshot', protocol='local', path=output_path)
        with mss(display=self.display_num) as sct:
            sct.shot(output=output_path)

    def _get_scale_factors(self) -> tuple[float, float]:
        """Calculate the scale factors between physical pixels and logical coordinates."""
        import pyautogui
        with mss(display=self.display_num) as sct:
            monitor = sct.monitors[1]
            phys_width = monitor['width']
            phys_height = monitor['height']

        self._set_display_env()
        log_width, log_height = pyautogui.size()

        scale_x = phys_width / log_width
        scale_y = phys_height / log_height
        return scale_x, scale_y

    def click(self, x: int, y: int, button: MouseButton = MouseButton.LEFT) -> None:
        scale_x, scale_y = self._get_scale_factors()
        lx, ly = round(x / scale_x), round(y / scale_y)

        logger.info(
            'click', protocol='local', x=x, y=y,
            logical_x=lx, logical_y=ly, button=button.value,
        )
        import pyautogui
        pyautogui.click(x=lx, y=ly, button=button.value)

    def move(self, x: int, y: int) -> None:
        scale_x, scale_y = self._get_scale_factors()
        lx, ly = round(x / scale_x), round(y / scale_y)

        logger.info(
            'move', protocol='local', x=x,
            y=y, logical_x=lx, logical_y=ly,
        )
        import pyautogui
        pyautogui.moveTo(lx, ly)

    def scroll(self, clicks: int) -> None:
        logger.info('scroll', protocol='local', clicks=clicks)
        self._set_display_env()
        import pyautogui
        pyautogui.scroll(clicks)

    def type_text(self, text: str) -> None:
        logger.info('type_text', protocol='local', text=text)
        self._set_display_env()
        import pyautogui
        pyautogui.write(text)

    def key_event(self, key: Key) -> None:
        logger.info('key_event', protocol='local', key=key.value)
        self._set_display_env()
        import pyautogui
        pyautogui.press(key.value)

    def hotkey(self, *keys: str) -> None:
        logger.info('hotkey', protocol='local', keys=list(keys))
        self._set_display_env()
        import pyautogui
        pyautogui.hotkey(*keys)

    def get_screen_size(self) -> tuple[int, int]:
        with mss(display=self.display_num) as sct:
            monitor = sct.monitors[1]
            return monitor['width'], monitor['height']
