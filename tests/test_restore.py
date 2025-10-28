from __future__ import annotations

import io
import shutil
import subprocess
import types
import uuid
import zipfile
from pathlib import Path

from ios_toolkit import restore


def _good_disk_usage():
    gb = 1024 ** 3
    return types.SimpleNamespace(total=200 * gb, used=50 * gb, free=150 * gb)


def _good_subprocess_run(*args, **kwargs):
    return types.SimpleNamespace(returncode=0, stdout="STATE : 4 RUNNING", stderr="")


def _fresh_dir() -> Path:
    base = Path("tmp-test-restore")
    base.mkdir(exist_ok=True)
    path = base / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    return path


def _make_ipsw(base_dir: Path, name: str = "firmware.ipsw") -> Path:
    path = base_dir / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "BuildManifest.plist",
            "<plist><dict><key>ProductType</key><string>iPhone12,8</string></dict></plist>",
        )
    return path


def test_preflight_tool_missing(monkeypatch):
    work_dir = _fresh_dir()
    ipsw = _make_ipsw(work_dir)
    monkeypatch.setattr(restore, "_have", lambda cmd: False if cmd == "idevicerestore" else True)
    monkeypatch.setattr(restore.shutil, "disk_usage", lambda _: _good_disk_usage())
    monkeypatch.setattr(restore.subprocess, "run", _good_subprocess_run)
    checks = restore.preflight_checks(udid=None, ipsw_path=str(ipsw))
    assert checks["ok"] is False
    assert any(not c["ok"] and c["name"] == "check_idevicerestore" for c in checks["checks"])
    assert any(c["name"] == "ipsw_validated" for c in checks["checks"])
    shutil.rmtree(work_dir, ignore_errors=True)


def test_restore_validation_ipsw_missing(monkeypatch):
    work_dir = _fresh_dir()
    monkeypatch.setattr(restore, "_have", lambda cmd: True)
    monkeypatch.setattr(restore.shutil, "disk_usage", lambda _: _good_disk_usage())
    monkeypatch.setattr(restore.subprocess, "run", _good_subprocess_run)
    missing = work_dir / "missing.ipsw"
    result = restore.restore(ipsw_path=str(missing), preflight_only=True)
    assert result.status == "failure"
    assert any(step.name == "ipsw_validated" and not step.ok for step in result.steps)
    assert restore.is_validation_failure(result) is True
    shutil.rmtree(work_dir, ignore_errors=True)


def test_restore_preflight_only_success(monkeypatch):
    work_dir = _fresh_dir()
    ipsw = _make_ipsw(work_dir)
    monkeypatch.setattr(restore, "_have", lambda cmd: True)
    monkeypatch.setattr(restore.shutil, "disk_usage", lambda _: _good_disk_usage())
    monkeypatch.setattr(restore.subprocess, "run", _good_subprocess_run)
    result = restore.restore(ipsw_path=str(ipsw), preflight_only=True, log_dir=str(work_dir))
    assert result.status == "success"
    assert any(step.name == "preflight" and step.ok for step in result.steps)
    assert any(step.name == "ipsw_validated" and step.ok for step in result.steps)
    shutil.rmtree(work_dir, ignore_errors=True)


def test_restore_dry_run(monkeypatch):
    work_dir = _fresh_dir()
    ipsw = _make_ipsw(work_dir)
    monkeypatch.setattr(restore, "_have", lambda cmd: True)
    monkeypatch.setattr(restore.shutil, "disk_usage", lambda _: _good_disk_usage())
    monkeypatch.setattr(restore.subprocess, "run", _good_subprocess_run)
    result = restore.restore(ipsw_path=str(ipsw), dry_run=True, log_dir=str(work_dir))
    assert result.status == "success"
    assert any(step.name == "compose_cmd" for step in result.steps)
    shutil.rmtree(work_dir, ignore_errors=True)


def test_restore_success(monkeypatch):
    work_dir = _fresh_dir()
    ipsw = _make_ipsw(work_dir)

    def have(cmd: str) -> bool:
        return cmd == "idevicerestore"

    monkeypatch.setattr(restore, "_have", have)
    monkeypatch.setattr(restore.shutil, "disk_usage", lambda _: _good_disk_usage())
    monkeypatch.setattr(restore.subprocess, "run", _good_subprocess_run)

    class FakeProcess:
        def __init__(self, *args, **kwargs):
            self.stdout = io.StringIO("Extracting\nSending RestoreImage\nRebooting\n")
            self._rc = 0

        def wait(self, timeout=None):
            return self._rc

        def terminate(self):
            self._rc = 1

        def kill(self):
            self._rc = 1

        def poll(self):
            return self._rc

    monkeypatch.setattr(restore.subprocess, "Popen", FakeProcess)

    result = restore.restore(ipsw_path=str(ipsw), log_dir=str(work_dir))
    assert result.status == "success"
    step_names = [step.name for step in result.steps]
    assert "extract" in step_names
    assert "send_restore_image" in step_names
    assert "idevicerestore" in step_names
    assert Path(result.logfile).exists()
    shutil.rmtree(work_dir, ignore_errors=True)


def test_restore_timeout(monkeypatch):
    work_dir = _fresh_dir()
    ipsw = _make_ipsw(work_dir)
    monkeypatch.setattr(restore, "_have", lambda cmd: True)
    monkeypatch.setattr(restore.shutil, "disk_usage", lambda _: _good_disk_usage())
    monkeypatch.setattr(restore.subprocess, "run", _good_subprocess_run)

    class HangingProcess:
        def __init__(self, *args, **kwargs):
            self.stdout = io.StringIO("")
            self._terminated = False
            self._rc = None

        def wait(self, timeout=None):
            if not self._terminated:
                raise subprocess.TimeoutExpired(cmd="idevicerestore", timeout=timeout)
            self._rc = 1
            return self._rc

        def terminate(self):
            self._terminated = True

        def kill(self):
            self._terminated = True
            self._rc = 1

        def poll(self):
            return self._rc

    monkeypatch.setattr(restore.subprocess, "Popen", HangingProcess)

    result = restore.restore(ipsw_path=str(ipsw), timeout_sec=1, log_dir=str(work_dir))
    assert result.status == "failure"
    assert any(step.name == "timeout" for step in result.steps)
    shutil.rmtree(work_dir, ignore_errors=True)
