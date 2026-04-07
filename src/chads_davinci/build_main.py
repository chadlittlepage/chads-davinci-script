"""Direct entry point for the build command — bypasses click to avoid
issues with Cocoa drag-and-drop in click's invocation context.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import json
import subprocess
import sys

from rich.console import Console

from chads_davinci import __version__
from chads_davinci.file_picker import pick_files
from chads_davinci.metadata import print_metadata_comparison
from chads_davinci.models import MetadataConfig
from chads_davinci.resolve_connection import (
    connect,
    set_project_settings,
)
from chads_davinci.ui_automation import set_playback_frame_rate

console = Console()

BANNER = (
    "[bold]Chad's DaVinci Script[/bold] v{version}\n"
    "[dim]Created by Chad Littlepage | chad.littlepage@gmail.com | "
    "323.974.0444 | 2026-04-02[/dim]"
)


def main() -> int:
    """Run the full build pipeline."""
    # Set up console logging for crash reports
    try:
        from chads_davinci.console_log import setup_logging
        setup_logging()
    except (ImportError, OSError):
        pass

    console.print(BANNER.format(version=__version__))
    console.print()

    # Step 1: File picker (menu bar gets installed inside pick_files after NSApp init)
    console.print("Opening file picker...")
    picker_result = pick_files()
    if picker_result is None:
        console.print("[yellow]Cancelled[/yellow]")
        return 0

    assignments = picker_result.assignments
    track_names = picker_result.track_names

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

        return 0

    # Step 3: Connect to Resolve and set project settings
    console.print()
    console.print("[bold]Connecting to DaVinci Resolve...[/bold]")
    ctx = connect(
        create_project=True,
        project_name=picker_result.project_name,
        database_name=picker_result.database_name,
        folder_name=picker_result.folder_name,
    )
    set_project_settings(
        ctx,
        frame_rate=picker_result.frame_rate,
        start_timecode=picker_result.start_timecode,
        source_resolution=picker_result.source_resolution,
        timeline_color_space=picker_result.timeline_color_space,
        output_color_space=picker_result.output_color_space,
    )

    # Step 4: Set playback frame rate via AppleScript before any timeline/clips
    console.print()
    r_playback = ctx.project.SetSetting("timelinePlaybackFrameRate", picker_result.frame_rate)
    if not r_playback:
        set_playback_frame_rate(picker_result.frame_rate)

    # Step 5: Run bins/media/timeline in subprocess (fresh Resolve API connection)
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

    build_args = json.dumps({
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
    })

    result = subprocess.run(
        [sys.executable, "-m", "chads_davinci.build_worker"],
        input=build_args,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.stdout:
        console.print(result.stdout, end="")
    if result.returncode != 0:
        if result.stderr:
            console.print(f"[red]{result.stderr}[/red]")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
