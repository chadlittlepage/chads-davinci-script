"""Console logging — captures stdout/stderr to a file for crash reports.

Features:
  - Tees stdout + stderr to console.log so the user can export it via
    Help → Export Console Log… and email it to support.
  - Auto-rotates the log on session start when it gets too old or too
    big, so the file never grows unbounded:
      * Older than 30 days → archived to console.log.old (one backup)
      * Larger than 10 MB → tail-truncated to last 5 MB

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

from chads_davinci.paths import APP_SUPPORT_DIR

LOG_DIR = APP_SUPPORT_DIR / "logs"
LOG_PATH = LOG_DIR / "console.log"

# Rotation thresholds — tweak here if support feedback says they're wrong.
LOG_MAX_AGE_DAYS = 30
LOG_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_TRUNCATE_TO_BYTES = 5 * 1024 * 1024  # keep last 5 MB on size rotation


def _rotate_log_if_needed() -> None:
    """Inspect the existing log and rotate it if it's too old or too big.
    Never raises — log rotation is best-effort and must not block app
    startup."""
    try:
        if not LOG_PATH.exists():
            return
        stat = LOG_PATH.stat()
        # Age check: if older than LOG_MAX_AGE_DAYS, archive and start fresh.
        age_days = (time.time() - stat.st_mtime) / 86400
        if age_days > LOG_MAX_AGE_DAYS:
            backup = LOG_PATH.with_suffix(".log.old")
            try:
                if backup.exists():
                    backup.unlink()
                LOG_PATH.rename(backup)
            except Exception:
                # Last resort: truncate in place
                try:
                    LOG_PATH.write_text("", encoding="utf-8")
                except Exception:
                    pass
            return
        # Size check: if too big, keep only the trailing N bytes.
        if stat.st_size > LOG_MAX_SIZE_BYTES:
            try:
                with LOG_PATH.open("rb") as f:
                    f.seek(-LOG_TRUNCATE_TO_BYTES, 2)  # from end
                    f.readline()  # discard partial line
                    tail = f.read()
                LOG_PATH.write_bytes(
                    b"=== log truncated (rolling 5 MB cap) ===\n" + tail
                )
            except Exception:
                pass
    except Exception:
        # Never let log-rotation failures break setup_logging
        pass


class _Tee:
    """File-like object that writes to multiple streams.

    The terminal stream(s) get the original bytes verbatim. The log file
    stream gets a `[HH:MM:SS.mmm] ` prefix at the start of every line so
    timing analysis is possible from an exported log without needing the
    user to wall-clock-time anything.
    """

    def __init__(self, *streams, log_stream=None):
        self._streams = streams
        self._log_stream = log_stream
        self._log_at_line_start = True

    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass
        if self._log_stream is not None:
            self._write_log(data)

    def _write_log(self, data):
        try:
            now = datetime.now()
            ms = now.microsecond // 1000
            stamp = now.strftime(f"[%H:%M:%S.{ms:03d}] ")
            # Walk the chunk and prepend the timestamp at every line start.
            i = 0
            n = len(data)
            while i < n:
                if self._log_at_line_start:
                    self._log_stream.write(stamp)
                    self._log_at_line_start = False
                nl = data.find("\n", i)
                if nl == -1:
                    self._log_stream.write(data[i:])
                    break
                self._log_stream.write(data[i:nl + 1])
                self._log_at_line_start = True
                i = nl + 1
            self._log_stream.flush()
        except Exception:
            pass

    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass
        if self._log_stream is not None:
            try:
                self._log_stream.flush()
            except Exception:
                pass

    def isatty(self):
        return False


def setup_logging() -> None:
    """Redirect stdout/stderr to both terminal AND a log file.
    Rotates the log first if it's older than 30 days or larger than 10 MB."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Rotate stale / oversized logs before opening for append.
    _rotate_log_if_needed()

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

    # Tee stdout/stderr to terminal verbatim AND timestamped to the log
    sys.stdout = _Tee(sys.__stdout__, log_stream=log_file)
    sys.stderr = _Tee(sys.__stderr__, log_stream=log_file)


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
