from __future__ import annotations

import shutil
import subprocess

def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def _call(cmd, timeout=15):
    try:
        out = subprocess.check_output(cmd, timeout=timeout, stderr=subprocess.STDOUT, text=True)
        return True, out
    except Exception as e:
        return False, str(e)

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
    if _have("irecovery"):
        cmd = ["irecovery", "-q"]
        ok, out = _call(cmd)
        if ok and out:
            # heuristisch
            if "DEVICE_STATE" in out and "Recovery" in out:
                mode = "recovery"
            elif "MODE" in out and "DFU" in out:
                mode = "dfu"
            else:
                mode = "recovery" if "CPID" in out else "unknown"
    return {"mode": mode}

def kickout(udid=None) -> bool:
    if _have("irecovery"):
        ok, _ = _call(["irecovery", "-n"])
        return ok
    return False
