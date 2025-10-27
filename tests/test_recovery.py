from __future__ import annotations

import types

from ios_toolkit import recovery as r


def test_parse_irecovery_q_variants():
    assert r.parse_irecovery_q("MODE: DFU\nCPID: 1234") == "dfu"
    assert r.parse_irecovery_q("DEVICE_STATE: Recovery\nCPID: 1234") == "recovery"
    assert r.parse_irecovery_q("state: normal\nblah") == "normal"
    assert r.parse_irecovery_q("random output") == "unknown"


def test_status_tool_missing(monkeypatch):
    monkeypatch.setattr(r, "shutil", types.SimpleNamespace(which=lambda _: None))
    data = r.status(udid=None)
    assert data["mode"] == "unknown"
    assert data.get("tool_missing") is True
    assert data.get("error")


def test_status_recovery(monkeypatch):
    monkeypatch.setattr(
        r,
        "shutil",
        types.SimpleNamespace(
            which=lambda cmd: "C:\\Tools\\irecovery.exe" if cmd == "irecovery" else None
        ),
    )
    monkeypatch.setattr(r, "_run", lambda cmd, timeout=30: (0, "DEVICE_STATE: Recovery", ""))
    data = r.status(udid=None)
    assert data == {"mode": "recovery"}


def test_status_dfu(monkeypatch):
    monkeypatch.setattr(
        r,
        "shutil",
        types.SimpleNamespace(
            which=lambda cmd: "C:\\Tools\\irecovery.exe" if cmd == "irecovery" else None
        ),
    )
    monkeypatch.setattr(r, "_run", lambda cmd, timeout=30: (0, "MODE: DFU", ""))
    data = r.status(udid=None)
    assert data == {"mode": "dfu"}


def test_status_error(monkeypatch):
    monkeypatch.setattr(
        r,
        "shutil",
        types.SimpleNamespace(
            which=lambda cmd: "C:\\Tools\\irecovery.exe" if cmd == "irecovery" else None
        ),
    )
    monkeypatch.setattr(r, "_run", lambda cmd, timeout=30: (1, "", "boom"))
    data = r.status(udid=None)
    assert data["mode"] == "unknown"
    assert data.get("error") == "irecovery -q failed"


def test_enter_no_tool(monkeypatch):
    monkeypatch.setattr(r, "shutil", types.SimpleNamespace(which=lambda _: None))
    assert r.enter(udid=None) is False


def test_enter_success(monkeypatch):
    monkeypatch.setattr(
        r,
        "shutil",
        types.SimpleNamespace(
            which=lambda cmd: "C:\\Tools\\idevicediagnostics.exe" if cmd == "idevicediagnostics" else None
        ),
    )
    calls = []

    def run_stub(cmd, timeout=30):
        calls.append(cmd)
        return 0, "", ""

    monkeypatch.setattr(r, "_run", run_stub)
    assert r.enter(udid="ABC") is True
    assert calls and calls[0][0] == "idevicediagnostics"


def test_kickout_failure(monkeypatch):
    monkeypatch.setattr(
        r,
        "shutil",
        types.SimpleNamespace(
            which=lambda cmd: "C:\\Tools\\irecovery.exe" if cmd == "irecovery" else None
        ),
    )
    monkeypatch.setattr(r, "_run", lambda cmd, timeout=30: (1, "", "boom"))
    assert r.kickout(udid=None) is False


def test_kickout_success(monkeypatch):
    monkeypatch.setattr(
        r,
        "shutil",
        types.SimpleNamespace(
            which=lambda cmd: "C:\\Tools\\irecovery.exe" if cmd == "irecovery" else None
        ),
    )
    calls = []

    def run_stub(cmd, timeout=30):
        calls.append(cmd)
        return 0, "", ""

    monkeypatch.setattr(r, "_run", run_stub)
    assert r.kickout(udid="ABC") is True
    assert calls and calls[0][0] == "irecovery"
