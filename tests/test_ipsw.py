from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from ios_toolkit import cli, ipsw


def _workspace_dir(prefix: str = "tmp-test-ipsw") -> Path:
    root = Path(prefix)
    root.mkdir(exist_ok=True)
    path = root / uuid.uuid4().hex
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


def test_validate_ipsw_ok():
    work_dir = _workspace_dir()
    try:
        path = _make_ipsw(work_dir)
        info = ipsw.validate_ipsw(str(path))
        assert info["ok"] is True
        assert info["size"] > 0
        assert info["sha1"]
        assert info["has_manifest"] is True
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def test_validate_ipsw_missing():
    work_dir = _workspace_dir()
    try:
        path = work_dir / "missing.ipsw"
        info = ipsw.validate_ipsw(str(path))
        assert info["ok"] is False
        assert info["error"]
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def test_cli_ipsw_verify_success():
    work_dir = _workspace_dir()
    try:
        path = _make_ipsw(work_dir)
        runner = CliRunner()
        result = runner.invoke(cli.app, ["ipsw", "verify", "--file", str(path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def test_cli_ipsw_verify_failure():
    work_dir = _workspace_dir()
    try:
        path = work_dir / "missing.ipsw"
        runner = CliRunner()
        result = runner.invoke(cli.app, ["ipsw", "verify", "--file", str(path), "--json"])
        assert result.exit_code == 2
        data = json.loads(result.stdout)
        assert data["ok"] is False
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
