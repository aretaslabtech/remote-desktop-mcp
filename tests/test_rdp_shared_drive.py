"""Tests for RDP shared-directory / FreeRDP drive-redirection support."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from remote_desktop_mcp.protocol.rdp import RDPSession

ORIGINAL_RDP_CMD = [
    '/v:example.com',
    '/u:alice',
    '/p:secret',
    '/size:1280x720',
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


def _start_session(session: RDPSession) -> list[list[object]]:
    """Start the session with subprocess/time mocked out and return the
    argv lists Popen was called with, in call order."""
    with patch('remote_desktop_mcp.protocol.rdp.subprocess.Popen') as popen, \
            patch('remote_desktop_mcp.protocol.rdp.time.sleep'):
        popen.return_value = MagicMock()
        session.start()
        return [call.args[0] for call in popen.call_args_list]


def test_no_shared_dir_means_no_drive_arg_and_unchanged_cmd() -> None:
    session = RDPSession(host='example.com', user='alice', password='secret')
    calls = _start_session(session)

    assert len(calls) == 2
    xvfb_cmd, rdp_cmd = calls
    assert not any(str(arg).startswith('/drive:') for arg in rdp_cmd)
    assert rdp_cmd == ['xfreerdp', *ORIGINAL_RDP_CMD]


def test_default_construction_produces_identical_cmd_to_before_change() -> None:
    """Regression test: constructing RDPSession with only the original
    parameters must produce exactly the same xfreerdp argv as before the
    shared_dir/shared_name feature was added."""
    session = RDPSession(host='example.com', user='alice', password='secret')
    assert session.shared_dir is None
    assert session.shared_name == 'shared'

    _, rdp_cmd = _start_session(session)
    assert rdp_cmd == ['xfreerdp', *ORIGINAL_RDP_CMD]


def test_valid_shared_dir_and_explicit_name_adds_drive_arg(tmp_path: Path) -> None:
    session = RDPSession(
        host='example.com', user='alice', password='secret',
        shared_dir=str(tmp_path), shared_name='rea',
    )
    _, rdp_cmd = _start_session(session)

    resolved = str(tmp_path.resolve())
    assert f"/drive:rea,{resolved}" in rdp_cmd


def test_shared_dir_pointing_at_a_file_raises(tmp_path: Path) -> None:
    file_path = tmp_path / 'not-a-dir.txt'
    file_path.write_text('hello')

    with patch('remote_desktop_mcp.protocol.rdp.subprocess.Popen') as popen:
        with pytest.raises(ValueError, match='is not a directory'):
            RDPSession(
                host='example.com', user='alice', password='secret',
                shared_dir=str(file_path),
            )
        popen.assert_not_called()


def test_shared_dir_pointing_at_nonexistent_path_raises(tmp_path: Path) -> None:
    missing = tmp_path / 'does-not-exist'

    with patch('remote_desktop_mcp.protocol.rdp.subprocess.Popen') as popen:
        with pytest.raises(ValueError, match='does not exist'):
            RDPSession(
                host='example.com', user='alice', password='secret',
                shared_dir=str(missing),
            )
        popen.assert_not_called()


def test_tilde_expanding_shared_dir_is_resolved_correctly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = tmp_path / 'home-dir'
    share_dir = fake_home / 'rdp-share'
    share_dir.mkdir(parents=True)

    monkeypatch.setattr(Path, 'home', lambda: fake_home)
    monkeypatch.setenv('HOME', str(fake_home))

    session = RDPSession(
        host='example.com', user='alice', password='secret',
        shared_dir='~/rdp-share',
    )

    assert session.shared_dir == str(share_dir.resolve())


@pytest.mark.parametrize('forbidden_path_name', ['home', 'cwd', 'root', 'tmp'])
def test_forbidden_paths_are_refused(
    forbidden_path_name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    if forbidden_path_name == 'home':
        monkeypatch.setattr(Path, 'home', lambda: tmp_path)
        candidate = str(tmp_path)
    elif forbidden_path_name == 'cwd':
        monkeypatch.chdir(tmp_path)
        candidate = str(tmp_path)
    elif forbidden_path_name == 'root':
        candidate = '/'
    else:
        candidate = '/tmp'

    with pytest.raises(ValueError):
        RDPSession(
            host='example.com', user='alice', password='secret',
            shared_dir=candidate,
        )
