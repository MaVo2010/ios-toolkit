from __future__ import annotations

import shutil
import subprocess
from typing import Dict, Any

def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def _call(cmd, timeout=15):
    try:
        out = subprocess.check_output(cmd, timeout=timeout, stderr=subprocess.STDOUT, text=True)
        return True, out
    except Exception as e:
        return False, str(e)


def parse_irecovery_q(output: str) -> Dict[str, Any]:
    """
    Parse the `irecovery -q` output into a structured payload.
    Returns a dict with `raw` values and a best-effort `mode`.
    """
    raw: Dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        raw[key.strip()] = value.strip()

    mode_value = raw.get("MODE") or raw.get("Mode") or raw.get("mode")
    device_state = raw.get("DEVICE_STATE") or raw.get("DeviceState")
    normalized_mode = "unknown"

    def _contains(text: str | None, needle: str) -> bool:
        return bool(text and needle.lower() in text.strip().lower())

    if _contains(mode_value, "dfu"):
        normalized_mode = "dfu"
    elif _contains(mode_value, "recovery"):
        normalized_mode = "recovery"
    elif _contains(device_state, "dfu"):
        normalized_mode = "dfu"
    elif _contains(device_state, "recovery"):
        normalized_mode = "recovery"
    elif "CPID" in raw and "SRNM" in raw:
        normalized_mode = "recovery"

    return {"raw": raw, "mode": normalized_mode, "device_state": device_state}

def enter(udid=None) -> bool:
    """
    Best-Effort: idevicediagnostics enter_recovery (falls vorhanden).
    """
    if _have("idevicediagnostics"):
        cmd = ["idevicediagnostics", "enter_recovery"]
        if udid:
            cmd += ["-u", udid]
        ok, _ = _call(cmd)
        return ok
    return False

def status(udid=None):
    """
    Sehr rudimentär: nutzt irecovery -q, falls vorhanden.
    Agent soll hier USB Product IDs/States verbessern.
    """
    mode = "unknown"
    details = {}
    if _have("irecovery"):
        cmd = ["irecovery", "-q"]
        ok, out = _call(cmd)
        if ok and out:
            parsed = parse_irecovery_q(out)
            mode = parsed.get("mode", "unknown")
            details = parsed.get("raw", {})
    return {"mode": mode, "details": details}

def kickout(udid=None) -> bool:
    if _have("irecovery"):
        ok, _ = _call(["irecovery", "-n"])
        return ok
    return False
