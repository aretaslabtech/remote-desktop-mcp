from typing import Optional
from typing import TYPE_CHECKING

import structlog

from .base import DesktopSession
from .base import Key
from .base import MouseButton

if TYPE_CHECKING:
    from vncdotool.client import VNCDoToolClient  # type: ignore

logger = structlog.get_logger()

# Mapping of our Key enum to vncdotool key names
# Reference: vncdotool/client.py KEYMAP
KEY_MAP = {
    Key.ENTER: 'enter',
    Key.BACKSPACE: 'backspace',
    Key.DELETE: 'delete',
    Key.TAB: 'tab',
    Key.SPACE: 'space',
    Key.ESC: 'esc',
    Key.UP: 'up',
    Key.DOWN: 'down',
    Key.LEFT: 'left',
    Key.RIGHT: 'right',
    Key.HOME: 'home',
    Key.END: 'end',
    Key.PAGEUP: 'pgup',
    Key.PAGEDOWN: 'pgdn',
    Key.INSERT: 'ins',
    Key.F1: 'f1',
    Key.F2: 'f2',
    Key.F3: 'f3',
    Key.F4: 'f4',
    Key.F5: 'f5',
    Key.F6: 'f6',
    Key.F7: 'f7',
    Key.F8: 'f8',
    Key.F9: 'f9',
    Key.F10: 'f10',
    Key.F11: 'f11',
    Key.F12: 'f12',
    Key.SHIFT: 'shift',
    Key.CTRL: 'ctrl',
    Key.ALT: 'alt',
    Key.CMD: 'meta',
    Key.WIN: 'super',
    Key.OPTION: 'alt',
    Key.CAPSLOCK: 'caplk',
    Key.NUMLOCK: 'numlk',
    Key.SCROLLLOCK: 'scrlk',
    Key.PRINTSCREEN: 'print',
    Key.VOLUMEUP: 'volumeup',
    Key.VOLUMEDOWN: 'volumedown',
    Key.VOLUMEMUTE: 'volumemute',
}


class VNCSession(DesktopSession):
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
            vnc_key = KEY_MAP.get(key, key.value)
            self.client.keyPress(vnc_key)

    def hotkey(self, *keys: str) -> None:
        logger.info('hotkey', protocol='vnc', keys=list(keys))
        if self.client:
            mapped_keys = []
            for k in keys:
                # Try to find if this string matches a Key enum value
                try:
                    key_enum = Key(k.lower())
                    mapped_keys.append(KEY_MAP.get(key_enum, k))
                except ValueError:
                    mapped_keys.append(k)

            for k in mapped_keys:
                self.client.keyDown(k)
            for k in reversed(mapped_keys):
                self.client.keyUp(k)

    def get_screen_size(self) -> tuple[int, int]:
        if not self.client:
            return 0, 0
        return self.client.screen.width, self.client.screen.height
