"""Tests for the RDP clipboard backend and RDPSession integration."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from remote_desktop_mcp.protocol.rdp import ClipboardBackend
from remote_desktop_mcp.protocol.rdp import ClipboardError
from remote_desktop_mcp.protocol.rdp import RDPSession


def _make_session() -> RDPSession:
    return RDPSession(host='example.com', user='alice', password='secret')


def _start_session(session: RDPSession) -> None:
    """Start the session with Xvfb/xfreerdp subprocess calls mocked out."""
    with patch('remote_desktop_mcp.protocol.rdp.subprocess.Popen') as popen, \
            patch('remote_desktop_mcp.protocol.rdp.time.sleep'):
        popen.return_value = MagicMock()
        session.start()


class TestClipboardBackend:
    def test_read_text_returns_output_of_clipboard_tool(self) -> None:
        backend = ClipboardBackend(display=':99')
        fake_result = MagicMock(stdout=b'hello from clipboard', returncode=0)

        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value='/usr/bin/xclip'), \
                patch('remote_desktop_mcp.protocol.rdp.subprocess.run', return_value=fake_result) as run:
            text = backend.read_text()

        assert text == 'hello from clipboard'
        run.assert_called_once()
        argv = run.call_args.args[0]
        assert argv[0] == 'xclip'
        assert '-o' in argv

    def test_write_text_invokes_clipboard_tool_without_raising(self) -> None:
        backend = ClipboardBackend(display=':99')

        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value='/usr/bin/xclip'), \
                patch('remote_desktop_mcp.protocol.rdp.subprocess.run') as run:
            backend.write_text('some clipboard text')

        run.assert_called_once()
        kwargs = run.call_args.kwargs
        assert kwargs['input'] == b'some clipboard text'

    def test_write_text_does_not_capture_stdout_or_stderr(self) -> None:
        """Regression test (found against a real xclip): `xclip -i` forks a
        background process that stays alive to serve the clipboard and
        inherits any stdout/stderr pipe we give it, so capture_output=True
        (or stdout=PIPE/stderr=PIPE) makes subprocess.run() hang until the
        timeout on every real write, even though the write itself already
        succeeded. Mocked tests can't catch the hang itself, so this test
        pins the fix (DEVNULL on both streams) so it can't silently regress."""
        backend = ClipboardBackend(display=':99')

        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value='/usr/bin/xclip'), \
                patch('remote_desktop_mcp.protocol.rdp.subprocess.run') as run:
            backend.write_text('text')

        kwargs = run.call_args.kwargs
        assert kwargs.get('stdout') is subprocess.DEVNULL
        assert kwargs.get('stderr') is subprocess.DEVNULL
        assert 'capture_output' not in kwargs

    def test_read_text_passes_requested_display_to_subprocess(self) -> None:
        backend = ClipboardBackend(display=':42')
        fake_result = MagicMock(stdout=b'', returncode=0)

        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value='/usr/bin/xclip'), \
                patch('remote_desktop_mcp.protocol.rdp.subprocess.run', return_value=fake_result) as run:
            backend.read_text()

        env = run.call_args.kwargs['env']
        assert env['DISPLAY'] == ':42'

    def test_write_text_passes_requested_display_to_subprocess(self) -> None:
        backend = ClipboardBackend(display=':42')

        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value='/usr/bin/xclip'), \
                patch('remote_desktop_mcp.protocol.rdp.subprocess.run') as run:
            backend.write_text('text')

        env = run.call_args.kwargs['env']
        assert env['DISPLAY'] == ':42'

    def test_read_text_raises_clear_error_when_binary_missing(self) -> None:
        backend = ClipboardBackend(display=':99')

        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value=None):
            with pytest.raises(ClipboardError, match="xclip' is unavailable"):
                backend.read_text()

    def test_write_text_raises_clear_error_when_binary_missing(self) -> None:
        backend = ClipboardBackend(display=':99')

        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value=None):
            with pytest.raises(ClipboardError, match="xclip' is unavailable"):
                backend.write_text('text')

    def test_read_text_raises_clear_error_on_file_not_found(self) -> None:
        backend = ClipboardBackend(display=':99')

        run_patch = patch('remote_desktop_mcp.protocol.rdp.subprocess.run', side_effect=FileNotFoundError())
        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value='/usr/bin/xclip'), run_patch:
            with pytest.raises(ClipboardError, match="xclip' is unavailable"):
                backend.read_text()

    def test_read_text_returns_empty_string_when_clipboard_has_no_text(self) -> None:
        """xclip -o exits non-zero when CLIPBOARD has no owner or holds
        non-text content — the spec requires reporting that as "", not an
        error (there is no FileNotFoundError/TimeoutExpired here, just a
        failed run with a non-zero return code)."""
        backend = ClipboardBackend(display=':99')
        fake_result = MagicMock(stdout=b'', stderr=b'Error: target STRING not available', returncode=1)

        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value='/usr/bin/xclip'), \
                patch('remote_desktop_mcp.protocol.rdp.subprocess.run', return_value=fake_result):
            assert backend.read_text() == ''

    def test_read_text_raises_clear_error_on_timeout(self) -> None:
        """A hung xclip/X11 call must not block the MCP tool call forever."""
        backend = ClipboardBackend(display=':99')

        timeout = subprocess.TimeoutExpired(cmd=['xclip'], timeout=5)
        run_patch = patch('remote_desktop_mcp.protocol.rdp.subprocess.run', side_effect=timeout)
        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value='/usr/bin/xclip'), run_patch:
            with pytest.raises(ClipboardError, match='timed out'):
                backend.read_text()

    def test_write_text_raises_clear_error_on_timeout(self) -> None:
        backend = ClipboardBackend(display=':99')

        timeout = subprocess.TimeoutExpired(cmd=['xclip'], timeout=5)
        run_patch = patch('remote_desktop_mcp.protocol.rdp.subprocess.run', side_effect=timeout)
        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value='/usr/bin/xclip'), run_patch:
            with pytest.raises(ClipboardError, match='timed out'):
                backend.write_text('text')

    def test_read_text_passes_timeout_to_subprocess(self) -> None:
        backend = ClipboardBackend(display=':99')
        fake_result = MagicMock(stdout=b'', returncode=0)

        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value='/usr/bin/xclip'), \
                patch('remote_desktop_mcp.protocol.rdp.subprocess.run', return_value=fake_result) as run:
            backend.read_text()

        assert run.call_args.kwargs['timeout'] == 5


class TestRDPSessionClipboardIntegration:
    def test_read_clipboard_returns_text_from_backend(self) -> None:
        session = _make_session()

        with patch.object(session._clipboard, 'read_text', return_value='clip value') as read_text:
            result = session.read_clipboard()

        assert result == 'clip value'
        read_text.assert_called_once()

    def test_write_clipboard_delegates_to_backend_without_raising(self) -> None:
        session = _make_session()

        with patch.object(session._clipboard, 'write_text') as write_text:
            session.write_clipboard('some secret value')

        write_text.assert_called_once_with('some secret value')

    def test_clipboard_subprocess_uses_session_display(self) -> None:
        session = RDPSession(
            host='example.com', user='alice', password='secret',
            display_num=':77',
        )
        fake_result = MagicMock(stdout=b'', returncode=0)

        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value='/usr/bin/xclip'), \
                patch('remote_desktop_mcp.protocol.rdp.subprocess.run', return_value=fake_result) as run:
            session.read_clipboard()

        env = run.call_args.kwargs['env']
        assert env['DISPLAY'] == ':77'

    def test_read_clipboard_raises_clear_error_when_binary_unavailable(self) -> None:
        session = _make_session()

        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value=None):
            with pytest.raises(ClipboardError, match="xclip' is unavailable"):
                session.read_clipboard()

    def test_write_clipboard_raises_clear_error_when_binary_unavailable(self) -> None:
        session = _make_session()

        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value=None):
            with pytest.raises(ClipboardError, match="xclip' is unavailable"):
                session.write_clipboard('text')

    def test_session_start_does_not_fail_when_clipboard_binary_unavailable(self) -> None:
        """Missing clipboard binary must never abort the RDP connection."""
        session = _make_session()

        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value=None):
            _start_session(session)

        assert session._clipboard_available is False
        # The session itself was built and started fine; only clipboard
        # calls are affected.
        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value=None):
            with pytest.raises(ClipboardError):
                session.read_clipboard()

    def test_session_construction_does_not_check_clipboard_availability(self) -> None:
        """Constructing a session must not require/check the clipboard binary."""
        with patch('remote_desktop_mcp.protocol.rdp.shutil.which', return_value=None) as which:
            session = _make_session()
            which.assert_not_called()

        assert session._clipboard_available is None


class TestClipboardLoggingSecrecy:
    SECRET_TEXT = 'super-secret-password-12345'

    def _assert_secret_never_passed_to_logger(self, mock_logger: MagicMock) -> None:
        for call in mock_logger.mock_calls:
            _, args, kwargs = call
            for value in (*args, *kwargs.values()):
                assert self.SECRET_TEXT != value
                assert self.SECRET_TEXT not in str(value)

    def test_read_clipboard_never_logs_clipboard_content(self) -> None:
        session = _make_session()

        with patch.object(session._clipboard, 'read_text', return_value=self.SECRET_TEXT), \
                patch('remote_desktop_mcp.protocol.rdp.logger') as mock_logger:
            session.read_clipboard()

        mock_logger.info.assert_called_once()
        self._assert_secret_never_passed_to_logger(mock_logger)

    def test_write_clipboard_never_logs_clipboard_content(self) -> None:
        session = _make_session()

        with patch.object(session._clipboard, 'write_text'), \
                patch('remote_desktop_mcp.protocol.rdp.logger') as mock_logger:
            session.write_clipboard(self.SECRET_TEXT)

        mock_logger.info.assert_called_once()
        self._assert_secret_never_passed_to_logger(mock_logger)
