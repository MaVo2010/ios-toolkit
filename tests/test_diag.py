from __future__ import annotations

import types

from ios_toolkit import device

def _command_result(stdout: str = '', stderr: str = '', code: int = 0):
    return device.CommandResult(code, stdout, stderr)

def test_diag_usb_powershell(monkeypatch):
    def run_stub(cmd, capture_output, text, timeout):
        return types.SimpleNamespace(returncode=0, stdout='Running', stderr='')

    monkeypatch.setattr(device.subprocess, 'run', run_stub)
    monkeypatch.setattr(device, '_call', lambda *args, **kwargs: _command_result())
    monkeypatch.setattr(
        device.shutil,
        'which',
        lambda tool: 'C:/Tools/' + tool if tool != 'irecovery' else None,
    )
    monkeypatch.setenv('PATH', 'C:/Tools')

    data = device.diag_usb()
    assert data['amds_running'] is True
    assert 'irecovery' in data['missing_tools']
    assert data['notes']

def test_diag_usb_sc_fallback(monkeypatch):
    def run_fail(*args, **kwargs):
        raise RuntimeError('powershell missing')

    monkeypatch.setattr(device.subprocess, 'run', run_fail)

    def call_stub(cmd, timeout):
        return _command_result('SERVICE_NAME: Apple Mobile Device Service\n        STATE              : 1  STOPPED')

    monkeypatch.setattr(device, '_call', call_stub)
    monkeypatch.setattr(device.shutil, 'which', lambda tool: None)
    monkeypatch.setenv('PATH', 'C:/Tools')

    data = device.diag_usb()
    assert data['amds_running'] is False
    assert len(data['missing_tools']) >= 1

