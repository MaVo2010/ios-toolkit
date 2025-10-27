from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_LOGGER_NAME = "ios_toolkit"
_UDID_PATTERN = re.compile(r"\b[a-fA-F0-9]{8,40}\b")


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        return _UDID_PATTERN.sub("<UDID>", rendered)


def configure_logging(log_dir: Path | str, verbose: bool = False) -> Path:
    """
    Configure process-wide logging with rotating file handlers.

    Returns the path to the active session log file. Subsequent calls return the
    same file without reconfiguring handlers.
    """
    os.environ.setdefault("PYTHONUTF8", "1")
    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / f"session-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.log"

    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return log_path

    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    formatter = _RedactingFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return log_path


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Return a configured child logger. Defaults to the toolkit root logger.
    """
    if name:
        return logging.getLogger(f"{_LOGGER_NAME}.{name}")
    return logging.getLogger(_LOGGER_NAME)
