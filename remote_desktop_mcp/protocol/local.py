import os

import structlog
from mss import mss

from .base import GUISession
from .base import Key
from .base import MouseButton

logger = structlog.get_logger()


class LocalSession(GUISession):
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

    def click(self, x: int, y: int, button: MouseButton = MouseButton.LEFT) -> None:
        logger.info('click', protocol='local', x=x, y=y, button=button.value)
        self._set_display_env()
        import pyautogui
        pyautogui.click(x=x, y=y, button=button.value)

    def move(self, x: int, y: int) -> None:
        logger.info('move', protocol='local', x=x, y=y)
        self._set_display_env()
        import pyautogui
        pyautogui.moveTo(x, y)

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
