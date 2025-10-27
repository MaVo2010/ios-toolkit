from ios_toolkit import device


def test_parse_kv_text():
    raw = """
    ProductType: iPhone12,1
    DeviceName: Demo Phone
    # comment
    ProductVersion: 17.0
    """
    parsed = device._parse_kv_text(raw)
    assert parsed["ProductType"] == "iPhone12,1"
    assert parsed["DeviceName"] == "Demo Phone"
    assert "comment" not in parsed


def test_normalize_info_detects_modes():
    normal = device._normalize_info(
        {"ProductVersion": "17.0", "ProductType": "iPhone12,1", "DeviceName": "Demo", "UniqueDeviceID": "0001"},
        udid="0001",
        connection="usb",
    )
    assert normal["udid"] == "0001"
    assert normal["mode"] == "normal"
    assert normal["connection"] == "usb"
    assert normal["details"]["ProductType"] == "iPhone12,1"

    recovery = device._normalize_info({"RecoveryMode": "1"}, udid="0001")
    assert recovery["mode"] == "recovery"


def test_build_device_sanitizes_bytes():
    raw = {
        "UniqueDeviceID": "0001",
        "ProductType": "iPhone12,1",
        "BasebandSerialNumber": b"\x00\x01",
    }
    model = device._build_device(raw, udid="0001", connection="usb")
    assert model.udid == "0001"
    assert model.details["BasebandSerialNumber"] == "0001"
