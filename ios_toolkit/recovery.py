from __future__ import annotations

import re
import shutil
import subprocess
from typing import Dict, Optional

from .utils import get_logger

log = get_logger(__name__)


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return cp.returncode, cp.stdout or "", cp.stderr or ""
    except Exception as exc:  # pragma: no cover - defensive
        log.error("Command failed %s: %s", cmd, exc)
        return 127, "", str(exc)


def parse_irecovery_q(text: str) -> str:
    """
    Heuristic parser for `irecovery -q` output. Handles MODE/DEVICE_STATE cases.
    """
    payload = text or ""
    if re.search(r"\bDFU\b", payload, re.IGNORECASE):
        return "dfu"
    if re.search(r"\bRecovery\b", payload, re.IGNORECASE):
        return "recovery"
    if re.search(r"\bNormal\b", payload, re.IGNORECASE):
        return "normal"
    return "unknown"


def enter(udid: Optional[str] = None) -> bool:
    """
    Attempt to enter recovery mode via `idevicediagnostics enter_recovery`.
    """
    if not _have("idevicediagnostics"):
        log.warning("idevicediagnostics not found; cannot enter recovery")
        return False

    cmd = ["idevicediagnostics", "enter_recovery"]
    if udid:
        cmd += ["-u", udid]

    log.info("Executing recovery enter command: %s", " ".join(cmd))
    rc, out, err = _run(cmd)
    if rc != 0:
        log.error("enter_recovery failed rc=%s out=%s err=%s", rc, out.strip(), err.strip())
        return False
    return True


def status(udid: Optional[str] = None) -> Dict[str, str]:
    """
    Query current mode using `irecovery -q`.
    """
    if not _have("irecovery"):
        log.warning("irecovery not found; status unavailable")
        return {"mode": "unknown", "tool_missing": True, "error": "irecovery not found"}

    cmd = ["irecovery", "-q"]
    if udid:
        cmd += ["-u", udid]

    log.debug("Executing recovery status command: %s", " ".join(cmd))
    rc, out, err = _run(cmd)
    if rc != 0:
        log.error("irecovery -q failed rc=%s err=%s", rc, err.strip())
        return {"mode": "unknown", "error": "irecovery -q failed", "stderr": err.strip()}

    mode = parse_irecovery_q(out)
    data: Dict[str, str] = {"mode": mode}
    if mode == "unknown":
        data["raw"] = out.strip()
    return data


def kickout(udid: Optional[str] = None) -> bool:
    """
    Attempt to exit recovery/DFU via `irecovery -n`.
    """
    if not _have("irecovery"):
        log.warning("irecovery not found; cannot kickout")
        return False

    cmd = ["irecovery", "-n"]
    if udid:
        cmd += ["-u", udid]

    log.info("Executing recovery kickout command: %s", " ".join(cmd))
    rc, out, err = _run(cmd)
    if rc != 0:
        log.error("irecovery -n failed rc=%s out=%s err=%s", rc, out.strip(), err.strip())
        return False
    return True
