from abc import ABC
from abc import abstractmethod
from enum import Enum
from typing import ClassVar


class MouseButton(Enum):
    LEFT = 'left'
    MIDDLE = 'middle'
    RIGHT = 'right'


class Key(Enum):
    # Navigation
    ENTER = 'enter'
    BACKSPACE = 'backspace'
    DELETE = 'delete'
    TAB = 'tab'
    SPACE = 'space'
    ESC = 'esc'
    UP = 'up'
    DOWN = 'down'
    LEFT = 'left'
    RIGHT = 'right'
    HOME = 'home'
    END = 'end'
    PAGEUP = 'pageup'
    PAGEDOWN = 'pagedown'
    INSERT = 'insert'
    # Function keys
    F1 = 'f1'
    F2 = 'f2'
    F3 = 'f3'
    F4 = 'f4'
    F5 = 'f5'
    F6 = 'f6'
    F7 = 'f7'
    F8 = 'f8'
    F9 = 'f9'
    F10 = 'f10'
    F11 = 'f11'
    F12 = 'f12'
    # Modifiers (for single-key press; combos go through press_hotkey)
    SHIFT = 'shift'
    CTRL = 'ctrl'
    ALT = 'alt'
    CMD = 'win'       # macOS Command / Windows key
    WIN = 'win'       # Windows key alias
    OPTION = 'option'  # macOS Option alias
    # Media / system
    CAPSLOCK = 'capslock'
    NUMLOCK = 'numlock'
    SCROLLLOCK = 'scrolllock'
    PRINTSCREEN = 'printscreen'
    VOLUMEUP = 'volumeup'
    VOLUMEDOWN = 'volumedown'
    VOLUMEMUTE = 'volumemute'


class GUISession(ABC):
    """Base class for all GUI automation sessions (desktop and mobile)."""

    protocol: ClassVar[str]

    @abstractmethod
    def start(self) -> None:
        """Start the session."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the session and cleanup resources."""

    @abstractmethod
    def take_screenshot(self, output_path: str) -> None:
        """Capture a screenshot and save it to the specified path."""

    @abstractmethod
    def tap(self, x: int, y: int) -> None:
        """Tap at coordinates.  Desktop: left-click.  Mobile: touch."""

    @abstractmethod
    def type_text(self, text: str) -> None:
        """Type the given text."""

    @abstractmethod
    def key_event(self, key: Key) -> None:
        """Send a keyboard event."""

    @abstractmethod
    def get_screen_size(self) -> tuple[int, int]:
        """Get the current screen resolution (width, height)."""


class DesktopSession(GUISession):
    """Session for desktop environments (mouse + keyboard).

    Subclassed by Local, RDP, VNC, and Playwright backends.
    """

    #: Whether this backend supports reading/writing the remote clipboard.
    #: Defaults to False so backends with no equivalent support (VNC, ADB,
    #: Playwright, Local) need no changes; only backends that implement
    #: ``read_clipboard``/``write_clipboard`` override this to True.
    supports_clipboard: ClassVar[bool] = False

    def tap(self, x: int, y: int) -> None:
        """Tap = left-click on desktop."""
        self.click(x, y)

    @abstractmethod
    def click(self, x: int, y: int, button: MouseButton = MouseButton.LEFT) -> None:
        """Click at the specified coordinates with a given mouse button."""

    @abstractmethod
    def move(self, x: int, y: int) -> None:
        """Move the mouse cursor to the specified coordinates."""

    @abstractmethod
    def scroll(self, clicks: int) -> None:
        """Scroll the mouse wheel. Positive for up, negative for down."""

    @abstractmethod
    def hotkey(self, *keys: str) -> None:
        """Press a combination of keys simultaneously (e.g. 'ctrl', 'c')."""


class MobileSession(GUISession):
    """Session for mobile / touch-screen environments.

    Subclassed by the ADB backend.
    """

    @abstractmethod
    def swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300,
    ) -> None:
        """Swipe from (x1, y1) to (x2, y2) over *duration_ms* milliseconds."""

    @abstractmethod
    def long_press(self, x: int, y: int, duration_ms: int = 500) -> None:
        """Long-press at the specified coordinates."""
