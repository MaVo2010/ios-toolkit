import types

import pytest

from ios_toolkit import device, models


def _fake_normal_device(udid: str) -> models.Device:
    return models.Device(
        udid=udid,
        product_type="iPhone12,1",
        product_version="17.0",
        device_name="Demo",
        connection="usb",
        mode="normal",
        details={},
    )


@pytest.fixture(autouse=False)
def _stub_discovery(monkeypatch):
    monkeypatch.setattr(device, "_discover_devices", lambda: ([{"udid": "0001", "connection": "usb"}], [], True))
    monkeypatch.setattr(device, "get_info", lambda udid, allow_discovery: _fake_normal_device(udid))


def test_list_devices_includes_dfu_device(monkeypatch, _stub_discovery):
    monkeypatch.setattr(device.shutil, "which", lambda name: "irecovery" if name == "irecovery" else None)

    def fake_run(cmd, capture_output, text, timeout, check):
        assert cmd == ["irecovery", "-q"]
        return types.SimpleNamespace(returncode=0, stdout="MODE: DFU\n", stderr="")

    monkeypatch.setattr(device.subprocess, "run", fake_run)

    devices = device.list_devices(include_dfu=True)
    assert len(devices) == 2
    dfu = next((entry for entry in devices if entry.mode == "dfu"), None)
    assert dfu is not None
    assert dfu.udid is None
    assert dfu.device_name == "(DFU device)"


def test_list_devices_without_irecovery(monkeypatch, _stub_discovery):
    monkeypatch.setattr(device.shutil, "which", lambda name: None)

    def fail_run(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called without irecovery")

    monkeypatch.setattr(device.subprocess, "run", fail_run)

    devices = device.list_devices(include_dfu=True)
    assert len(devices) == 1
    assert all(entry.mode != "dfu" for entry in devices)


def test_list_devices_non_dfu_mode(monkeypatch, _stub_discovery):
    monkeypatch.setattr(device.shutil, "which", lambda name: "irecovery" if name == "irecovery" else None)

    def fake_run(cmd, capture_output, text, timeout, check):
        assert cmd == ["irecovery", "-q"]
        return types.SimpleNamespace(returncode=0, stdout="MODE: Recovery\n", stderr="")

    monkeypatch.setattr(device.subprocess, "run", fake_run)

    devices = device.list_devices(include_dfu=True)
    assert len(devices) == 1
    assert all(entry.mode != "dfu" for entry in devices)
