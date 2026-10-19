"""Tests for the clipboard_read, clipboard_write, and shared_drive_info MCP tools."""
from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from remote_desktop_mcp.mcp import server
from remote_desktop_mcp.protocol.base import DesktopSession
from remote_desktop_mcp.protocol.base import Key
from remote_desktop_mcp.protocol.base import MouseButton
from remote_desktop_mcp.protocol.rdp import ClipboardError
from remote_desktop_mcp.protocol.rdp import RDPSession


class FakeDesktopSession(DesktopSession):
    """Minimal concrete DesktopSession for testing MCP tool gating logic.

    Implements only the abstract methods required by the base classes;
    none of them need real behaviour since the clipboard tools never call
    them directly.
    """

    protocol = 'fake'
    supports_clipboard = True

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def take_screenshot(self, output_path: str) -> None:
        pass

    def type_text(self, text: str) -> None:
        pass

    def key_event(self, key: Key) -> None:
        pass

    def get_screen_size(self) -> tuple[int, int]:
        return (800, 600)

    def click(self, x: int, y: int, button: MouseButton = MouseButton.LEFT) -> None:
        pass

    def move(self, x: int, y: int) -> None:
        pass

    def scroll(self, clicks: int) -> None:
        pass

    def hotkey(self, *keys: str) -> None:
        pass

    def read_clipboard(self) -> str:
        raise NotImplementedError('override per-test with a mock')

    def write_clipboard(self, text: str) -> None:
        raise NotImplementedError('override per-test with a mock')


@pytest.fixture(autouse=True)
def _reset_session():
    """Ensure every test starts and ends with no active session."""
    server._session = None
    yield
    server._session = None


def _make_rdp_session(**kwargs) -> RDPSession:
    return RDPSession(host='example.com', user='alice', password='secret', **kwargs)


# =========================================================================== #
# clipboard_read / clipboard_write — no active session
# =========================================================================== #

class TestNoActiveSession:
    def test_clipboard_read_returns_no_session_error(self) -> None:
        assert server._session is None
        result = server.clipboard_read()
        assert result == 'Error: No session active.'

    def test_clipboard_write_returns_no_session_error(self) -> None:
        assert server._session is None
        result = server.clipboard_write('text')
        assert result == 'Error: No session active.'

    def test_shared_drive_info_returns_disabled_without_session(self) -> None:
        assert server._session is None
        assert server.shared_drive_info() == {'enabled': False}


# =========================================================================== #
# clipboard_read / clipboard_write — capability gating
# =========================================================================== #

class TestCapabilityGating:
    def test_clipboard_read_errors_when_session_does_not_support_clipboard(self) -> None:
        session = FakeDesktopSession()
        session.supports_clipboard = False
        server._session = session

        result = server.clipboard_read()

        assert result == 'Error: Clipboard is not supported by the active session.'

    def test_clipboard_write_errors_when_session_does_not_support_clipboard(self) -> None:
        session = FakeDesktopSession()
        session.supports_clipboard = False
        server._session = session

        result = server.clipboard_write('text')

        assert result == 'Error: Clipboard is not supported by the active session.'


# =========================================================================== #
# clipboard_read / clipboard_write — success paths
# =========================================================================== #

class TestClipboardSuccess:
    def test_clipboard_read_returns_backend_text(self) -> None:
        session = FakeDesktopSession()
        server._session = session

        with patch.object(session, 'read_clipboard', return_value='hello clipboard'):
            result = server.clipboard_read()

        assert result == 'hello clipboard'

    def test_clipboard_write_returns_confirmation_message(self) -> None:
        session = FakeDesktopSession()
        server._session = session

        with patch.object(session, 'write_clipboard') as write_clipboard:
            result = server.clipboard_write('some text')

        assert result == 'Clipboard updated.'
        write_clipboard.assert_called_once_with('some text')


# =========================================================================== #
# clipboard_read / clipboard_write — backend unavailable (ClipboardError)
# =========================================================================== #

class TestClipboardBackendUnavailable:
    def test_clipboard_read_returns_clean_error_without_traceback(self) -> None:
        session = FakeDesktopSession()
        server._session = session

        with patch.object(
            session, 'read_clipboard',
            side_effect=ClipboardError("Clipboard backend 'xclip' is unavailable."),
        ):
            result = server.clipboard_read()

        assert result == "Error: Clipboard backend 'xclip' is unavailable."

    def test_clipboard_write_returns_clean_error_without_traceback(self) -> None:
        session = FakeDesktopSession()
        server._session = session

        with patch.object(
            session, 'write_clipboard',
            side_effect=ClipboardError("Clipboard backend 'xclip' is unavailable."),
        ):
            result = server.clipboard_write('text')

        assert result == "Error: Clipboard backend 'xclip' is unavailable."


# =========================================================================== #
# shared_drive_info
# =========================================================================== #

class TestSharedDriveInfo:
    def test_reports_disabled_when_shared_dir_not_configured(self) -> None:
        session = _make_rdp_session()
        server._session = session

        assert server.shared_drive_info() == {'enabled': False}

    def test_reports_disabled_for_non_desktop_session(self) -> None:
        server._session = object()  # not a DesktopSession at all

        assert server.shared_drive_info() == {'enabled': False}

    def test_reports_enabled_with_exact_shape_when_configured(self, tmp_path) -> None:
        shared_dir = tmp_path / 'rdp-share'
        shared_dir.mkdir()
        session = _make_rdp_session(shared_dir=str(shared_dir), shared_name='rea')
        server._session = session

        result = server.shared_drive_info()

        assert result == {
            'enabled': True,
            'name': 'rea',
            'local_path': str(shared_dir.resolve()),
            'windows_path': '\\\\tsclient\\rea',
        }
        # Sanity-check the literal Windows UNC path contents.
        assert result['windows_path'] == r'\\tsclient\rea'


# =========================================================================== #
# Trace/log content secrecy — mirrors TestClipboardLoggingSecrecy in
# tests/test_rdp_clipboard.py: the clipboard text itself must never reach
# the trace/log mechanism, only its length.
# =========================================================================== #

class TestTraceContentSecrecy:
    SECRET_TEXT = 'super-secret-password-12345'

    def _assert_secret_never_in_notify_calls(self, mock_notify: MagicMock) -> None:
        for call in mock_notify.mock_calls:
            _, args, kwargs = call
            for value in (*args, *kwargs.values()):
                assert self.SECRET_TEXT != value
                assert self.SECRET_TEXT not in str(value)

    def test_clipboard_read_trace_never_contains_clipboard_text(self) -> None:
        session = FakeDesktopSession()
        server._session = session

        with patch.object(session, 'read_clipboard', return_value=self.SECRET_TEXT), \
                patch.object(server, '_notify') as mock_notify:
            result = server.clipboard_read()

        assert result == self.SECRET_TEXT
        mock_notify.assert_called_once_with(
            'clipboard_read', {'length': len(self.SECRET_TEXT)},
        )
        self._assert_secret_never_in_notify_calls(mock_notify)

    def test_clipboard_write_trace_never_contains_clipboard_text(self) -> None:
        session = FakeDesktopSession()
        server._session = session

        with patch.object(session, 'write_clipboard'), \
                patch.object(server, '_notify') as mock_notify:
            server.clipboard_write(self.SECRET_TEXT)

        mock_notify.assert_called_once_with(
            'clipboard_write', {'length': len(self.SECRET_TEXT)},
        )
        self._assert_secret_never_in_notify_calls(mock_notify)
