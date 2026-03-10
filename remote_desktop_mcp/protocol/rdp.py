import os
import subprocess
import time

import structlog
from mss import mss

from .base import GUISession
from .base import Key
from .base import MouseButton

logger = structlog.get_logger()


class RDPSession(GUISession):
    host: str
    user: str
    password: str
    display_num: str
    resolution: str
    xvfb_proc: subprocess.Popen[bytes] | None
    rdp_proc: subprocess.Popen[bytes] | None

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        display_num: str = ':99',
        resolution: str = '1280x720',
    ) -> None:
        self.host = host
        self.user = user
        self.password = password
        self.display_num = display_num
        self.resolution = resolution
        self.xvfb_proc = None
        self.rdp_proc = None

    def _set_display_env(self) -> None:
        os.environ['DISPLAY'] = self.display_num

    def start(self) -> None:
        logger.info('starting_xvfb', protocol='rdp', display=self.display_num)
        xvfb_cmd: list[str] = [
            'Xvfb', self.display_num,
            '-screen', '0', f"{self.resolution}x24",
        ]
        self.xvfb_proc = subprocess.Popen(
            xvfb_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1)

        logger.info('starting_xfreerdp', protocol='rdp', host=self.host)
        self._set_display_env()
        rdp_cmd: list[str] = [
            'xfreerdp',
            f"/v:{self.host}",
            f"/u:{self.user}",
            f"/p:{self.password}",
            f"/size:{self.resolution}",
            '/cert:ignore',
            '/bpp:24',
            '+clipboard',
        ]
        self.rdp_proc = subprocess.Popen(
            rdp_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(8)

    def stop(self) -> None:
        logger.info('stopping_processes', protocol='rdp')
        if self.rdp_proc:
            self.rdp_proc.terminate()
        if self.xvfb_proc:
            self.xvfb_proc.terminate()

    def take_screenshot(self, output_path: str) -> None:
        logger.info('screenshot', protocol='rdp', path=output_path)
        with mss(display=self.display_num) as sct:
            sct.shot(output=output_path)

    def click(self, x: int, y: int, button: MouseButton = MouseButton.LEFT) -> None:
        logger.info('click', protocol='rdp', x=x, y=y, button=button.value)
        self._set_display_env()
        import pyautogui
        pyautogui.click(x=x, y=y, button=button.value)

    def move(self, x: int, y: int) -> None:
        logger.info('move', protocol='rdp', x=x, y=y)
        self._set_display_env()
        import pyautogui
        pyautogui.moveTo(x, y)

    def scroll(self, clicks: int) -> None:
        logger.info('scroll', protocol='rdp', clicks=clicks)
        self._set_display_env()
        import pyautogui
        pyautogui.scroll(clicks)

    def type_text(self, text: str) -> None:
        logger.info('type_text', protocol='rdp', text=text)
        self._set_display_env()
        import pyautogui
        pyautogui.write(text)

    def key_event(self, key: Key) -> None:
        logger.info('key_event', protocol='rdp', key=key.value)
        self._set_display_env()
        import pyautogui
        pyautogui.press(key.value)
