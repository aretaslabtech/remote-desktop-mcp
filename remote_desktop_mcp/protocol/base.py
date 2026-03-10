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
    CMD = 'cmd'       # macOS Command / Windows key
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
    def click(self, x: int, y: int, button: MouseButton = MouseButton.LEFT) -> None:
        """Click at the specified coordinates."""

    @abstractmethod
    def move(self, x: int, y: int) -> None:
        """Move the mouse cursor to the specified coordinates."""

    @abstractmethod
    def scroll(self, clicks: int) -> None:
        """Scroll the mouse wheel. Positive for up, negative for down."""

    @abstractmethod
    def type_text(self, text: str) -> None:
        """Type the given text."""

    @abstractmethod
    def key_event(self, key: Key) -> None:
        """Send a keyboard event."""

    @abstractmethod
    def hotkey(self, *keys: str) -> None:
        """Press a combination of keys simultaneously (e.g. 'ctrl', 'c')."""
