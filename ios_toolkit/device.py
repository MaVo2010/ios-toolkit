from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

from . import models, utils
from .recovery import parse_irecovery_q

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

    parsed = parse_irecovery_q(result.stdout)
    return str(parsed.get("mode", "")).strip().lower() == "dfu"


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


def diag_usb() -> Dict[str, Any]:
    tools_to_check = [
        "idevice_id",
        "ideviceinfo",
        "idevicesyslog",
        "idevicecrashreport",
        "irecovery",
        "idevicerestore",
    ]

    def _query_amds_status() -> Dict[str, Any]:
        amds: Dict[str, Any] = {"running": False, "status": None, "error": None, "source": None}
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
                    amds["status"] = status
                    amds["running"] = status.upper() == "RUNNING"
                    amds["source"] = "powershell"
                    return amds
        except Exception as exc:  # pragma: no cover - PowerShell not available
            amds["error"] = str(exc)
            log.debug("PowerShell AMDS check failed: %s", exc)

        fallback = _call(["sc", "query", "Apple Mobile Device Service"], timeout=5)
        if fallback.code == 0 and fallback.stdout:
            status_text = fallback.stdout.strip()
            amds["status"] = status_text
            amds["running"] = "RUNNING" in status_text.upper()
            amds["source"] = "sc"
            if not amds.get("error"):
                amds["error"] = None
        else:
            fallback_error = fallback.stderr or (f"exit code {fallback.code}" if fallback.code else None)
            if fallback_error:
                amds["error"] = fallback_error if amds.get("error") is None else amds["error"]
        return amds

    def _probe_tool_version(executable: str) -> Optional[str]:
        for args in ([executable, "--version"], [executable, "-V"]):
            result = _call(args, timeout=5)
            text = (result.stdout or "").strip() or (result.stderr or "").strip()
            if text:
                return text.splitlines()[0][:200]
        return None

    def _collect_tools() -> Dict[str, Any]:
        entries: list[Dict[str, Any]] = []
        missing: list[str] = []
        for tool in tools_to_check:
            path = shutil.which(tool)
            entry: Dict[str, Any] = {"name": tool, "found": bool(path), "path": path, "version": None}
            if path:
                version = _probe_tool_version(path)
                if version:
                    entry["version"] = version
            else:
                missing.append(tool)
            entries.append(entry)
        return {"checked": tools_to_check, "entries": entries, "missing": missing}

    def _gather_usb_info(irecovery_available: bool) -> Dict[str, Any]:
        usb_info: Dict[str, Any] = {
            "irecovery_available": irecovery_available,
            "dfu_detected": False,
            "recovery_detected": False,
            "irecovery": None,
            "error": None,
        }
        if not irecovery_available:
            return usb_info

        result = _call(["irecovery", "-q"], timeout=5)
        if result.ok and result.stdout:
            parsed = parse_irecovery_q(result.stdout)
            usb_info["irecovery"] = parsed
            mode = str(parsed.get("mode", "")).strip().lower()
            if mode == "dfu":
                usb_info["dfu_detected"] = True
            if mode == "recovery":
                usb_info["recovery_detected"] = True
            device_state = parsed.get("device_state")
            if isinstance(device_state, str):
                lowered = device_state.lower()
                if "dfu" in lowered:
                    usb_info["dfu_detected"] = True
                if "recovery" in lowered:
                    usb_info["recovery_detected"] = True
        else:
            usb_info["error"] = result.stderr or "irecovery -q failed"
        return usb_info

    def _detect_apple_pnp() -> Dict[str, Any]:
        data: Dict[str, Any] = {"present": False, "raw": None, "error": None}
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-PnpDevice | Where-Object { $_.InstanceId -like 'USB\\\\VID_05AC*' } | "
            "Select-Object -First 1 | Out-String",
        ]
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            output = (completed.stdout or "").strip()
            data["raw"] = output or None
            if completed.returncode == 0:
                data["present"] = bool(output)
            else:
                data["error"] = (completed.stderr or "").strip() or f"exit code {completed.returncode}"
        except Exception as exc:  # pragma: no cover - PowerShell not available
            data["error"] = str(exc)
            log.debug("PowerShell PnP query failed: %s", exc)
        return data

    def _collect_host_info() -> Dict[str, Any]:
        path_value = os.environ.get("PATH", "")
        path_preview = path_value if len(path_value) <= 120 else f"{path_value[:117]}..."
        host: Dict[str, Any] = {
            "path_preview": path_preview,
            "path_length": len(path_value),
        }
        try:
            anchor = Path.cwd().anchor or str(Path.cwd().resolve())
            usage = shutil.disk_usage(anchor)
            host["disk_free_gb"] = round(usage.free / (1024**3), 2)
        except Exception as exc:  # pragma: no cover - not expected
            host["disk_free_gb"] = None
            host["disk_error"] = str(exc)

        pnp_info = _detect_apple_pnp()
        host["apple_pnp_present"] = pnp_info["present"]
        if pnp_info.get("raw"):
            host["apple_pnp_sample"] = pnp_info["raw"]
        if pnp_info.get("error"):
            host["apple_pnp_error"] = pnp_info["error"]
        return host

    def _build_hints(
        amds_info: Dict[str, Any], tools_info: Dict[str, Any], usb_info: Dict[str, Any], host_info: Dict[str, Any]
    ) -> list[str]:
        hints: list[str] = []
        if tools_info["missing"]:
            hints.append(
                "Fehlende Tools: "
                + ", ".join(tools_info["missing"])
                + " - bitte libimobiledevice/irecovery installieren."
            )
        if not amds_info.get("running"):
            hints.append("Apple Mobile Device Service laeuft nicht; starte den Dienst oder installiere iTunes.")
        if usb_info.get("dfu_detected"):
            hints.append("DFU erkannt: 'list' zeigt DFU i. d. R. nicht; nutze 'recovery status' oder '--include-dfu'.")
        elif usb_info.get("recovery_detected"):
            hints.append("Recovery-Modus erkannt: pruefe 'recovery status' fuer weitere Details.")
        if not host_info.get("apple_pnp_present"):
            hints.append("Keine Apple USB-Geraete via PnP gefunden; pruefe Kabel und USB-Port.")

        # Deduplicate while keeping order
        unique_hints: list[str] = []
        seen: set[str] = set()
        for hint in hints:
            if hint not in seen:
                unique_hints.append(hint)
                seen.add(hint)
        return unique_hints

    amds_info = _query_amds_status()
    tools_info = _collect_tools()
    host_info = _collect_host_info()
    usb_info = _gather_usb_info(any(entry["found"] for entry in tools_info["entries"] if entry["name"] == "irecovery"))
    hints = _build_hints(amds_info, tools_info, usb_info, host_info)

    return {
        "amds": amds_info,
        "tools": tools_info,
        "usb": usb_info,
        "host": host_info,
        "hints": hints,
    }
