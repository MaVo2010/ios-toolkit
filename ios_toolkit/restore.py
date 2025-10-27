from __future__ import annotations

import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Optional

from . import models, utils

log = utils.get_logger(__name__)


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _build_result(
    *,
    status: models.Status,
    udid: Optional[str],
    ipsw: Optional[str],
    wipe: bool,
    steps: Iterable[models.Step],
    logfile: Path,
    started_at: datetime,
    finished_at: datetime,
    duration: int,
) -> models.RestoreResult:
    return models.RestoreResult(
        status=status,
        udid=udid,
        ipsw=ipsw,
        wipe=wipe,
        steps=list(steps),
        logfile=str(logfile),
        started_at=started_at,
        finished_at=finished_at,
        duration_sec=duration,
    )


def restore(
    udid: Optional[str] = None,
    ipsw_path: Optional[str] = None,
    latest: bool = False,
    wipe: bool = True,
    keep_logs: bool = False,
) -> models.RestoreResult:
    started = datetime.now(UTC)
    log_path = Path("restore_log.txt").resolve()

    if latest and not ipsw_path:
        step = models.Step(name="resolve_latest_ipsw", ok=False, detail="latest requested without resolver")
        return _build_result(
            status="failure",
            udid=udid,
            ipsw=None,
            wipe=wipe,
            steps=[step],
            logfile=log_path,
            started_at=started,
            finished_at=datetime.now(UTC),
            duration=0,
        )

    if not ipsw_path or not Path(ipsw_path).exists():
        step = models.Step(name="validate_ipsw", ok=False, detail="missing or invalid IPSW path")
        return _build_result(
            status="failure",
            udid=udid,
            ipsw=ipsw_path,
            wipe=wipe,
            steps=[step],
            logfile=log_path,
            started_at=started,
            finished_at=datetime.now(UTC),
            duration=0,
        )

    if not _have("idevicerestore"):
        step = models.Step(name="check_idevicerestore", ok=False, detail="idevicerestore not found in PATH")
        return _build_result(
            status="failure",
            udid=udid,
            ipsw=ipsw_path,
            wipe=wipe,
            steps=[step],
            logfile=log_path,
            started_at=started,
            finished_at=datetime.now(UTC),
            duration=0,
        )

    cmd = ["idevicerestore", "-w" if wipe else "-r"]
    if udid:
        cmd += ["-u", udid]
    cmd.append(ipsw_path)

    log.info("Starting idevicerestore for %s", udid or "auto")
    t0 = time.time()
    rc = 1
    try:
        with log_path.open("w", encoding="utf-8") as fp:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            assert process.stdout is not None  # narrow type
            for line in process.stdout:
                fp.write(line)
            rc = process.wait()
    except Exception as exc:  # pragma: no cover - subprocess failures are environment-specific
        log.error("idevicerestore failed: %s", exc, exc_info=True)
    duration = int(time.time() - t0)
    finished = datetime.now(UTC)

    step = models.Step(name="idevicerestore", ok=(rc == 0))
    status: models.Status = "success" if rc == 0 else "failure"
    return _build_result(
        status=status,
        udid=udid,
        ipsw=ipsw_path,
        wipe=wipe,
        steps=[step],
        logfile=log_path,
        started_at=started,
        finished_at=finished,
        duration=duration,
    )
