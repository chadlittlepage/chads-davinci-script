"""Direct entry point for the build command — bypasses click to avoid
issues with Cocoa drag-and-drop in click's invocation context.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from rich.console import Console

from chads_davinci import __version__
from chads_davinci.file_picker import pick_files
from chads_davinci.metadata import print_metadata_comparison
from chads_davinci.models import MetadataConfig
from chads_davinci.ui_automation import set_playback_frame_rate
from chads_davinci.resolve_connection import (
    connect,
    set_project_settings,
)

console = Console()

# Feature flag — set to True to run the build phase inline in the
# parent process instead of spawning a build_worker subprocess.
#
# DISABLED: The Resolve scripting API does NOT support two
# `scriptapp("Resolve")` connections from the same Python process.
# The second connection returns silently-failing stubs (bin creation
# returns None, ImportMedia returns empty), breaking every build.
# The subprocess pattern was implicitly working around this by giving
# the build phase a fresh Python interpreter with no prior Resolve
# state.
#
# Leaving the code path in place behind the flag in case a future
# Resolve version lifts the limitation.
INLINE_BUILD_WORKER = False

BANNER = (
    "[bold]Chad's DaVinci Script[/bold] v{version}\n"
    "[dim]Created by Chad Littlepage | chad.littlepage@gmail.com | "
    "323.974.0444 | 2026-04-02[/dim]"
)


def _show_alert(title: str, message: str, critical: bool = False) -> None:
    """Show a final dialog before the process exits.

    Uses `osascript display dialog` (not NSAlert) because it's the only
    reliable way to bring a dialog to the front above DaVinci Resolve.
    NSAlert + NSRunningApplication.activate just doesn't win the focus
    fight on modern macOS when the calling process is no longer
    foreground from the WindowServer's perspective.

    Bonus: `display dialog` does NOT need Accessibility (TCC) permission
    because it's served by osascript itself via StandardAdditions, not
    via System Events.
    """
    # Always print to console first so the log captures the message
    # regardless of whether the dialog actually appears.
    console.print(f"[bold]{title}[/bold]\n{message}")

    # AppleScript needs the message to be a single quoted string. Escape
    # backslashes and double-quotes, and use \r for newlines (Apple's
    # native line separator inside display dialog).
    def _escape(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\r")

    safe_title = _escape(title)
    safe_msg = _escape(message)
    icon = "stop" if critical else "note"
    script = (
        f'display dialog "{safe_msg}" '
        f'with title "{safe_title}" '
        f'buttons {{"OK"}} default button "OK" '
        f'with icon {icon}'
    )
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
    except Exception as e:
        console.print(f"[dim]osascript dialog failed: {e}[/dim]")
        # Last-resort fallback: NSAlert. Worse Z-ordering on modern
        # macOS but at least the user might see it via Cmd-Tab.
        try:
            from AppKit import NSAlert, NSAlertStyleCritical, NSAlertStyleInformational
            alert = NSAlert.alloc().init()
            alert.setMessageText_(title)
            alert.setInformativeText_(message)
            alert.setAlertStyle_(NSAlertStyleCritical if critical else NSAlertStyleInformational)
            alert.addButtonWithTitle_("OK")
            alert.runModal()
        except Exception:
            pass


def _maybe_show_first_launch_welcome() -> None:
    """On the very first launch (no marker file present), show a native
    dialog that warns the user about the macOS permission prompts they
    will see during the first build, BEFORE the picker opens. Subsequent
    launches skip this dialog."""
    from chads_davinci.paths import APP_SUPPORT_DIR
    marker = APP_SUPPORT_DIR / ".first_launch_seen"
    if marker.exists():
        return
    try:
        from AppKit import (
            NSAlert,
            NSAlertStyleInformational,
            NSApplication,
            NSApplicationActivationPolicyRegular,
        )
        # Spin up NSApplication early so the welcome alert comes to the
        # foreground (otherwise it can hide behind Resolve or Terminal).
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)

        alert = NSAlert.alloc().init()
        alert.setMessageText_("Welcome to Chad's DaVinci Script")
        alert.setInformativeText_(
            "Heads-up for first-time users:\n\n"
            "• When you click OK to build a project, macOS will ask "
            "permission for this app to control DaVinci Resolve. "
            "Click \"OK\" / \"Allow\" — it only happens once.\n\n"
            "• Make sure DaVinci Resolve is running BEFORE you click "
            "OK to build.\n\n"
            "• Drag video files from Finder directly onto the path "
            "fields. The field will outline in blue when ready to drop.\n\n"
            "• All your settings auto-save and persist between launches. "
            "Use \"Reset Defaults\" if you ever want to start fresh."
        )
        alert.setAlertStyle_(NSAlertStyleInformational)
        alert.addButtonWithTitle_("Got it")
        alert.runModal()
    except Exception:
        # Best-effort; never block the app from starting.
        pass
    finally:
        try:
            APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
            marker.write_text("seen", encoding="utf-8")
        except Exception:
            pass


def main() -> int:
    """Run the full build pipeline."""
    # py2app bundles ship without LANG/LC_ALL set, so Python defaults to
    # ASCII for subprocess pipes. Any non-ASCII byte from osascript /
    # mediainfo / ffprobe / etc. would crash _translate_newlines with a
    # UnicodeDecodeError. Force UTF-8 globally before anything else runs.
    os.environ.setdefault("LANG", "en_US.UTF-8")
    os.environ.setdefault("LC_ALL", "en_US.UTF-8")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    # Set up console logging for crash reports
    try:
        from chads_davinci.console_log import setup_logging
        setup_logging()
    except (ImportError, OSError):
        pass

    # Diagnostics: install global exception hook + write system probe to log
    try:
        from chads_davinci.diagnostics import (
            install_global_exception_hook,
            write_session_probe,
        )
        install_global_exception_hook()
        write_session_probe()
    except Exception:
        pass

    console.print(BANNER.format(version=__version__))
    console.print()

    # First-launch welcome — show a one-time native dialog explaining what
    # macOS permission prompts to expect, so users aren't blindsided.
    _maybe_show_first_launch_welcome()

    # Step 1: File picker (menu bar gets installed inside pick_files after NSApp init)
    console.print("Opening file picker...")
    picker_result = pick_files()
    if picker_result is None:
        console.print("[yellow]Cancelled[/yellow]")
        return 0

    assignments = picker_result.assignments
    track_names = picker_result.track_names

    # Show a floating progress window so the user has visible feedback
    # during the long synchronous Resolve build steps and knows not to
    # click in Resolve until everything completes.
    progress = None
    try:
        from chads_davinci.progress_window import ProgressWindow
        progress = ProgressWindow()
        progress.show()
        progress.set_status("Reviewing your file assignments…")
    except Exception as e:
        console.print(f"[dim]Progress window unavailable: {e}[/dim]")

    console.print()
    console.print("[bold]File Assignments:[/bold]")
    for a in assignments:
        name = track_names.get(a.role, a.role.value)
        status = "auto-generated" if a.file_path is None and a.role.name == "QUAD_TEMPLATE" else ""
        if a.file_path:
            status = a.file_path.name
        elif not status:
            status = "(none)"
        enabled = "ON" if a.enabled else "OFF"
        console.print(f"  {name}: {status} [{enabled}]")

    console.print()
    console.print(f"[bold]Project:[/bold] {picker_result.project_name}")
    if picker_result.database_name:
        console.print(f"[bold]Database:[/bold] {picker_result.database_name}")
    if picker_result.folder_name:
        console.print(f"[bold]Folder:[/bold] {picker_result.folder_name}")

    # Step 2: Metadata extraction
    metadata_results = []
    edl_marker_path = None
    if picker_result.use_mediainfo or picker_result.use_ffprobe:
        if progress:
            progress.set_status("Extracting metadata from media files…",
                                f"MediaInfo + ffprobe on {len(assignments) - 1} files")
        console.print()
        console.print("[bold]Extracting metadata...[/bold]")
        meta_config = MetadataConfig(
            use_mediainfo=picker_result.use_mediainfo,
            use_ffprobe=picker_result.use_ffprobe,
        )
        metadata_results = print_metadata_comparison(assignments, meta_config)

        # Save report files if requested
        if picker_result.report_format != "None":
            from chads_davinci.metadata import save_report
            if progress:
                progress.set_status("Saving metadata reports…")

            saved = save_report(
                metadata_results,
                picker_result.project_name,
                picker_result.report_format,
                out_dir=picker_result.export_directory,
            )
            if saved:
                console.print()
                console.print("[bold]Saved metadata reports:[/bold]")
                for p in saved:
                    console.print(f"  [cyan]{p}[/cyan]")

        # Export EDL markers if requested
        if "EDL" in picker_result.marker_option:
            from chads_davinci.metadata import export_edl_markers
            if progress:
                progress.set_status("Exporting EDL marker file…")

            edl_marker_path = export_edl_markers(
                metadata_results,
                picker_result.project_name,
                picker_result.frame_rate,
                out_dir=picker_result.export_directory,
            )
            console.print()
            console.print(f"[bold]Saved EDL markers:[/bold] [cyan]{edl_marker_path}[/cyan]")
    else:
        console.print()
        console.print("[dim]Metadata extraction skipped (both tools disabled)[/dim]")

    # If metadata-only mode, stop here — no Resolve build
    if picker_result.metadata_only:
        console.print()
        console.print("[green bold]Metadata Export complete.[/green bold]")

        # Open Finder showing the export directory
        from chads_davinci.metadata import REPORTS_DIR

        export_dir = picker_result.export_directory or str(REPORTS_DIR)
        subprocess.run(["open", export_dir], check=False)

        if progress:
            progress.close()
        _show_alert(
            "Metadata Export complete",
            f"Reports saved to:\n{export_dir}\n\n"
            f"A Finder window has been opened at that location.",
        )
        return 0

    # Step 3: Connect to Resolve and set project settings
    if progress:
        progress.set_status("Connecting to DaVinci Resolve…",
                            "Make sure Resolve is running")
    console.print()
    console.print("[bold]Connecting to DaVinci Resolve...[/bold]")
    ctx = connect(
        create_project=True,
        project_name=picker_result.project_name,
        database_name=picker_result.database_name,
        folder_name=picker_result.folder_name,
    )
    try:
        from chads_davinci.diagnostics import log_resolve_connection
        log_resolve_connection(ctx)
    except Exception:
        pass
    if progress:
        progress.set_status("Configuring Resolve project settings…",
                            "Resolution, frame rate, color management, SDI monitoring")
    set_project_settings(
        ctx,
        frame_rate=picker_result.frame_rate,
        start_timecode=picker_result.start_timecode,
        source_resolution=picker_result.source_resolution,
        timeline_color_space=picker_result.timeline_color_space,
        output_color_space=picker_result.output_color_space,
    )

    # Step 4: Set the playback frame rate.
    #
    # The Resolve API treats `timelinePlaybackFrameRate` as read-only on
    # most Resolve versions, so SetSetting() returns falsy and the
    # playback monitor stays at Resolve's default (e.g. 24) even though
    # the timeline frame rate is correctly set to (e.g.) 23.976.
    #
    # If the API call doesn't take effect, fall back to UI automation
    # via AppleScript. The AppleScript opens Resolve's Project Settings
    # dialog, sets the field, and clicks Save (or Cancel if Save is
    # disabled because the value was already correct — see
    # ui_automation.set_playback_frame_rate for details).
    #
    # We HIDE the progress panel before running the AppleScript so it
    # isn't covered by the Project Settings dialog (Resolve is Qt and
    # its modals bypass AppKit's window level hierarchy), then SHOW it
    # again afterward.
    console.print()
    desired = str(picker_result.frame_rate)
    try:
        current_playback = str(ctx.project.GetSetting("timelinePlaybackFrameRate") or "")
    except Exception:
        current_playback = ""
    if current_playback == desired:
        console.print(f"  Playback frame rate already {desired}")
    else:
        try:
            ctx.project.SetSetting("timelinePlaybackFrameRate", desired)
        except Exception:
            pass
        try:
            current_playback = str(ctx.project.GetSetting("timelinePlaybackFrameRate") or "")
        except Exception:
            pass
        if current_playback == desired:
            console.print(f"  Playback frame rate set to {desired} via API")
        else:
            # Fall back to AppleScript UI automation. Hide the progress
            # panel briefly so it doesn't get covered by the Project
            # Settings dialog, run the script, then re-show.
            console.print(
                f"  [dim]API couldn't set playback frame rate "
                f"(still {current_playback}); falling back to UI automation[/dim]"
            )
            if progress:
                progress.set_status(
                    "Setting playback frame rate via Resolve UI…",
                    "Resolve will briefly show its Project Settings dialog",
                )
                try:
                    progress.window.orderOut_(None)
                    progress.pump()
                except Exception:
                    pass
            try:
                set_playback_frame_rate(desired)
            finally:
                if progress:
                    try:
                        progress.window.orderFrontRegardless()
                        progress.pump()
                    except Exception:
                        pass
                    progress.set_status(
                        "Continuing build…",
                        "Playback frame rate updated",
                    )

    # Step 5: Run bins/media/timeline (fresh Resolve API connection)
    console.print()
    console.print("[dim]Launching fresh Resolve connection for build...[/dim]")

    # Build marker data for subprocess if "Add to Timeline" was selected
    timeline_markers = []
    if "Timeline" in picker_result.marker_option and metadata_results:
        for assignment, meta in metadata_results:
            comment_parts = [
                f"Codec: {meta.codec}",
                f"Res: {meta.resolution}",
                f"Bit: {meta.bit_depth or 'N/A'}",
                f"CS: {meta.color_space}",
                f"Transfer: {meta.hdr10.transfer_characteristics or 'N/A'}",
                f"MaxCLL: {meta.hdr10.max_cll or 'N/A'}",
                f"DV: {'Yes' if meta.dolby_vision.rpu_present else 'No'}",
            ]
            timeline_markers.append({
                "role": assignment.role.value,
                "name": assignment.role.value,
                "comment": " | ".join(comment_parts),
            })

    build_args_dict = {
        "assignments": [
            {
                "role": a.role.value,
                "file_path": str(a.file_path) if a.file_path else None,
                "enabled": a.enabled,
            }
            for a in assignments
        ],
        "track_names": {role.value: name for role, name in track_names.items()},
        "timeline_name": "Quad View",
        "start_timecode": picker_result.start_timecode,
        "bin_structure": picker_result.bin_structure,
        "bin_rename_map": picker_result.bin_rename_map,
        "source_resolution": picker_result.source_resolution,
        "timeline_markers": timeline_markers,
        "extras": picker_result.extras or [],
    }

    if progress:
        progress.set_status("Building Resolve project…",
                            "Creating bins, importing media, building timeline")

    import time

    if INLINE_BUILD_WORKER:
        # Run the build phase in-process — saves the ~4s of Python
        # subprocess startup. Output goes through the same logger so
        # the per-line timestamps are still captured.
        from chads_davinci.build_worker import run_build
        try:
            run_build(build_args_dict)
            returncode = 0
        except Exception as e:
            import traceback
            console.print(f"[red]Inline build failed: {e}[/red]")
            console.print(f"[red]{traceback.format_exc()}[/red]")
            returncode = 1

        if returncode != 0:
            if progress:
                progress.close()
            _show_alert(
                "Build failed",
                "The Resolve build raised an exception.\n\n"
                "Open Help → Export Console Log… to capture the details.",
                critical=True,
            )
            return 1
    else:
        # Subprocess fallback — original isolation pattern. Use Popen
        # + polling so the progress window keeps animating, AND stream
        # stdout line-by-line so the parent log captures real per-line
        # timestamps for diagnosing slow phases.
        import select
        build_args = json.dumps(build_args_dict)
        proc = subprocess.Popen(
            [sys.executable, "-m", "chads_davinci.build_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env={
                **os.environ,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUNBUFFERED": "1",
                "LANG": "en_US.UTF-8",
            },
        )
        try:
            proc.stdin.write(build_args)
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

        stderr_chunks: list[str] = []
        deadline = time.time() + 600
        while proc.poll() is None:
            if time.time() > deadline:
                try:
                    proc.kill()
                except Exception:
                    pass
                break
            try:
                ready, _, _ = select.select(
                    [proc.stdout, proc.stderr], [], [], 0.05
                )
            except Exception:
                ready = []
            if proc.stdout in ready:
                line = proc.stdout.readline()
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
            if proc.stderr in ready:
                line = proc.stderr.readline()
                if line:
                    stderr_chunks.append(line)
            if progress:
                progress.pump()

        try:
            for line in proc.stdout:
                sys.stdout.write(line)
            sys.stdout.flush()
        except Exception:
            pass
        try:
            for line in proc.stderr:
                stderr_chunks.append(line)
        except Exception:
            pass

        stderr = "".join(stderr_chunks)
        returncode = proc.returncode if proc.returncode is not None else -1

        if returncode != 0:
            if stderr:
                console.print(f"[red]{stderr}[/red]")
            if progress:
                progress.close()
            _show_alert(
                "Build failed",
                "The Resolve build subprocess returned an error.\n\n"
                "Open Help → Export Console Log… to capture the details.",
                critical=True,
            )
            return 1

    if progress:
        progress.set_status("Done!", "Switch to DaVinci Resolve to view the project")
        # Brief flash of the success state before closing
        time.sleep(0.4)
        progress.pump()
        progress.close()

    _show_alert(
        "Build complete",
        f"Project: {picker_result.project_name}\n"
        f"Folder:  {picker_result.folder_name or '(none)'}\n"
        f"Timeline: Quad View\n\n"
        f"Switch to DaVinci Resolve to view the project.",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
