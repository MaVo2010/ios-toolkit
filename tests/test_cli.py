import json

from typer.testing import CliRunner

from ios_toolkit import cli, device, models


runner = CliRunner()


def test_list_json_no_devices(monkeypatch):
    monkeypatch.setattr(device, "list_devices", lambda: [])
    result = runner.invoke(cli.app, ["list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


def test_list_json_reports_missing_tools(monkeypatch):
    def _fake():
        raise device.DeviceToolMissingError(["idevice_id"])

    monkeypatch.setattr(device, "list_devices", _fake)
    result = runner.invoke(cli.app, ["list", "--json"])
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["error"]
    assert payload["missing_tools"] == ["idevice_id"]


def test_info_json_success(monkeypatch):
    sample = models.Device(
        udid="0001",
        product_type="iPhone12,1",
        product_version="17.0",
        device_name="Demo",
        mode="normal",
        connection="usb",
        details={"UniqueDeviceID": "0001"},
    )
    monkeypatch.setattr(device, "get_info", lambda udid=None: sample)
    result = runner.invoke(cli.app, ["info", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    expected = sample.model_dump(mode="json")
    assert payload == expected


def test_info_json_handles_errors(monkeypatch):
    def _fake(udid=None):
        raise device.NoDevicesError()

    monkeypatch.setattr(device, "get_info", _fake)
    result = runner.invoke(cli.app, ["info", "--json"])
    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["error"]
