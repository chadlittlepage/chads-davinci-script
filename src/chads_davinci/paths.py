"""Sandbox-friendly application support paths.

All persistent state lives under ~/Library/Application Support/Chads DaVinci Script/
which is the only home-directory location an App-Sandbox / Hardened-Runtime app
can write to without extra entitlements.

Includes a one-shot migration from the legacy ~/.chads-davinci/ location.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import shutil
from pathlib import Path

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "Chads DaVinci Script"
LEGACY_DIR = Path.home() / ".chads-davinci"


def ensure_app_support_dir() -> Path:
    """Create the app support dir if needed and migrate legacy data once."""
    APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    _migrate_legacy()
    return APP_SUPPORT_DIR


def _migrate_legacy() -> None:
    """Copy legacy ~/.chads-davinci/* into the new location if not already present."""
    if not LEGACY_DIR.exists():
        return
    try:
        for entry in LEGACY_DIR.iterdir():
            target = APP_SUPPORT_DIR / entry.name
            if target.exists():
                continue
            if entry.is_dir():
                shutil.copytree(entry, target)
            else:
                shutil.copy2(entry, target)
    except Exception:
        # Migration is best-effort; silent failure is OK because the app
        # will simply start with empty state.
        pass


# Convenience helpers used throughout the codebase.
def app_support_path(*parts: str) -> Path:
    """Return APP_SUPPORT_DIR / parts (joined). Does NOT create parents."""
    p = APP_SUPPORT_DIR
    for part in parts:
        p = p / part
    return p


# Eagerly run the migration the first time this module is imported so every
# downstream module sees the new location populated.
ensure_app_support_dir()
