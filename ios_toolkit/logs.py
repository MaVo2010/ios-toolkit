from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time

def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def stream_syslog(udid=None, save_path=None, filter_expr=None, duration=None):
    """
    Fallback-Implementierung: idevicesyslog (wenn vorhanden).
    Agent kann dies später auf pymobiledevice3 (Python API) umstellen.
    """
    if not _have("idevicesyslog"):
        print("idevicesyslog nicht gefunden. Bitte libimobiledevice installieren.", file=sys.stderr)
        return 2

    cmd = ["idevicesyslog"]
    if udid:
        cmd += ["-u", udid]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    start = time.time()
    fp = open(save_path, "a", encoding="utf-8") if save_path else None
    regex = re.compile(filter_expr) if filter_expr else None
    try:
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            if (regex is None) or regex.search(line):
                sys.stdout.write(line)
                sys.stdout.flush()
                if fp:
                    fp.write(line)
            if duration and (time.time() - start) >= duration:
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        if fp:
            fp.close()
    return 0
