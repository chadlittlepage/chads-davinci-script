"""User settings export/import — backup and restore all picker defaults.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from chads_davinci.paths import APP_SUPPORT_DIR

USER_SETTINGS_PATH = APP_SUPPORT_DIR / "user_settings.json"
BIN_STRUCTURE_PATH = APP_SUPPORT_DIR / "bin_structure.json"
PRESETS_PATH = APP_SUPPORT_DIR / "presets.json"


def load_presets() -> dict:
    """Load named presets dict {name: settings_dict}. Empty if missing."""
    if not PRESETS_PATH.exists():
        return {}
    try:
        data = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_presets(presets: dict) -> None:
    PRESETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRESETS_PATH.write_text(json.dumps(presets, indent=2, ensure_ascii=False), encoding="utf-8")


def save_preset(name: str, settings: dict) -> None:
    presets = load_presets()
    presets[name] = settings
    save_presets(presets)


def delete_preset(name: str) -> None:
    presets = load_presets()
    if name in presets:
        del presets[name]
        save_presets(presets)


# Factory defaults for picker form values
DEFAULT_SETTINGS = {
    "track_names": {
        "REEL_SOURCE": "REEL SOURCE",
        "HW2_300_NIT": "HW2 300 nit",
        "L1SHW_300": "L1SHW 300",
        "HW2_795_STRETCH_1500": "HW2 795 Stretch 1500",
        "L1SHW_795_STRETCH_1500": "L1SHW 795 Stretch 1500",
        "L1SHW_HDMI": "L1SHW HDMI",
    },
    "folder_name": "Quad Projects",
    "project_name": "Quad Project v001",
    "source_resolution": "3840x2160 UHD (timeline 8K)",
    "frame_rate": "23.976",
    "start_timecode": "00:00:00:00",
    "timeline_color_space": "Rec.2100 ST2084",
    "output_color_space": "Rec.2100 ST2084",
    "use_mediainfo": True,
    "use_ffprobe": True,
    "report_format": "None",
    "marker_option": "None",
}


def reset_user_settings() -> None:
    """Delete the user settings and bin structure files (revert to factory defaults)."""
    if USER_SETTINGS_PATH.exists():
        USER_SETTINGS_PATH.unlink()
    if BIN_STRUCTURE_PATH.exists():
        BIN_STRUCTURE_PATH.unlink()


def load_user_settings() -> dict:
    """Load user picker defaults from disk. Returns empty dict if not present."""
    if not USER_SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(USER_SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_user_settings(data: dict) -> None:
    """Persist user picker defaults to disk."""
    USER_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_SETTINGS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def collect_settings_bundle() -> dict:
    """Build a complete settings bundle for export."""
    bundle = {
        "version": 1,
        "exported": datetime.now().isoformat(),
        "user_settings": load_user_settings(),
    }

    # Include bin structure if it exists
    if BIN_STRUCTURE_PATH.exists():
        try:
            bundle["bin_structure"] = json.loads(BIN_STRUCTURE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    return bundle


def apply_settings_bundle(bundle: dict) -> tuple[bool, str]:
    """Apply an imported settings bundle. Returns (success, message)."""
    if not isinstance(bundle, dict):
        return False, "Invalid settings file (not a JSON object)"

    if "version" not in bundle:
        return False, "Invalid settings file (missing version)"

    # Apply user_settings if present
    if "user_settings" in bundle and isinstance(bundle["user_settings"], dict):
        save_user_settings(bundle["user_settings"])

    # Apply bin_structure if present
    if "bin_structure" in bundle:
        BIN_STRUCTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BIN_STRUCTURE_PATH.write_text(
            json.dumps(bundle["bin_structure"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return True, "Settings imported successfully"


def export_to_file(target_path: Path | str) -> Path:
    """Export the current settings bundle to the given file path."""
    target = Path(target_path)
    bundle = collect_settings_bundle()
    target.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def import_from_file(source_path: Path | str) -> tuple[bool, str]:
    """Import a settings bundle from a JSON file."""
    source = Path(source_path)
    if not source.exists():
        return False, f"File not found: {source}"
    try:
        bundle = json.loads(source.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"Failed to parse JSON: {e}"
    return apply_settings_bundle(bundle)
