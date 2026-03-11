from typing import ClassVar

import structlog
from playwright.sync_api import Browser
from playwright.sync_api import BrowserContext
from playwright.sync_api import Page
from playwright.sync_api import Playwright
from playwright.sync_api import sync_playwright

from .base import GUISession
from .base import Key
from .base import MouseButton

logger = structlog.get_logger()

KEY_MAP = {
    Key.ENTER: 'Enter',
    Key.BACKSPACE: 'Backspace',
    Key.DELETE: 'Delete',
    Key.TAB: 'Tab',
    Key.SPACE: 'Space',
    Key.ESC: 'Escape',
    Key.UP: 'ArrowUp',
    Key.DOWN: 'ArrowDown',
    Key.LEFT: 'ArrowLeft',
    Key.RIGHT: 'ArrowRight',
    Key.HOME: 'Home',
    Key.END: 'End',
    Key.PAGEUP: 'PageUp',
    Key.PAGEDOWN: 'PageDown',
    Key.INSERT: 'Insert',
    Key.F1: 'F1',
    Key.F2: 'F2',
    Key.F3: 'F3',
    Key.F4: 'F4',
    Key.F5: 'F5',
    Key.F6: 'F6',
    Key.F7: 'F7',
    Key.F8: 'F8',
    Key.F9: 'F9',
    Key.F10: 'F10',
    Key.F11: 'F11',
    Key.F12: 'F12',
    Key.SHIFT: 'Shift',
    Key.CTRL: 'Control',
    Key.ALT: 'Alt',
    Key.CMD: 'Meta',
    Key.WIN: 'Meta',
    Key.OPTION: 'Alt',
    Key.CAPSLOCK: 'CapsLock',
    Key.NUMLOCK: 'NumLock',
    Key.SCROLLLOCK: 'ScrollLock',
    Key.PRINTSCREEN: 'PrintScreen',
}


class PlaywrightSession(GUISession):
    protocol: ClassVar[str] = 'playwright'

    def __init__(
        self,
        url: str = 'https://www.google.com',
        resolution: str = '1280x720',
        headless: bool = False,
        user_data_dir: str | None = None,
    ) -> None:
        self.url = url
        res_parts = resolution.split('x')
        self.width = int(res_parts[0])
        self.height = int(res_parts[1])
        self.headless = headless
        self.user_data_dir = user_data_dir

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def start(self) -> None:
        logger.info(
            'starting_playwright_session',
            protocol='playwright', url=self.url,
        )
        self._playwright = sync_playwright().start()

        browser_args = [
            '--disable-blink-features=AutomationControlled',
        ]

        if self.user_data_dir:
            self._context = self._playwright.chromium.launch_persistent_context(
                self.user_data_dir,
                headless=self.headless,
                args=browser_args,
                viewport={'width': self.width, 'height': self.height},
            )
            self._browser = self._context.browser
        else:
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=browser_args,
            )
            self._context = self._browser.new_context(
                viewport={'width': self.width, 'height': self.height},
            )

        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = self._context.new_page()

        self._page.goto(self.url)
        self._page.wait_for_load_state('networkidle')

    def stop(self) -> None:
        logger.info('stopping_playwright_session', protocol='playwright')
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def take_screenshot(self, output_path: str) -> None:
        logger.info('screenshot', protocol='playwright', path=output_path)
        if self._page:
            self._page.screenshot(path=output_path)

    def click(self, x: int, y: int, button: MouseButton = MouseButton.LEFT) -> None:
        logger.info(
            'click', protocol='playwright',
            x=x, y=y, button=button.value,
        )
        if self._page:
            self._page.mouse.click(x, y, button=button.value)

    def move(self, x: int, y: int) -> None:
        logger.info('move', protocol='playwright', x=x, y=y)
        if self._page:
            self._page.mouse.move(x, y)

    def scroll(self, clicks: int) -> None:
        logger.info('scroll', protocol='playwright', clicks=clicks)
        # Playwright's mouse.wheel(delta_x, delta_y)
        # clicks > 0 is scroll up, so delta_y should be negative?
        # Actually in many APIs, positive delta_y is scroll down.
        # base.py says: "Positive for up, negative for down."
        # Playwright mouse.wheel(delta_x, delta_y): delta_y is vertical scroll amount.
        # Usually scrolling "up" means delta_y is negative in browser terms (moving the view up).
        # Let's check playwright docs or assume a factor.
        if self._page:
            self._page.mouse.wheel(0, -clicks * 100)

    def type_text(self, text: str) -> None:
        logger.info('type_text', protocol='playwright', text=text)
        if self._page:
            self._page.keyboard.type(text)

    def key_event(self, key: Key) -> None:
        logger.info('key_event', protocol='playwright', key=key.value)
        if self._page:
            pw_key = KEY_MAP.get(key)
            if pw_key:
                self._page.keyboard.press(pw_key)
            else:
                logger.warning('unsupported_key', key=key.value)

    def hotkey(self, *keys: str) -> None:
        logger.info('hotkey', protocol='playwright', keys=list(keys))
        if self._page:
            # Join keys with '+' for playwright keyboard.press
            # We need to map them first if they are in our Key enum (as strings)
            mapped_keys = []
            for k in keys:
                try:
                    key_enum = Key(k.lower())
                    mapped_keys.append(KEY_MAP.get(key_enum, k))
                except ValueError:
                    mapped_keys.append(k)

            self._page.keyboard.press('+'.join(mapped_keys))
