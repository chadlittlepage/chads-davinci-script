"""Subprocess worker for Resolve bin/media/timeline operations.

This runs in a separate process to get a fresh Resolve API connection
after AppleScript UI automation has been used in the parent process.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rich.console import Console

from chads_davinci.models import TrackAssignment, TrackRole

console = Console()


def _parse_resolution(s: str, default: tuple[int, int] = (1920, 1080)) -> tuple[int, int]:
    """Parse 'WxH' or 'WxH UHD ...' resolution strings, returning (w, h)."""
    import re
    m = re.match(r"\s*(\d+)\s*x\s*(\d+)", s or "")
    if m:
        try:
            return int(m.group(1)), int(m.group(2))
        except (ValueError, TypeError):
            pass
    console.print(f"[yellow]Warning: invalid source_resolution '{s}', using {default[0]}x{default[1]}[/yellow]")
    return default


def run_build(data: dict) -> None:
    """Execute the bins/media/timeline build phase from a parsed args dict.

    Same logic as the historical subprocess `main()` entry point — but
    refactored as a free function so the parent process can call it
    inline (saving the ~4s subprocess startup) when
    `build_main.INLINE_BUILD_WORKER` is True.

    Reconstruct assignments"""
    role_map = {r.value: r for r in TrackRole}
    assignments: list[TrackAssignment] = []
    for a in data["assignments"]:
        role = role_map.get(a["role"])
        if role is None:
            console.print(f"[yellow]Skipping unknown role: {a['role']}[/yellow]")
            continue
        file_path = Path(a["file_path"]) if a["file_path"] else None
        assignments.append(TrackAssignment(role=role, file_path=file_path, enabled=a["enabled"]))

    # Reconstruct track names (skip unknown roles)
    track_names = {role_map[k]: v for k, v in data["track_names"].items() if k in role_map}
    timeline_name = data["timeline_name"]
    start_timecode = data["start_timecode"]

    # Reconstruct custom bin structure if provided
    bin_structure_raw = data.get("bin_structure")
    custom_bin_structure = None
    if bin_structure_raw:
        # JSON gives us list of [name, [subs]], convert to list of (name, [subs])
        custom_bin_structure = [(name, sub_list) for name, sub_list in bin_structure_raw]

    # Update QUAD_TRANSFORMS based on source resolution (timeline = 2x source)
    source_resolution = data.get("source_resolution", "1920x1080")
    src_w, src_h = _parse_resolution(source_resolution)
    tl_w = src_w * 2
    tl_h = src_h * 2
    from chads_davinci import models
    from chads_davinci.settings_io import load_quadrant_settings
    custom_quad = load_quadrant_settings()
    custom_tracks = custom_quad.get("tracks") if custom_quad else None
    models.QUAD_TRANSFORMS = models.get_quad_transforms(tl_w, tl_h, custom=custom_tracks)
    skip_v1 = (custom_quad or {}).get("skip_v1_templates", False)

    # Apply bin rename map to TRACK_BIN_MAP so renamed bins still get the right files
    bin_rename_map = data.get("bin_rename_map") or {}
    if bin_rename_map:
        new_track_map = {}
        for role, bin_path in models.TRACK_BIN_MAP.items():
            # Check if this bin path was renamed
            new_path = bin_rename_map.get(bin_path, bin_path)
            # Also check if any prefix was renamed (e.g. HW2 → FOO renames HW2/Target_300 → FOO/Target_300)
            for old, new in bin_rename_map.items():
                if bin_path.startswith(old + "/"):
                    new_path = new + bin_path[len(old):]
                    break
            new_track_map[role] = new_path
        models.TRACK_BIN_MAP = new_track_map

    # Fresh connection to Resolve
    from chads_davinci.resolve_connection import (
        connect,
        create_bin_structure,
        create_quad_timeline,
        import_media_files,
    )

    console.print("[bold]Connecting to DaVinci Resolve (fresh)...[/bold]")
    ctx = connect(create_project=False)

    console.print()
    bin_map = create_bin_structure(ctx, custom_structure=custom_bin_structure)

    console.print()
    console.print("[bold]Importing media...[/bold]")
    media_items = import_media_files(ctx, assignments, bin_map)

    console.print()
    console.print("[bold]Building quad-view timeline...[/bold]")
    create_quad_timeline(
        ctx, assignments, media_items,
        timeline_name=timeline_name,
        track_names=track_names,
        start_timecode=start_timecode,
        skip_v1_templates=skip_v1,
    )

    # Add any user-defined extra video tracks (imported into Master/Extras bin,
    # added as new video tracks above the quad layout, no transform applied)
    extras = data.get("extras") or []
    extras = [e for e in extras if e.get("file_path")]
    if extras and ctx.timeline:
        from chads_davinci.resolve_connection import add_extra_tracks
        console.print()
        console.print(f"[bold]Adding {len(extras)} extra video track(s)...[/bold]")
        add_extra_tracks(ctx, extras)

    # Add metadata markers to the timeline if requested
    timeline_markers = data.get("timeline_markers") or []
    if timeline_markers and ctx.timeline:
        console.print()
        console.print(f"[bold]Adding {len(timeline_markers)} metadata markers to timeline...[/bold]")
        # Marker colors cycle through a few options for visibility
        colors = ["Blue", "Cyan", "Green", "Yellow", "Pink", "Purple"]
        # Spread markers across the timeline so they don't all stack at frame 0
        tl_end = ctx.timeline.GetEndFrame() - ctx.timeline.GetStartFrame()
        spacing = max(1, tl_end // (len(timeline_markers) + 1))
        for i, m in enumerate(timeline_markers):
            frame_id = (i + 1) * spacing
            color = colors[i % len(colors)]
            try:
                ctx.timeline.AddMarker(frame_id, color, m["name"], m["comment"], 1)
                console.print(f"  Added marker: [cyan]{m['name']}[/cyan] at frame {frame_id}")
            except Exception as e:
                console.print(f"  [yellow]Failed to add marker {m['name']}: {e}[/yellow]")

    console.print()
    console.print("[green bold]Done![/green bold]")


def main() -> None:
    """Subprocess entry point — read JSON from stdin and run the build."""
    data = json.loads(sys.stdin.read())
    run_build(data)


if __name__ == "__main__":
    main()
