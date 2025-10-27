from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Optional

from . import ipsw as ipsw_utils
from . import models, utils

log = utils.get_logger(__name__)

# Regex patterns mapped to logical restore steps; match only once per run.
STEP_PATTERNS = [
    ("extract", re.compile(r"\bextract", re.IGNORECASE)),
    ("send_restore_image", re.compile(r"Sending\s+RestoreImage", re.IGNORECASE)),
    ("restore", re.compile(r"\brestore\b", re.IGNORECASE)),
    ("flash", re.compile(r"flashing", re.IGNORECASE)),
    ("verify", re.compile(r"verif", re.IGNORECASE)),
    ("reboot", re.compile(r"reboot", re.IGNORECASE)),
    ("wipe", re.compile(r"wipe|erase", re.IGNORECASE)),
]

# Validation-oriented step names used to detect exit-code 2 in the CLI.
VALIDATION_STEPS = {
    "check_idevicerestore",
    "ipsw_exists",
    "ipsw_validated",
    "disk_free_gb",
    "preflight",
    "resolve_latest_ipsw",
}

# Optional checks do not contribute to overall preflight ok-state.
OPTIONAL_CHECKS = {"amds_running", "device_info"}


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


def _format_detail(entry: dict) -> Optional[str]:
    detail_keys = ("error", "detail", "path", "value", "suffix", "size", "threshold")
    parts = []
    for key in detail_keys:
        if key in entry and entry[key] not in (None, ""):
            parts.append(f"{key}={entry[key]}")
    return ", ".join(parts) if parts else None


def _sanitize_udid(value: Optional[str]) -> str:
    if not value:
        return "unknown"
    return re.sub(r"[^\w.-]", "_", value)


def _compose_log_path(udid: Optional[str], base_dir: Optional[str], timestamp: str) -> Path:
    base = Path(base_dir) if base_dir else Path("logs")
    return (base / _sanitize_udid(udid) / f"restore-{timestamp}.log").resolve()


def preflight_checks(
    udid: Optional[str],
    ipsw_path: Optional[str],
    min_disk_gb: int = 10,
    log_dir: Optional[str] = None,
) -> dict:
    """
    Perform local checks before running idevicerestore.
    Returns summary with `ok`, `checks` (list of dicts) and `errors`.
    """
    checks: list[dict] = []
    errors: list[dict] = []

    def add_check(name: str, ok: bool, **info) -> None:
        entry = {"name": name, "ok": bool(ok)}
        entry.update({k: v for k, v in info.items() if v is not None})
        checks.append(entry)
        if not ok and name not in OPTIONAL_CHECKS:
            errors.append({"name": name, "message": info.get("error") or info.get("detail") or ""})

    have_restore = _have("idevicerestore")
    add_check("check_idevicerestore", have_restore)

    ipsw = Path(ipsw_path) if ipsw_path else None
    if ipsw is None:
        add_check("ipsw_exists", False, error="no IPSW path provided")
    else:
        exists = ipsw.exists()
        add_check("ipsw_exists", exists, path=str(ipsw))
        if exists:
            validation = ipsw_utils.validate_ipsw(str(ipsw))
            add_check(
                "ipsw_validated",
                validation["ok"],
                sha1=validation.get("sha1"),
                size=validation.get("size"),
                has_manifest=validation.get("has_manifest"),
                error=validation.get("error"),
            )
            if validation["ok"] and validation.get("sha1"):
                log.info("Validated IPSW %s sha1=%s", ipsw, validation["sha1"])
        else:
            add_check("ipsw_validated", False, error="IPSW not found")

    disk_target = Path(log_dir) if log_dir else Path.cwd()
    try:
        usage = shutil.disk_usage(disk_target)
        free_gb = usage.free / (1024 ** 3)
        disk_ok = free_gb >= min_disk_gb
        add_check(
            "disk_free_gb",
            disk_ok,
            value=round(free_gb, 2),
            threshold=min_disk_gb,
            error=None if disk_ok else f"free space {free_gb:.1f}GB below minimum {min_disk_gb}GB",
        )
    except Exception as exc:  # pragma: no cover - depends on platform specifics
        log.warning("Failed to query disk usage: %s", exc)
        add_check("disk_free_gb", False, error=str(exc))

    # Optional: Apple Mobile Device Service status.
    try:
        cmd = ["sc", "query", "Apple Mobile Device Service"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        running = "RUNNING" in (result.stdout or "").upper()
        add_check("amds_running", running, detail="running" if running else "stopped")
    except Exception as exc:  # pragma: no cover - environment specific
        log.debug("AMDS check failed: %s", exc)
        add_check("amds_running", False, error=str(exc))

    # Optional: current device info (best effort).
    device_info = None
    if udid:
        try:
            from . import device

            info = device.get_info(udid=udid, allow_discovery=False)
            if info:
                device_info = {
                    "product_type": (
                        info.product_type if hasattr(info, "product_type") else info.get("product_type")
                    ),
                    "product_version": (
                        info.product_version if hasattr(info, "product_version") else info.get("product_version")
                    ),
                }
        except Exception as exc:  # pragma: no cover
            log.debug("Device info lookup failed: %s", exc)
    add_check("device_info", bool(device_info), detail=device_info)

    overall_ok = all(entry["ok"] for entry in checks if entry["name"] not in OPTIONAL_CHECKS)
    return {"ok": overall_ok, "checks": checks, "errors": errors}


def _compose_command(
    *,
    udid: Optional[str],
    ipsw_path: str,
    wipe: bool,
) -> list[str]:
    cmd = ["idevicerestore"]
    cmd.append("-w" if wipe else "-r")
    if udid:
        cmd += ["-u", udid]
    cmd.append(ipsw_path)
    return cmd


def _stream_process_output(
    process: subprocess.Popen,
    log_file,
    progress_steps: list[models.Step],
    seen_steps: set[str],
) -> None:
    assert process.stdout is not None
    for line in iter(process.stdout.readline, ""):
        log_file.write(line)
        log_file.flush()
        for name, pattern in STEP_PATTERNS:
            if name not in seen_steps and pattern.search(line):
                progress_steps.append(models.Step(name=name, ok=True))
                seen_steps.add(name)
        log.debug("idevicerestore: %s", line.rstrip())


def is_validation_failure(result: models.RestoreResult) -> bool:
    """
    Determine whether the restore outcome represents a validation failure (tool missing, invalid input, etc.).
    """
    for step in result.steps:
        if step.name in VALIDATION_STEPS and not step.ok:
            return True
    return False


def restore(
    udid: Optional[str] = None,
    ipsw_path: Optional[str] = None,
    latest: bool = False,
    wipe: bool = True,
    keep_logs: bool = False,
    preflight_only: bool = False,
    dry_run: bool = False,
    timeout_sec: Optional[int] = None,
    log_dir: Optional[str] = None,
) -> models.RestoreResult:
    started = datetime.now(UTC)
    timestamp = started.strftime("%Y%m%d-%H%M%S")
    log_path = _compose_log_path(udid, log_dir, timestamp)

    steps: list[models.Step] = []

    if latest:
        steps.append(models.Step(name="resolve_latest_ipsw", ok=False, detail="--latest is not implemented"))
        finished = datetime.now(UTC)
        return _build_result(
            status="failure",
            udid=udid,
            ipsw=ipsw_path,
            wipe=wipe,
            steps=steps,
            logfile=log_path,
            started_at=started,
            finished_at=finished,
            duration=0,
        )

    preflight = preflight_checks(udid, ipsw_path, log_dir=log_dir)
    for entry in preflight["checks"]:
        steps.append(models.Step(name=entry["name"], ok=entry["ok"], detail=_format_detail(entry)))
    steps.append(
        models.Step(
            name="preflight",
            ok=preflight["ok"],
            detail="; ".join(err["name"] for err in preflight["errors"]) if not preflight["ok"] else None,
        )
    )

    finished = datetime.now(UTC)
    if preflight_only:
        status: models.Status = "success" if preflight["ok"] else "failure"
        return _build_result(
            status=status,
            udid=udid,
            ipsw=ipsw_path,
            wipe=wipe,
            steps=steps,
            logfile=log_path,
            started_at=started,
            finished_at=finished,
            duration=int((finished - started).total_seconds()),
        )

    if not preflight["ok"]:
        return _build_result(
            status="failure",
            udid=udid,
            ipsw=ipsw_path,
            wipe=wipe,
            steps=steps,
            logfile=log_path,
            started_at=started,
            finished_at=finished,
            duration=int((finished - started).total_seconds()),
        )

    assert ipsw_path is not None
    cmd = _compose_command(udid=udid, ipsw_path=ipsw_path, wipe=wipe)

    if dry_run:
        steps.append(models.Step(name="compose_cmd", ok=True, detail=" ".join(cmd)))
        finished = datetime.now(UTC)
        return _build_result(
            status="success",
            udid=udid,
            ipsw=ipsw_path,
            wipe=wipe,
            steps=steps,
            logfile=log_path,
            started_at=started,
            finished_at=finished,
            duration=int((finished - started).total_seconds()),
        )

    log_path.parent.mkdir(parents=True, exist_ok=True)

    log.info("Starting idevicerestore for %s | cmd=%s", udid or "auto", " ".join(cmd))
    t0 = time.time()
    progress_steps: list[models.Step] = []
    seen_step_names: set[str] = set()
    rc = 1
    timeout_occurred = False

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as exc:  # pragma: no cover - environment specific
        log.error("idevicerestore failed to start: %s", exc, exc_info=True)
        steps.append(models.Step(name="idevicerestore", ok=False, detail=str(exc)))
        finished = datetime.now(UTC)
        return _build_result(
            status="failure",
            udid=udid,
            ipsw=ipsw_path,
            wipe=wipe,
            steps=steps,
            logfile=log_path,
            started_at=started,
            finished_at=finished,
            duration=int((finished - started).total_seconds()),
        )

    assert process.stdout is not None
    with log_path.open("w", encoding="utf-8") as fp:
        stream_thread = threading.Thread(
            target=_stream_process_output,
            args=(process, fp, progress_steps, seen_step_names),
            daemon=True,
        )
        stream_thread.start()

        try:
            rc = process.wait(timeout=timeout_sec) if timeout_sec else process.wait()
        except subprocess.TimeoutExpired:
            timeout_occurred = True
            log.error("idevicerestore timed out after %s seconds", timeout_sec)
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                process.kill()
        finally:
            stream_thread.join(timeout=5)

    duration = int(time.time() - t0)
    finished = datetime.now(UTC)

    steps.extend(progress_steps)

    if timeout_occurred:
        steps.append(models.Step(name="timeout", ok=False, detail=f"{timeout_sec}s"))
        rc = 1 if rc == 0 else rc

    steps.append(models.Step(name="idevicerestore", ok=(rc == 0), detail=f"rc={rc}"))

    status: models.Status = "success" if rc == 0 else "failure"

    if status == "success" and not keep_logs:
        log.info("Restore completed successfully. Logfile at %s", log_path)
    elif status != "success":
        log.error("Restore failed rc=%s. Logfile at %s", rc, log_path)

    return _build_result(
        status=status,
        udid=udid,
        ipsw=ipsw_path,
        wipe=wipe,
        steps=steps,
        logfile=log_path,
        started_at=started,
        finished_at=finished,
        duration=duration,
    )
