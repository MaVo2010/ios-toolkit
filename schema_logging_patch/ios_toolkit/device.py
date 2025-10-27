from __future__ import annotations
import shutil
import subprocess
from typing import List, Optional

from . import models
from .utils import get_logger

log = get_logger()

def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def _call(cmd, timeout=10) -> str:
    try:
        out = subprocess.check_output(cmd, timeout=timeout, stderr=subprocess.STDOUT)
        return out.decode(errors="ignore")
    except Exception as e:
        log.debug(f"Subprocess failed: {cmd} ({e})")
        return ""

def list_devices() -> List[models.Device]:
    """Primär: idevice_id -l (Fallback); Agent kann später pymobiledevice3 direkt nutzen."""
    devices: List[models.Device] = []
    if _have("idevice_id"):
        out = _call(["idevice_id", "-l"])
        for line in out.splitlines():
            udid = line.strip()
            if not udid:
                continue
            info = get_info(udid)
            if info is None:
                info = models.Device(udid=udid)
            devices.append(info)
    return devices

def get_info(udid: Optional[str] = None) -> Optional[models.Device]:
    """Nutzt ideviceinfo, wenn vorhanden. Liefert ein Device-Modell oder None."""
    if not _have("ideviceinfo"):
        return None
    cmd = ["ideviceinfo"]
    if udid:
        cmd += ["-u", udid]
    out = _call(cmd)
    if not out:
        return None
    data = {}
    for line in out.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip()

    return models.Device(
        udid=data.get("UniqueDeviceID") or udid or "",
        product_type=data.get("ProductType"),
        product_version=data.get("ProductVersion"),
        device_name=data.get("DeviceName"),
        connection="usb",
        mode="unknown",
    )

def diag_usb():
    data = {
        "amds_running": False,
        "have_idevice_tools": False,
        "have_irecovery": False,
        "have_idevicerestore": False,
    }
    try:
        out = _call(["sc", "query", "Apple Mobile Device Service"], timeout=5)
        data["amds_running"] = "RUNNING" in out.upper()
    except Exception:
        data["amds_running"] = False
    data["have_idevice_tools"] = _have("idevice_id") and _have("ideviceinfo")
    data["have_irecovery"] = _have("irecovery")
    data["have_idevicerestore"] = _have("idevicerestore")
    return data
