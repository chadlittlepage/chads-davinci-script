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

    If the failure is the macOS Accessibility permission denial (TCC error
    -1719), we return None silently — that path is non-fatal and would
    otherwise spam the console on every run.
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        stderr = result.stderr.strip()
        if "-1719" in stderr or "not allowed assistive access" in stderr:
            # Accessibility permission not granted. The build still works
            # without this; the playback frame rate just won't be auto-set.
            return None
        console.print(f"[yellow]AppleScript error: {stderr}[/yellow]")
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        console.print(f"[yellow]AppleScript failed: {e}[/yellow]")
        return None


def set_playback_frame_rate(frame_rate: str) -> bool:
    """Set the Playback frame rate in Project Settings via UI automation.

    Opens Project Settings, sets the playback frame rate text field, and clicks Save.
    This is necessary because the Resolve scripting API treats this setting as read-only.
    """
    script = f'''
tell application "DaVinci Resolve"
    activate
end tell
delay 0.5
tell application "System Events"
    tell process "DaVinci Resolve"
        set frontmost to true
        delay 0.3

        -- Open Project Settings
        click menu item "Project Settings…" of menu 1 of menu bar item "File" of menu bar 1
        delay 1.5

        tell window "Project Settings"
            tell group 1
                -- Direct value set on Playback frame rate (text field 3)
                set value of text field 3 to "{frame_rate}"
                delay 0.3

                -- Click into the field then click a label to defocus.
                -- This makes Resolve register the change and enables Save.
                click text field 3
                delay 0.1
                click static text 22
                delay 0.5
            end tell

            -- Click Save to apply and close
            click button "Save"
            delay 0.5
        end tell
    end tell
end tell

return "OK"
'''
    result = _run_applescript(script)
    if result == "OK":
        console.print(f"  Playback frame rate set to {frame_rate} (via UI automation)")
        return True
    # Silent fall-through: the timeline frame rate is already set via the
    # Resolve API, so the playback monitor will inherit it. The UI-automation
    # path is best-effort and only matters when Resolve's API treats
    # `timelinePlaybackFrameRate` as read-only on this version.
    return False
