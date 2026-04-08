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

    Opens Project Settings, sets the playback frame rate text field, and
    clicks Save. The script ALWAYS closes the dialog before returning —
    if the value is unchanged (Save button disabled), it clicks Cancel
    instead. Leaving the dialog open would block every subsequent
    Resolve API call (ImportMedia, AddTrack, etc.) in the build_worker
    subprocess and produce silent import failures.

    This is necessary because some Resolve versions treat the playback
    frame rate setting as read-only via the scripting API.
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

            -- Click Save if it is enabled (i.e. Resolve detected a change),
            -- otherwise click Cancel. EITHER WAY, the dialog must close —
            -- if it stays open it blocks every subsequent Resolve API call.
            try
                if enabled of button "Save" then
                    click button "Save"
                    delay 0.5
                    return "SAVED"
                else
                    click button "Cancel"
                    delay 0.5
                    return "UNCHANGED"
                end if
            on error errMsg
                -- Defensive: if anything goes sideways trying to read the
                -- Save button state, force-close via Cancel so we never
                -- leave a modal dialog blocking Resolve.
                try
                    click button "Cancel"
                end try
                return "ERROR:" & errMsg
            end try
        end tell
    end tell
end tell
'''
    result = _run_applescript(script)
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
    # Silent fall-through: the timeline frame rate is already set via the
    # Resolve API, so the playback monitor will inherit it. The UI-automation
    # path is best-effort and only matters when Resolve's API treats
    # `timelinePlaybackFrameRate` as read-only on this version.
    return False
