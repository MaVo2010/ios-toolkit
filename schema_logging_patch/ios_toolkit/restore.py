from __future__ import annotations
import os, time, shutil, subprocess, datetime
from . import models
from .utils import get_logger

log = get_logger()

def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def restore(udid=None, ipsw_path=None, latest=False, wipe=True, keep_logs=False) -> models.RestoreResult:
    started = datetime.datetime.utcnow().isoformat()
    steps = []
    log_path = os.path.abspath("restore_log.txt")

    if latest and not ipsw_path:
        steps.append(models.Step(name="resolve_latest_ipsw", ok=False))
        return models.RestoreResult(
            status="failure",
            udid=udid,
            ipsw=None,
            wipe=wipe,
            steps=steps,
            logfile=log_path,
            started_at=started,
            finished_at=datetime.datetime.utcnow().isoformat(),
            duration_sec=0,
        )

    if not ipsw_path or not os.path.exists(ipsw_path):
        return models.RestoreResult(
            status="failure",
            udid=udid,
            ipsw=ipsw_path,
            wipe=wipe,
            steps=[models.Step(name="validate_ipsw", ok=False)],
            logfile=log_path,
            started_at=started,
            finished_at=datetime.datetime.utcnow().isoformat(),
            duration_sec=0,
        )

    if not _have("idevicerestore"):
        return models.RestoreResult(
            status="failure",
            udid=udid,
            ipsw=ipsw_path,
            wipe=wipe,
            steps=[models.Step(name="check_idevicerestore", ok=False)],
            logfile=log_path,
            started_at=started,
            finished_at=datetime.datetime.utcnow().isoformat(),
            duration_sec=0,
        )

    cmd = ["idevicerestore"]
    if wipe:
        cmd += ["-w"]
    else:
        cmd += ["-r"]
    if udid:
        cmd += ["-u", udid]
    cmd += [ipsw_path]

    t0 = time.time()
    rc = 1
    try:
        with open(log_path, "w", encoding="utf-8") as fp:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                fp.write(line)
            rc = proc.wait()
    except Exception as e:
        log.error(f"idevicerestore failed: {e}")

    finished = datetime.datetime.utcnow().isoformat()
    return models.RestoreResult(
        status="success" if rc == 0 else "failure",
        udid=udid,
        ipsw=ipsw_path,
        wipe=wipe,
        steps=[models.Step(name="idevicerestore", ok=(rc == 0))],
        logfile=log_path,
        started_at=started,
        finished_at=finished,
        duration_sec=int(time.time() - t0),
    )
