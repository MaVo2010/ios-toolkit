from __future__ import annotations

import io
import shutil
import types
import uuid
from pathlib import Path

import pytest

from ios_toolkit import logs as logs_mod


def _make_temp_dir(name: str) -> Path:
    base = Path("tmp-test-logs")
    base.mkdir(exist_ok=True)
    target = base / f"{name}-{uuid.uuid4().hex}"
    target.mkdir(parents=True, exist_ok=False)
    return target


def test_stream_syslog_ok_with_filter_and_save(monkeypatch):
    # Pretend idevicesyslog exists.
    monkeypatch.setattr(logs_mod, "shutil", types.SimpleNamespace(which=lambda _: "C:\\Tools\\idevicesyslog.exe"))

    class FakeStdout(io.StringIO):
        def readline(self):
            try:
                return super().readline()
            except Exception:
                return ""

    def popen_stub(cmd, stdout, stderr, text, bufsize):
        data = "alpha\nbeta apfs\ncharlie nand\n"
        stream = FakeStdout(data)
        return types.SimpleNamespace(
            stdout=stream,
            poll=lambda: 0,
            terminate=lambda: None,
            wait=lambda timeout=None: None,
            kill=lambda: None,
        )

    monkeypatch.setattr(logs_mod.subprocess, "Popen", popen_stub)

    temp_dir = _make_temp_dir("syslog")
    out_file = temp_dir / "syslog.log"
    rc = logs_mod.stream_syslog(
        udid="UDID",
        save_path=str(out_file),
        filter_expr="apfs|nand",
        duration=None,
    )
    assert rc == 0
    content = out_file.read_text(encoding="utf-8")
    assert "apfs" in content or "nand" in content
    assert "alpha" not in content
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_stream_syslog_tool_missing(monkeypatch):
    monkeypatch.setattr(logs_mod, "shutil", types.SimpleNamespace(which=lambda _: None))
    rc = logs_mod.stream_syslog()
    assert rc == 2


def test_export_crashlogs_with_idevicecrashreport(monkeypatch):
    out_dir = _make_temp_dir("crashes")

    monkeypatch.setattr(logs_mod, "shutil", types.SimpleNamespace(which=lambda _: "C:\\Tools\\idevicecrashreport.exe"))

    class Completed:
        def __init__(self):
            self.returncode = 0
            self.stdout = "ok"
            self.stderr = ""

    def run_stub(cmd, capture_output, text, check):
        for index in range(5):
            (out_dir / f"crash_{index}.log").write_text(f"log {index}", encoding="utf-8")
        return Completed()

    monkeypatch.setattr(logs_mod.subprocess, "run", run_stub)

    result = logs_mod.export_crashlogs(udid="UDID", out_dir=str(out_dir), limit=3)
    assert result["source"] == "idevicecrashreport"
    assert len(result["exported"]) == 3
    assert Path(result["exported"][0]).exists()
    shutil.rmtree(out_dir, ignore_errors=True)


def test_export_crashlogs_tool_missing(monkeypatch):
    monkeypatch.setattr(logs_mod, "shutil", types.SimpleNamespace(which=lambda _: None))
    temp_dir = _make_temp_dir("missing")
    with pytest.raises(RuntimeError):
        logs_mod.export_crashlogs(udid=None, out_dir=str(temp_dir))
    shutil.rmtree(temp_dir, ignore_errors=True)
