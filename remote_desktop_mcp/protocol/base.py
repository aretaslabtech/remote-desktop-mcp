from abc import ABC
from abc import abstractmethod
from enum import Enum


class MouseButton(Enum):
    LEFT = 'left'
    MIDDLE = 'middle'
    RIGHT = 'right'


class Key(Enum):
    ENTER = 'enter'
    BACKSPACE = 'backspace'
    TAB = 'tab'
    SPACE = 'space'
    ESC = 'esc'
    UP = 'up'
    DOWN = 'down'
    LEFT = 'left'
    RIGHT = 'right'


class GUISession(ABC):
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
