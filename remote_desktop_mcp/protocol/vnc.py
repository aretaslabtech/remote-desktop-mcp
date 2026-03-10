from typing import Optional
from typing import TYPE_CHECKING

import structlog

from .base import GUISession
from .base import Key
from .base import MouseButton

if TYPE_CHECKING:
    from vncdotool.client import VNCDoToolClient  # type: ignore

logger = structlog.get_logger()


class VNCSession(GUISession):
    protocol = 'vnc'

    host: str
    password: str | None
    client: Optional['VNCDoToolClient']

    def __init__(self, host: str, password: str | None = None) -> None:
        self.host = host
        self.password = password
        self.client = None

    def start(self) -> None:
        from vncdotool import api  # type: ignore
        logger.info('connecting_to_vnc', protocol='vnc', host=self.host)
        self.client = api.connect(self.host, password=self.password)

    def stop(self) -> None:
        logger.info('disconnecting_vnc', protocol='vnc')
        if self.client:
            self.client.disconnect()

    def take_screenshot(self, output_path: str) -> None:
        logger.info('screenshot', protocol='vnc', path=output_path)
        if self.client:
            self.client.captureScreen(output_path)

    def click(self, x: int, y: int, button: MouseButton = MouseButton.LEFT) -> None:
        logger.info('click', protocol='vnc', x=x, y=y, button=button.value)
        btn_map: dict[MouseButton, int] = {
            MouseButton.LEFT: 1,
            MouseButton.MIDDLE: 2,
            MouseButton.RIGHT: 3,
        }
        if self.client:
            self.client.mouseMove(x, y)
            self.client.mousePress(btn_map[button])

    def move(self, x: int, y: int) -> None:
        logger.info('move', protocol='vnc', x=x, y=y)
        if self.client:
            self.client.mouseMove(x, y)

    def scroll(self, clicks: int) -> None:
        logger.info('scroll', protocol='vnc', clicks=clicks)
        button: int = 4 if clicks > 0 else 5
        if self.client:
            for _ in range(abs(clicks)):
                self.client.mousePress(button)

    def type_text(self, text: str) -> None:
        logger.info('type_text', protocol='vnc', text=text)
        if self.client:
            self.client.type(text)

    def key_event(self, key: Key) -> None:
        logger.info('key_event', protocol='vnc', key=key.value)
        if self.client:
            self.client.keyPress(key.value)

    def hotkey(self, *keys: str) -> None:
        logger.info('hotkey', protocol='vnc', keys=list(keys))
        if self.client:
            for k in keys:
                self.client.keyDown(k)
            for k in reversed(keys):
                self.client.keyUp(k)
