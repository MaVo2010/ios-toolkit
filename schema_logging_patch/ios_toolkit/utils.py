from __future__ import annotations
import logging, os, re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime

_LOGGER_NAME = "ios_toolkit"
_UDID_RE = re.compile(r"\b[a-fA-F0-9]{40}\b")

class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        return _UDID_RE.sub("<UDID>", msg)

def configure_logging(log_dir: Path, verbose: bool = False) -> Path:
    """Globales Logging initialisieren. Rotierende Logdateien in log_dir."""
    os.environ["PYTHONUTF8"] = "1"  # Windows: UTF-8 i/o
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"session-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.log"

    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return log_path

    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    fmt = _RedactingFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    fh = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return log_path

def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)
