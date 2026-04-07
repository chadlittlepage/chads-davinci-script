"""Console logging — captures stdout/stderr to a file for crash reports.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from chads_davinci.paths import APP_SUPPORT_DIR

LOG_DIR = APP_SUPPORT_DIR / "logs"
LOG_PATH = LOG_DIR / "console.log"


class _Tee:
    """File-like object that writes to multiple streams."""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass

    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass

    def isatty(self):
        return False


def setup_logging() -> None:
    """Redirect stdout/stderr to both terminal AND a log file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Open log file in append mode
    try:
        log_file = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    except Exception:
        return

    # Write a session header
    log_file.write(f"\n{'=' * 70}\n")
    log_file.write(f"Session started: {datetime.now().isoformat()}\n")
    log_file.write(f"{'=' * 70}\n")
    log_file.flush()

    # Tee stdout/stderr to both original and log file
    sys.stdout = _Tee(sys.__stdout__, log_file)
    sys.stderr = _Tee(sys.__stderr__, log_file)


def get_log_path() -> Path:
    """Return the current log file path."""
    return LOG_PATH


def get_recent_log(max_bytes: int = 200_000) -> str:
    """Return the last N bytes of the console log."""
    if not LOG_PATH.exists():
        return ""
    try:
        size = LOG_PATH.stat().st_size
        with LOG_PATH.open("rb") as f:
            if size > max_bytes:
                f.seek(-max_bytes, 2)  # seek from end
                # Skip to next line
                f.readline()
            return f.read().decode("utf-8", errors="replace")
    except Exception:
        return ""
