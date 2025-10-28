from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple

from . import models, utils

log = utils.get_logger(__name__)


class DeviceError(Exception):
    """Base error for device discovery/inspection issues."""

    def __init__(self, message: str, *, exit_code: int = 1, payload: Optional[dict] = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.payload = payload or {}


class DeviceToolMissingError(DeviceError):
    """Raised when required external tools are not available."""

    def __init__(self, tools: Iterable[str]) -> None:
        self.tools = sorted({tool for tool in tools})
        message = "Benoetigte Tools fehlen: " + ", ".join(self.tools)
        super().__init__(message, exit_code=2, payload={"missing_tools": self.tools})


class NoDevicesError(DeviceError):
    """Raised when no devices are detected."""

    def __init__(self) -> None:
        super().__init__("Kein Geraet erkannt.", exit_code=3)


class MultipleDevicesError(DeviceError):
    """Raised when multiple devices are available but no UDID was requested."""

    def __init__(self, udids: Iterable[str]) -> None:
        udid_list = sorted(udids)
        message = "Mehrere Geraete erkannt. Bitte --udid angeben."
        super().__init__(message, exit_code=4, payload={"udids": udid_list})
        self.udids = udid_list


@dataclass
class CommandResult:
    code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def detect_dfu() -> bool:
    """Return True if irecovery reports DFU mode; never raises."""
    if not _have("irecovery"):
        return False

    result = _call(["irecovery", "-q"])
    if not result.ok or not result.stdout:
        return False

    kv = _parse_kv_text(result.stdout)
    mode_value = kv.get("MODE") or kv.get("Mode") or kv.get("mode")
    if mode_value and mode_value.strip().lower() == "dfu":
        return True

    return False


def _call(cmd: Sequence[str], timeout: int = 10) -> CommandResult:
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)
    except FileNotFoundError:
        return CommandResult(127, "", f"{cmd[0]} not found")
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else "timeout"
        return CommandResult(-1, stdout, stderr)
    except Exception as exc:  # pragma: no cover - defensive
        return CommandResult(-1, "", str(exc))


def _parse_kv_text(text: str) -> dict:
    data: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def _detect_mode(raw: dict) -> str:
    def _truthy(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes"}
        return False

    if _truthy(raw.get("DFUMode")) or _truthy(raw.get("DeviceMode") == "dfu"):
        return "dfu"
    if _truthy(raw.get("RecoveryMode")) or _truthy(raw.get("IsInRecoveryMode")):
        return "recovery"
    if raw.get("ProductVersion"):
        return "normal"
    return "unknown"


def _normalize_connection(value: Optional[str]) -> str:
    if value is None:
        return "unknown"
    normalized = str(value).strip().lower()
    return normalized if normalized in {"usb", "wifi"} else "unknown"


def _json_safe(value):
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, bytes):
        return value.hex()
    return value


def _normalize_info(raw: dict, *, udid: Optional[str] = None, connection: Optional[str] = None) -> dict:
    connection_value = _normalize_connection(raw.get("ConnectionType") or connection)

    normalized = {
        "udid": raw.get("UniqueDeviceID") or raw.get("udid") or udid,
        "product_type": raw.get("ProductType") or raw.get("product_type"),
        "product_version": raw.get("ProductVersion") or raw.get("product_version"),
        "device_name": raw.get("DeviceName") or raw.get("device_name"),
        "mode": _detect_mode(raw),
        "connection": connection_value,
        "details": {k: _json_safe(v) for k, v in raw.items()},
    }
    return normalized


def _build_device(raw: dict, *, udid: Optional[str], connection: Optional[str]) -> models.Device:
    return models.Device.model_validate(_normalize_info(raw, udid=udid, connection=connection))


def _discover_via_pymobiledevice3() -> Tuple[list[dict], bool]:
    try:
        from pymobiledevice3.usbmux import list_devices as mux_list  # type: ignore
    except ImportError:
        return [], False

    try:
        mux_devices = mux_list()
    except Exception:
        return [], True

    discovered = []
    for mux_device in mux_devices:
        udid = getattr(mux_device, "serial", None)
        if not udid:
            continue
        connection_type = getattr(mux_device, "connection_type", "unknown") or "unknown"
        discovered.append(
            {
                "udid": str(udid),
                "connection": str(connection_type).lower(),
                "source": "pymobiledevice3",
            }
        )
    return discovered, True


def _discover_via_idevice_id() -> Tuple[list[dict], bool]:
    if not _have("idevice_id"):
        return [], False

    result = _call(["idevice_id", "-l"])
    if result.code not in (0, 1):
        return [], True

    discovered = []
    for raw_line in result.stdout.splitlines():
        udid = raw_line.strip()
        if udid:
            discovered.append(
                {
                    "udid": udid,
                    "connection": "usb",
                    "source": "idevice_id",
                }
            )
    return discovered, True


def _discover_devices() -> Tuple[list[dict], list[str], bool]:
    devices: dict[str, dict] = {}
    missing_tools: list[str] = []

    pymux_devices, pymux_available = _discover_via_pymobiledevice3()
    for entry in pymux_devices:
        devices[entry["udid"]] = entry

    idevice_devices, idevice_available = _discover_via_idevice_id()
    for entry in idevice_devices:
        devices.setdefault(entry["udid"], entry)

    if not idevice_available:
        missing_tools.append("idevice_id")

    any_tool_available = pymux_available or idevice_available
    return list(devices.values()), missing_tools, any_tool_available


def list_devices(include_dfu: bool = False) -> list[models.Device]:
    discovered, missing_tools, any_tool = _discover_devices()
    devices: list[models.Device] = []

    if not discovered:
        if not any_tool and missing_tools:
            raise DeviceToolMissingError(missing_tools)
    else:
        info_missing_tools: set[str] = set()
        for entry in discovered:
            udid = entry["udid"]
            connection = entry.get("connection")
            try:
                info = get_info(udid, allow_discovery=False)
            except DeviceToolMissingError as exc:
                info_missing_tools.update(exc.tools)
                info = _build_device({}, udid=udid, connection=connection)
            except DeviceError as exc:
                log.debug("get_info fallback for %s: %s", udid, exc)
                info = _build_device({}, udid=udid, connection=connection)
            else:
                if connection and info.connection == "unknown":
                    info = info.model_copy(update={"connection": _normalize_connection(connection)})
            devices.append(info)

        if info_missing_tools:
            raise DeviceToolMissingError(info_missing_tools)

    if include_dfu and detect_dfu():
        if not any(existing.mode == "dfu" for existing in devices):
            devices.append(
                models.Device.model_construct(
                    udid=None,
                    product_type=None,
                    product_version=None,
                    device_name="(DFU device)",
                    connection="usb",
                    mode="dfu",
                    details={},
                )
            )

    return devices


def _get_info_via_pymobiledevice3(udid: str) -> Optional[dict]:
    try:
        from pymobiledevice3.lockdown import create_using_usbmux  # type: ignore
    except ImportError:
        return None

    try:
        with create_using_usbmux(serial=udid, autopair=False) as client:
            raw = dict(client.all_values or {})
            raw.setdefault("UniqueDeviceID", client.udid or udid)
            raw.setdefault("ConnectionType", getattr(client.service.mux_device, "connection_type", "unknown"))
            return raw
    except Exception:
        return None


def _get_info_via_ideviceinfo(udid: Optional[str]) -> Optional[dict]:
    if not _have("ideviceinfo"):
        return None

    cmd = ["ideviceinfo"]
    if udid:
        cmd += ["-u", udid]
    result = _call(cmd)
    if not result.ok or not result.stdout.strip():
        return None
    data = _parse_kv_text(result.stdout)
    if udid and not data.get("UniqueDeviceID"):
        data["UniqueDeviceID"] = udid
    return data


def get_info(udid: Optional[str] = None, *, allow_discovery: bool = True) -> models.Device:
    if udid is None and allow_discovery:
        discovered, missing_tools, any_tool = _discover_devices()
        if not discovered:
            if missing_tools and not any_tool:
                raise DeviceToolMissingError(missing_tools)
            raise NoDevicesError()
        if len(discovered) > 1:
            raise MultipleDevicesError(entry["udid"] for entry in discovered)
        udid = discovered[0]["udid"]

    if not udid:
        raise DeviceError("UDID konnte nicht ermittelt werden.", exit_code=5)

    raw_info = _get_info_via_pymobiledevice3(udid)
    if raw_info:
        return _build_device(raw_info, udid=udid, connection=None)

    raw_info = _get_info_via_ideviceinfo(udid)
    if raw_info:
        return _build_device(raw_info, udid=udid, connection="usb")

    missing_tools = []
    if not _have("ideviceinfo"):
        missing_tools.append("ideviceinfo")
    if missing_tools:
        raise DeviceToolMissingError(missing_tools)

    raise DeviceError(f"Konnte keine Informationen fuer {udid} abrufen.", exit_code=6)


def diag_usb():
    def _query_amds_status() -> Tuple[bool, Optional[str], Optional[str]]:
        error_text = None
        ps_cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-Service 'Apple Mobile Device Service' -ErrorAction Stop).Status",
        ]
        try:
            completed = subprocess.run(ps_cmd, capture_output=True, text=True, timeout=5)
            if completed.returncode == 0 and completed.stdout:
                status = completed.stdout.strip()
                if status:
                    return status.upper() == "RUNNING", status, None
        except Exception as exc:  # pragma: no cover - PowerShell not available
            error_text = str(exc)
            log.debug("PowerShell AMDS check failed: %s", exc)

        fallback = _call(["sc", "query", "Apple Mobile Device Service"], timeout=5)
        if fallback.code == 0:
            status_text = fallback.stdout.strip()
            return "RUNNING" in status_text.upper(), status_text, error_text
        return False, None, fallback.stderr or error_text

    amds_running, amds_status, amds_error = _query_amds_status()

    tool_list = [
        "idevice_id",
        "ideviceinfo",
        "idevicesyslog",
        "idevicecrashreport",
        "irecovery",
        "idevicerestore",
    ]

    missing_tools = [tool for tool in tool_list if not _have(tool)]
    have_idevice_tools = _have("idevice_id") and _have("ideviceinfo")
    have_irecovery = _have("irecovery")
    have_idevicerestore = _have("idevicerestore")

    path_value = os.environ.get("PATH", "")
    path_hint = path_value if len(path_value) <= 200 else f"{path_value[:197]}..."

    data = {
        "amds_running": amds_running,
        "amds_status": amds_status,
        "have_idevice_tools": have_idevice_tools,
        "have_irecovery": have_irecovery,
        "have_idevicerestore": have_idevicerestore,
        "missing_tools": missing_tools,
        "tools_checked": tool_list,
        "path": path_hint,
    }

    if amds_error:
        data["amds_error"] = amds_error

    if not have_irecovery:
        data["notes"] = "DFU/Recovery erfordert irecovery/libusb"

    return data
