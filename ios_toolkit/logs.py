from __future__ import annotations
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from .utils import get_logger

log = get_logger()


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def stream_syslog(
    udid: Optional[str] = None,
    save_path: Optional[str] = None,
    filter_expr: Optional[str] = None,
    duration: Optional[int] = None,
) -> int:
    """
    Stream iOS syslog through `idevicesyslog`.
    Exit codes: 0=success, 2=tool missing, 1=unexpected error.
    """
    if not _have("idevicesyslog"):
        print("idevicesyslog nicht gefunden. Bitte libimobiledevice installieren.", file=sys.stderr)
        return 2

    cmd: List[str] = ["idevicesyslog"]
    if udid:
        cmd += ["-u", udid]

    # Save-File vorbereiten
    fp = None
    if save_path:
        out_path = Path(save_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fp = out_path.open("a", encoding="utf-8")

    regex = re.compile(filter_expr) if filter_expr else None

    log.info(f"Starting syslog: {' '.join(cmd)} | save={bool(save_path)} | filter={filter_expr} | duration={duration}")
    start = time.monotonic()

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as e:
        log.error(f"Failed to start idevicesyslog: {e}")
        if fp:
            fp.close()
        return 1

    rc = 0
    try:
        while True:
            line = proc.stdout.readline() if proc.stdout else ""
            if not line:
                if proc.poll() is not None:
                    break
                # Kein Output: kurze Pause um Busy-Wait zu vermeiden
                time.sleep(0.02)
                continue

            # Filter optional anwenden
            if regex is None or regex.search(line):
                sys.stdout.write(line)
                sys.stdout.flush()
                if fp:
                    fp.write(line)

            if duration is not None and duration >= 0 and (time.monotonic() - start) >= duration:
                log.info("Syslog duration reached, stopping.")
                break
    except KeyboardInterrupt:
        log.info("Syslog interrupted by user (Ctrl+C).")
        rc = 0
    except Exception as e:
        log.exception(f"Syslog streaming error: {e}")
        rc = 1
    finally:
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()
        except Exception:
            pass
        if fp:
            fp.close()

    return rc


def export_crashlogs(
    udid: Optional[str],
    out_dir: str,
    limit: Optional[int] = 20,
) -> Dict[str, Any]:
    """
    Export crash logs, primarily via `idevicecrashreport` if available.
    Returns a dict: {"exported": [...], "skipped": int, "source": "idevicecrashreport"}.

    Raises RuntimeError on failure (the CLI maps this to exit codes).
    """
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)

    exported: List[str] = []

    if _have("idevicecrashreport"):
        # idevicecrashreport [--udid UDID] [--extract] <dir>
        cmd = ["idevicecrashreport"]
        if udid:
            cmd += ["-u", udid]
        cmd += ["-e", str(target)]

        log.info(f"Running crash export: {' '.join(cmd)}")
        try:
            cp = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except Exception as e:
            log.error(f"idevicecrashreport failed to start: {e}")
            raise RuntimeError("idevicecrashreport could not be started") from e

        if cp.returncode != 0:
            log.error(f"idevicecrashreport rc={cp.returncode} | stdout={cp.stdout} | stderr={cp.stderr}")
            raise RuntimeError(f"idevicecrashreport failed (rc={cp.returncode})." )

        # Scan directory and trim to requested limit (newest first)
        files = sorted((p for p in target.glob("**/*") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
        total = len(files)
        if limit is not None:
            files = files[: max(0, limit)]
        exported = [str(p) for p in files]
        skipped = max(0, total - len(files))
        return {"exported": exported, "skipped": skipped, "source": "idevicecrashreport"}
    else:
        msg = "idevicecrashreport is not available. Please install libimobiledevice or implement an AFC export."
        log.warning(msg)
        raise RuntimeError(msg)
