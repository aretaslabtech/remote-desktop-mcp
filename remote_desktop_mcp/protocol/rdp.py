import os
import shutil
import subprocess
import time
from pathlib import Path

import structlog
from mss import mss

from .base import DesktopSession
from .base import Key
from .base import MouseButton

logger = structlog.get_logger()

_CLIPBOARD_BINARY = 'xclip'


class ClipboardError(RuntimeError):
    """Raised when the X11 clipboard backend cannot be used."""


class ClipboardBackend:
    """Reads/writes the X11 clipboard by shelling out to ``xclip``.

    Deliberately avoids a Python clipboard dependency: FreeRDP's
    ``+clipboard`` channel already syncs the X11 ``CLIPBOARD`` selection of
    whatever display it is pointed at with the Windows clipboard, so this
    class only needs to read/write that X11 selection on the Xvfb display
    owned by the RDP session. The ``DISPLAY`` value is always passed
    explicitly to the subprocess (never inherited from the ambient process
    environment), so it talks to the correct Xvfb display even if the
    MCP server process itself has a different (or no) ``DISPLAY`` set.
    """

    def __init__(self, display: str) -> None:
        self.display = display

    def _require_available(self) -> None:
        if shutil.which(_CLIPBOARD_BINARY) is None:
            raise ClipboardError(
                f"Clipboard backend '{_CLIPBOARD_BINARY}' is unavailable.",
            )

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env['DISPLAY'] = self.display
        return env

    def read_text(self) -> str:
        self._require_available()
        try:
            result = subprocess.run(
                [_CLIPBOARD_BINARY, '-selection', 'clipboard', '-o'],
                env=self._env(),
                capture_output=True,
                check=True,
            )
        except FileNotFoundError as exc:
            raise ClipboardError(
                f"Clipboard backend '{_CLIPBOARD_BINARY}' is unavailable.",
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise ClipboardError(
                f"Clipboard backend '{_CLIPBOARD_BINARY}' failed to read "
                'the clipboard.',
            ) from exc
        return result.stdout.decode('utf-8', errors='replace')

    def write_text(self, text: str) -> None:
        self._require_available()
        try:
            subprocess.run(
                [_CLIPBOARD_BINARY, '-selection', 'clipboard'],
                input=text.encode('utf-8'),
                env=self._env(),
                capture_output=True,
                check=True,
            )
        except FileNotFoundError as exc:
            raise ClipboardError(
                f"Clipboard backend '{_CLIPBOARD_BINARY}' is unavailable.",
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise ClipboardError(
                f"Clipboard backend '{_CLIPBOARD_BINARY}' failed to write "
                'to the clipboard.',
            ) from exc


def _validate_shared_dir(shared_dir: str) -> str:
    """Validate and resolve a path requested for RDP drive redirection.

    Expands ``~``, converts to an absolute path, resolves it, and ensures
    the path exists, is a directory, and is not one of the locations that
    must never be auto-shared over RDP (the filesystem root, the user's
    home directory, the current working directory, or ``/tmp``).
    """
    resolved = Path(shared_dir).expanduser().resolve()

    if not resolved.exists():
        raise ValueError(f"RDP shared directory does not exist: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"RDP shared directory is not a directory: {resolved}")

    forbidden = {
        Path('/').resolve(),
        Path.home().resolve(),
        Path.cwd().resolve(),
        Path('/tmp').resolve(),
    }
    if resolved in forbidden:
        raise ValueError(
            'RDP shared directory must not be the filesystem root, the '
            f"home directory, the current working directory, or /tmp: {resolved}",
        )

    return str(resolved)


class RDPSession(DesktopSession):
    protocol = 'rdp'
    supports_clipboard = True

    host: str
    user: str
    password: str
    display_num: str
    resolution: str
    shared_dir: str | None
    shared_name: str
    xvfb_proc: subprocess.Popen[bytes] | None
    rdp_proc: subprocess.Popen[bytes] | None

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        display_num: str = ':99',
        resolution: str = '1280x720',
        shared_dir: str | None = None,
        shared_name: str = 'shared',
    ) -> None:
        self.host = host
        self.user = user
        self.password = password
        self.display_num = display_num
        self.resolution = resolution
        self.shared_dir = (
            _validate_shared_dir(shared_dir) if shared_dir is not None else None
        )
        self.shared_name = shared_name
        self.xvfb_proc = None
        self.rdp_proc = None
        self._clipboard = ClipboardBackend(display=self.display_num)
        # Populated on start(); a missing clipboard binary must never abort
        # the RDP connection, so this stays None until start() runs the
        # startup availability check.
        self._clipboard_available: bool | None = None

    def _set_display_env(self) -> None:
        os.environ['DISPLAY'] = self.display_num

    def start(self) -> None:
        self._set_display_env()

        self._clipboard_available = shutil.which(_CLIPBOARD_BINARY) is not None
        if not self._clipboard_available:
            logger.info(
                'clipboard_unavailable', protocol='rdp',
                binary=_CLIPBOARD_BINARY,
            )

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
        rdp_cmd: list[str] = [
            'xfreerdp',
            f"/v:{self.host}",
            f"/u:{self.user}",
            f"/p:{self.password}",
            f"/size:{self.resolution}",
            '/cert:ignore',
            '/bpp:24',
            '+clipboard',
            '/relax-order-checks',
            '/kbd:0x00000409',
            '+fonts',
            '+aero',
            '+window-drag',
            '+menu-anims',
            '/network:auto',
            '/gdi:sw',
        ]
        if self.shared_dir is not None:
            rdp_cmd.append(f"/drive:{self.shared_name},{self.shared_dir}")
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
        self._set_display_env()
        with mss(display=self.display_num) as sct:
            sct.shot(output=output_path)

    def _get_scale_factors(self) -> tuple[float, float]:
        """Calculate the scale factors between physical pixels and logical coordinates."""
        self._set_display_env()
        import pyautogui
        with mss(display=self.display_num) as sct:
            monitor = sct.monitors[1]
            phys_width = monitor['width']
            phys_height = monitor['height']

        log_width, log_height = pyautogui.size()

        scale_x = phys_width / log_width
        scale_y = phys_height / log_height
        return scale_x, scale_y

    def click(self, x: int, y: int, button: MouseButton = MouseButton.LEFT) -> None:
        self._set_display_env()
        scale_x, scale_y = self._get_scale_factors()
        lx, ly = round(x / scale_x), round(y / scale_y)

        logger.info(
            'click', protocol='rdp', x=x, y=y,
            logical_x=lx, logical_y=ly, button=button.value,
        )
        import pyautogui
        pyautogui.click(x=lx, y=ly, button=button.value)

    def move(self, x: int, y: int) -> None:
        self._set_display_env()
        scale_x, scale_y = self._get_scale_factors()
        lx, ly = round(x / scale_x), round(y / scale_y)

        logger.info(
            'move', protocol='rdp', x=x,
            y=y, logical_x=lx, logical_y=ly,
        )
        import pyautogui
        pyautogui.moveTo(lx, ly)

    def scroll(self, clicks: int) -> None:
        logger.info('scroll', protocol='rdp', clicks=clicks)
        self._set_display_env()
        import pyautogui
        pyautogui.scroll(clicks)

    def type_text(self, text: str) -> None:
        logger.info('type_text', protocol='rdp', text=text)
        self._set_display_env()
        import pyautogui
        pyautogui.write(text, interval=0.05)

    def key_event(self, key: Key) -> None:
        logger.info('key_event', protocol='rdp', key=key.value)
        self._set_display_env()
        import pyautogui
        pyautogui.press(key.value)

    def hotkey(self, *keys: str) -> None:
        logger.info('hotkey', protocol='rdp', keys=list(keys))
        self._set_display_env()
        import pyautogui
        pyautogui.hotkey(*keys)

    def get_screen_size(self) -> tuple[int, int]:
        res_parts = self.resolution.split('x')
        return int(res_parts[0]), int(res_parts[1])

    def read_clipboard(self) -> str:
        """Read text from the X11 clipboard FreeRDP's ``+clipboard`` channel
        syncs with the remote Windows clipboard.

        Never logs the clipboard content, only its length.
        """
        text = self._clipboard.read_text()
        logger.info('clipboard_read', protocol='rdp', length=len(text))
        return text

    def write_clipboard(self, text: str) -> None:
        """Write text to the X11 clipboard FreeRDP's ``+clipboard`` channel
        syncs with the remote Windows clipboard.

        Never logs the clipboard content, only its length.
        """
        self._clipboard.write_text(text)
        logger.info('clipboard_write', protocol='rdp', length=len(text))
