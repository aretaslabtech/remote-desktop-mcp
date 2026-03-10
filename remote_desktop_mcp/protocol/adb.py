import subprocess
from typing import ClassVar

import structlog

from .base import GUISession
from .base import Key
from .base import MouseButton

logger = structlog.get_logger()

# Mapping of our Key enum to Android Keycodes
# Reference: https://developer.android.com/reference/android/view/KeyEvent
KEY_MAP = {
    Key.ENTER: '66',
    Key.BACKSPACE: '67',
    Key.DELETE: '112',
    Key.TAB: '61',
    Key.SPACE: '62',
    Key.ESC: '111',
    Key.UP: '19',
    Key.DOWN: '20',
    Key.LEFT: '21',
    Key.RIGHT: '22',
    Key.HOME: '3',
    Key.END: '123',
    Key.PAGEUP: '92',
    Key.PAGEDOWN: '93',
    Key.INSERT: '124',
    Key.F1: '131',
    Key.F2: '132',
    Key.F3: '133',
    Key.F4: '134',
    Key.F5: '135',
    Key.F6: '136',
    Key.F7: '137',
    Key.F8: '138',
    Key.F9: '139',
    Key.F10: '140',
    Key.F11: '141',
    Key.F12: '142',
    Key.SHIFT: '59',
    Key.CTRL: '113',
    Key.ALT: '57',
    Key.CMD: '117',
    Key.WIN: '117',
    Key.OPTION: '57',
    Key.CAPSLOCK: '115',
    Key.NUMLOCK: '143',
    Key.SCROLLLOCK: '116',
    Key.PRINTSCREEN: '120',
    Key.VOLUMEUP: '24',
    Key.VOLUMEDOWN: '25',
    Key.VOLUMEMUTE: '164',
}


class ADBSession(GUISession):
    protocol: ClassVar[str] = 'adb'

    serial: str | None

    def __init__(self, serial: str | None = None) -> None:
        self.serial = serial
        self.adb_base = ['adb']
        if serial:
            self.adb_base.extend(['-s', serial])

    def _run_adb(self, args: list[str], capture_output: bool = False) -> subprocess.CompletedProcess:
        cmd = self.adb_base + args
        return subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=capture_output,
            check=True,
            text=True if capture_output else False,
        )

    def start(self) -> None:
        logger.info(
            'checking_adb_connection',
            protocol='adb', serial=self.serial,
        )
        try:
            # Check if device is connected and responsive
            res = self._run_adb(
                ['shell', 'getprop', 'ro.product.model'], capture_output=True,
            )
            model = res.stdout.strip()
            logger.info('adb_device_connected', model=model)
        except subprocess.CalledProcessError as e:
            logger.error('adb_connection_failed', error=str(e))
            raise RuntimeError(f"Failed to connect to ADB device: {e}")

    def stop(self) -> None:
        logger.info('adb_session_stopped', protocol='adb')

    def take_screenshot(self, output_path: str) -> None:
        logger.info('screenshot', protocol='adb', path=output_path)
        # Using exec-out to pipe binary data directly to local file
        with open(output_path, 'wb') as f:
            subprocess.run(
                self.adb_base + ['exec-out', 'screencap', '-p'],
                stdin=subprocess.DEVNULL,
                stdout=f,
                check=True,
            )

    def click(self, x: int, y: int, button: MouseButton = MouseButton.LEFT) -> None:
        logger.info('click', protocol='adb', x=x, y=y, button=button.value)
        # ADB 'input tap' doesn't distinguish between left/right/middle buttons natively
        self._run_adb(['shell', 'input', 'tap', str(x), str(y)])

    def move(self, x: int, y: int) -> None:
        logger.info('move', protocol='adb', x=x, y=y)
        # Moving without clicking is tricky via basic 'input' command.
        # We can use 'input mouse move' but it might not be supported on all versions.
        # For compatibility, we do nothing or use a very fast swipe to self.

    def scroll(self, clicks: int) -> None:
        logger.info('scroll', protocol='adb', clicks=clicks)
        # Simulate scroll with swipe. Positive clicks = scroll up (swipe down).
        # We assume a standard screen size for the swipe center.
        # This is a heuristic.
        duration = 300
        if clicks > 0:
            # Scroll up (Swipe down)
            self._run_adb([
                'shell', 'input', 'swipe', '500',
                '400', '500', '800', str(duration),
            ])
        else:
            # Scroll down (Swipe up)
            self._run_adb([
                'shell', 'input', 'swipe', '500',
                '800', '500', '400', str(duration),
            ])

    def type_text(self, text: str) -> None:
        logger.info('type_text', protocol='adb', text=text)
        # ADB input text requires spaces to be %s
        safe_text = text.replace(' ', '%s')
        # We might also need to escape other shell characters if they are complex.
        self._run_adb(['shell', 'input', 'text', f'"{safe_text}"'])

    def key_event(self, key: Key) -> None:
        logger.info('key_event', protocol='adb', key=key.value)
        keycode = KEY_MAP.get(key)
        if keycode:
            self._run_adb(['shell', 'input', 'keyevent', keycode])
        else:
            logger.warning('unsupported_key', key=key.value)

    def hotkey(self, *keys: str) -> None:
        logger.info('hotkey', protocol='adb', keys=list(keys))
        # ADB doesn't easily support simultaneous key presses via simple shell commands.
        # We will try to send them sequentially, but it likely won't work as a real hotkey.
        for k in keys:
            try:
                # Try to map string to Key enum then to keycode
                key_enum = Key(k.lower())
                self.key_event(key_enum)
            except ValueError:
                # If it's a single char, we can try to type it or look up its keycode
                self._run_adb(['shell', 'input', 'keyevent', k.upper()])
