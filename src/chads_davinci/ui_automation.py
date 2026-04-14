"""macOS UI automation for DaVinci Resolve settings that can't be set via API.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import subprocess

from rich.console import Console

console = Console()


def _run_applescript(script: str) -> str | None:
    """Run an AppleScript and return stdout, or None on failure.

    Always decodes the subprocess output as UTF-8 with errors="replace".
    This is critical inside py2app bundles where the default encoding is
    ASCII (no LANG/LC_ALL set), so any non-ASCII byte in osascript's
    output (em-dashes in Apple error messages, unicode quotes, etc.)
    would otherwise crash _translate_newlines with a UnicodeDecodeError.

    If the failure is the macOS Accessibility permission denial (TCC error
    -1719), we return None silently — that path is non-fatal and would
    otherwise spam the console on every run.
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        stderr = (result.stderr or "").strip()
        if "-1719" in stderr or "not allowed assistive access" in stderr:
            # Accessibility permission not granted. The build still works
            # without this; the settings just won't be auto-set.
            return None
        console.print(f"[yellow]AppleScript error: {stderr}[/yellow]")
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        console.print(f"[yellow]AppleScript failed: {e}[/yellow]")
        return None
    except Exception as e:
        # Defensive: never let an osascript wrapper bug crash the app.
        console.print(f"[yellow]AppleScript wrapper exception: {e}[/yellow]")
        return None


def set_project_settings_via_ui(
    frame_rate: str | None = None,
    set_quad_split: bool = False,
) -> str | None:
    """Open Project Settings ONCE, apply all requested changes, Save ONCE.

    Opens Resolve's Project Settings dialog and applies whichever settings
    are requested in a single dialog session:

    - frame_rate: set the Playback frame rate text field (text field 3 in group 1)
    - set_quad_split: click "Square Division Quad Split (SQ)" radio button

    Save/Cancel buttons are direct children of the window (NOT inside group 1).
    The dialog is ALWAYS closed before returning (Save if changed, Cancel if not)
    so it never blocks subsequent Resolve API calls.

    Returns:
        "SAVED"     — at least one change was made and saved
        "UNCHANGED" — dialog opened but nothing needed changing
        "ERROR:..." — something went wrong, dialog closed via Cancel
        None        — AppleScript failed entirely (accessibility, timeout, etc.)
    """
    # Build the AppleScript body dynamically based on what needs setting
    set_steps = []

    if frame_rate is not None:
        set_steps.append(f'''
            -- Set playback frame rate (text field 3 in group 1)
            try
                set value of text field 3 of group 1 to "{frame_rate}"
            end try
            delay 0.2
            try
                click text field 3 of group 1
            end try
            delay 0.1
            -- Tab to commit the field value
            key code 48
            delay 0.3''')

    if set_quad_split:
        set_steps.append('''
            -- Set 4K/8K format to Square Division Quad Split (SQ)
            try
                click radio button "Square Division Quad Split (SQ)" of group 1
            on error
                try
                    set rbs to every radio button of group 1
                    repeat with rb in rbs
                        if name of rb contains "Square" then
                            click rb
                            exit repeat
                        end if
                    end repeat
                end try
            end try
            delay 0.3''')

    if not set_steps:
        return "UNCHANGED"

    steps_block = "\n".join(set_steps)

    script = f'''
tell application "DaVinci Resolve"
    activate
end tell
delay 0.5
tell application "System Events"
    tell process "DaVinci Resolve"
        set frontmost to true
        delay 0.3

        -- Open Project Settings (one time)
        click menu item "Project Settings\u2026" of menu 1 of menu bar item "File" of menu bar 1
        delay 1.5

        tell window "Project Settings"
{steps_block}

            -- Save/Cancel are direct children of the window (NOT inside group 1).
            -- Resolve uses Qt, so the `enabled` property of buttons returns
            -- missing value via System Events. Instead, click Save directly —
            -- if it's disabled (no changes detected) the click is a no-op and
            -- the window stays open, so we follow up with Cancel to ensure
            -- the dialog always closes.
            try
                click button "Save"
                delay 0.5
            end try
            -- If the window is still open (Save was disabled / no-op), Cancel it
            try
                if exists window "Project Settings" then
                    click button "Cancel" of window "Project Settings"
                    delay 0.3
                    return "UNCHANGED"
                end if
            end try
            return "SAVED"
        end tell
    end tell
end tell
'''
    return _run_applescript(script)


def set_playback_frame_rate(frame_rate: str) -> bool:
    """Set the Playback frame rate in Project Settings via UI automation.

    Convenience wrapper around set_project_settings_via_ui for callers
    that only need the frame rate. When both frame rate AND 4K/8K format
    need setting, call set_project_settings_via_ui directly to open the
    dialog only once.
    """
    result = set_project_settings_via_ui(frame_rate=frame_rate)
    if result == "SAVED":
        console.print(f"  Playback frame rate set to {frame_rate} (via UI automation)")
        return True
    if result == "UNCHANGED":
        console.print(
            f"  Playback frame rate was already {frame_rate} — Project Settings closed via Cancel"
        )
        return True
    if result and result.startswith("ERROR:"):
        console.print(
            f"  [yellow]UI automation hit an error, dialog closed via Cancel: {result[6:]}[/yellow]"
        )
    return False


def set_4k8k_quad_split() -> bool:
    """Set the 4K/8K format to Square Division Quad Split (SQ) via UI automation.

    Convenience wrapper around set_project_settings_via_ui for callers
    that only need the 4K/8K format.
    """
    result = set_project_settings_via_ui(set_quad_split=True)
    if result == "SAVED":
        console.print("  4K/8K format set to Square Division (SQ) via UI automation")
        return True
    if result == "UNCHANGED":
        console.print("  4K/8K format was already Square Division (SQ)")
        return True
    if result and result.startswith("ERROR:"):
        console.print(
            f"  [yellow]4K/8K UI automation error, dialog closed via Cancel: {result[6:]}[/yellow]"
        )
    return False
