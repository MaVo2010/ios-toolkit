from __future__ import annotations

import json
import types

from typer.testing import CliRunner

from ios_toolkit import cli, device


runner = CliRunner()


def _command_result(stdout: str = "", stderr: str = "", code: int = 0):
    return device.CommandResult(code, stdout, stderr)


def _disk_usage(free_gb: int = 128):
    class _Usage:
        total = free_gb * 2 * 1024**3
        used = free_gb * 1024**3
        free = free_gb * 1024**3

    return _Usage()


def test_diag_usb_reports_dfu(monkeypatch):
    def run_stub(cmd, capture_output, text, timeout):
        command = cmd[-1]
        if "Get-Service" in command:
            return types.SimpleNamespace(returncode=0, stdout="Running", stderr="")
        if "Get-PnpDevice" in command:
            return types.SimpleNamespace(returncode=0, stdout="USB\\VID_05AC&PID_12A8", stderr="")
        raise AssertionError(f"Unexpected command: {cmd}")

    def call_stub(cmd, timeout=5):
        if cmd[:2] == ["irecovery", "-q"]:
            return _command_result(stdout="MODE: DFU\n")
        tool_name = cmd[0]
        if "idevice_id" in tool_name:
            return _command_result(stdout="idevice_id 1.3.0")
        if "ideviceinfo" in tool_name:
            return _command_result(stdout="ideviceinfo 1.3.0")
        if "irecovery" in tool_name and "--version" in cmd:
            return _command_result(stdout="irecovery 1.0.0")
        return _command_result()

    monkeypatch.setattr(device.subprocess, "run", run_stub)
    monkeypatch.setattr(device, "_call", call_stub)
    monkeypatch.setattr(
        device.shutil,
        "which",
        lambda tool: f"C:/Tools/{tool}.exe" if tool in {"idevice_id", "ideviceinfo", "irecovery"} else None,
    )
    monkeypatch.setattr(device.shutil, "disk_usage", lambda _: _disk_usage(200))
    monkeypatch.setenv("PATH", "C:/Tools;C:/More;")

    data = device.diag_usb()

    assert data["amds"]["running"] is True
    assert data["amds"]["status"] == "Running"
    assert any(entry["name"] == "irecovery" and entry["found"] for entry in data["tools"]["entries"])
    assert data["usb"]["dfu_detected"] is True
    assert data["usb"]["recovery_detected"] is False
    assert data["host"]["apple_pnp_present"] is True
    assert isinstance(data["hints"], list)
    assert any("Fehlende Tools" in hint for hint in data["hints"])


def test_diag_usb_sc_fallback_and_recovery(monkeypatch):
    def run_stub(cmd, capture_output, text, timeout):
        command = cmd[-1]
        if "Get-Service" in command:
            raise FileNotFoundError("powershell missing")
        if "Get-PnpDevice" in command:
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {cmd}")

    def call_stub(cmd, timeout=5):
        if cmd[:2] == ["sc", "query"]:
            return _command_result(
                stdout="SERVICE_NAME: Apple Mobile Device Service\n        STATE              : 1  STOPPED"
            )
        if cmd[:2] == ["irecovery", "-q"]:
            return _command_result(stdout="MODE: Recovery\nDEVICE_STATE: Recovery")
        tool_name = cmd[0]
        if "irecovery" in tool_name and "--version" in cmd:
            return _command_result(stdout="irecovery 1.0.0")
        return _command_result(stderr="not available", code=1)

    monkeypatch.setattr(device.subprocess, "run", run_stub)
    monkeypatch.setattr(device, "_call", call_stub)
    monkeypatch.setattr(
        device.shutil,
        "which",
        lambda tool: "C:/Tools/irecovery.exe" if tool == "irecovery" else None,
    )
    monkeypatch.setattr(device.shutil, "disk_usage", lambda _: _disk_usage(64))
    monkeypatch.setenv("PATH", "C:/Tools")

    data = device.diag_usb()

    assert data["amds"]["running"] is False
    assert data["amds"]["source"] == "sc"
    assert "STOPPED" in (data["amds"]["status"] or "")
    assert data["usb"]["recovery_detected"] is True
    assert data["usb"]["dfu_detected"] is False
    assert data["usb"]["irecovery_available"] is True
    assert data["host"]["apple_pnp_present"] is False
    assert any("Apple Mobile Device Service" in hint for hint in data["hints"])


def test_cli_diag_usb_json(monkeypatch):
    sample = {
        "amds": {"running": True, "status": "Running", "error": None},
        "tools": {"checked": [], "entries": [], "missing": []},
        "usb": {"dfu_detected": False},
        "host": {},
        "hints": [],
    }

    monkeypatch.setattr(device, "diag_usb", lambda: sample)

    result = runner.invoke(cli.app, ["diag", "usb", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["amds"]["running"] is True

