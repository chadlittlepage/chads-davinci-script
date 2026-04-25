"""DaVinci Resolve scripting API connection and timeline operations.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from chads_davinci import models
from chads_davinci.models import (
    BIN_STRUCTURE,
    TRACK_BIN_MAP,
    TrackAssignment,
    TrackRole,
)

console = Console()


def _is_resolve_running() -> bool:
    """Return True if DaVinci Resolve is currently running."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "Resolve"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode == 0
    except Exception:
        return False


def _reactivate_self() -> None:
    """Bring our own app back to the foreground.

    Resolve activates itself aggressively on launch even with `open -g`,
    so we periodically re-foreground ourselves while we wait for it.
    """
    try:
        from AppKit import NSApplicationActivateIgnoringOtherApps, NSRunningApplication
        NSRunningApplication.currentApplication().activateWithOptions_(
            NSApplicationActivateIgnoringOtherApps
        )
    except Exception:
        pass


def _launch_resolve_and_wait(timeout_sec: int = 90) -> bool:
    """Launch DaVinci Resolve.app and wait until its scripting API responds.

    Returns True if Resolve is reachable before the timeout, False otherwise.
    """
    console.print("[yellow]DaVinci Resolve is not running — launching it...[/yellow]")
    try:
        # -g launches in the background so Resolve doesn't steal focus
        # from our app's progress/connect window while it boots.
        subprocess.Popen(["open", "-g", "-a", "DaVinci Resolve"])
    except Exception as e:
        console.print(f"[red]Failed to launch DaVinci Resolve: {e}[/red]")
        return False

    # This function runs on a worker thread (file_picker.connectClicked_
    # spawns one), so a plain sleep is correct — the main thread services
    # its own runloop and keeps the picker repainting on its own.
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        time.sleep(1.5)
        # Resolve grabs focus on launch despite -g; pull it back every poll.
        _reactivate_self()
        try:
            import DaVinciResolveScript as dvr  # type: ignore[import-untyped]
            if dvr.scriptapp("Resolve") is not None:
                console.print("[green]DaVinci Resolve is ready.[/green]")
                _reactivate_self()
                return True
        except Exception:
            pass
    return False


def get_resolve() -> Any:
    """Import and return the DaVinci Resolve scripting module.

    If Resolve isn't already running, launch it automatically and wait for
    the scripting API to come online.
    """
    # macOS paths
    script_paths = [
        "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
        Path.home()
        / "Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
    ]

    for p in script_paths:
        path_str = str(p)
        if path_str not in sys.path:
            sys.path.append(path_str)

    try:
        import DaVinciResolveScript as dvr  # type: ignore[import-untyped]
    except ImportError:
        console.print("[red]DaVinci Resolve scripting module not found.[/red]")
        raise SystemExit(1)

    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        # Auto-launch Resolve if not running, then retry
        if not _is_resolve_running():
            if _launch_resolve_and_wait():
                resolve = dvr.scriptapp("Resolve")

    if resolve is None:
        console.print(
            "[red]Could not connect to DaVinci Resolve after auto-launch. "
            "Please open Resolve manually and try again.[/red]"
        )
        raise SystemExit(1)

    # Force the Edit page. The Cut page is dramatically slower for our
    # build operations (timeline create, AppendToTimeline, AddTrack,
    # InsertGenerator, transform application) on macOS 15 in particular,
    # because the Cut page re-renders its full timeline preview on every
    # API mutation. Switching to Edit before any of those calls is the
    # cheapest way to make builds responsive there.
    try:
        if resolve.GetCurrentPage() != "edit":
            resolve.OpenPage("edit")
            console.print("[dim]Switched Resolve to the Edit page.[/dim]")
    except Exception as e:
        console.print(f"[yellow]Could not switch to Edit page: {e}[/yellow]")

    return resolve


@dataclass
class ResolveContext:
    """Active Resolve session objects."""

    resolve: Any
    project_manager: Any
    project: Any
    media_pool: Any
    timeline: Any | None = None


def connect(
    create_project: bool = False,
    project_name: str = "Quad Project",
    database_name: str = "",
    folder_name: str = "",
) -> ResolveContext:
    """Establish connection to Resolve and optionally create a project.

    Args:
        create_project: If True, create a new project (or open existing).
        project_name: Name for the new/existing project.
        database_name: Resolve database to use. If empty, uses current.
        folder_name: Folder within the database to create/navigate to.
    """
    resolve = get_resolve()
    pm = resolve.GetProjectManager()

    # Switch database if specified
    if database_name:
        db_list = pm.GetDatabaseList() or []
        target_db = None
        for db in db_list:
            if db.get("DbName") == database_name:
                target_db = db
                break

        if target_db is None and db_list:
            console.print(f"[yellow]Database '{database_name}' not found. Available:[/yellow]")
            for db in db_list:
                console.print(f"  - {db.get('DbName', 'unknown')}")
            console.print("[yellow]Using current database instead.[/yellow]")
        else:
            result = pm.SetCurrentDatabase(target_db)
            if result:
                console.print(f"Switched to database: [cyan]{database_name}[/cyan]")
            else:
                console.print(f"[yellow]Could not switch to '{database_name}', using current[/yellow]")

    # Create/navigate to folder if specified
    if folder_name:
        if not pm.OpenFolder(folder_name):
            result = pm.CreateFolder(folder_name)
            if result:
                pm.OpenFolder(folder_name)
                console.print(f"Created folder: [cyan]{folder_name}[/cyan]")
            else:
                console.print(f"[yellow]Could not create folder '{folder_name}'[/yellow]")
        else:
            console.print(f"Opened folder: [cyan]{folder_name}[/cyan]")

    if create_project:
        # SAFETY: never silently delete a project that already exists.
        # An earlier version of this code called DeleteProject on the
        # conflict, which destroyed the user's open work if they had
        # the same project loaded with unsaved changes. Instead we
        # auto-bump the requested name with " (2)", " (3)", etc., until
        # we find a free slot, and log the rename clearly.
        requested_name = project_name
        project = pm.CreateProject(requested_name)
        if project is None:
            # Conflict — find a free name by appending " (N)".
            for n in range(2, 1000):
                candidate = f"{requested_name} ({n})"
                project = pm.CreateProject(candidate)
                if project is not None:
                    console.print(
                        f"[yellow]Project '{requested_name}' already exists; "
                        f"created '{candidate}' instead so the existing project "
                        f"is not touched.[/yellow]"
                    )
                    project_name = candidate
                    break
        if project is None:
            console.print(f"[red]Could not create project '{requested_name}'[/red]")
            raise SystemExit(1)
    else:
        project = pm.GetCurrentProject()
        if project is None:
            console.print("[red]No project is currently open in Resolve[/red]")
            raise SystemExit(1)

    media_pool = project.GetMediaPool()
    timeline = project.GetCurrentTimeline()

    return ResolveContext(
        resolve=resolve,
        project_manager=pm,
        project=project,
        media_pool=media_pool,
        timeline=timeline,
    )


def set_project_settings(
    ctx: ResolveContext,
    frame_rate: str = "23.976",
    start_timecode: str = "00:00:00:00",
    source_resolution: str = "1920x1080",
    timeline_color_space: str = "Rec.2100 ST2084",
    output_color_space: str = "Rec.2100 ST2084",
) -> None:
    """Configure the project for full Dolby Vision testing.

    Timeline resolution is 2x the source so quads fit at 1:1 zoom:
    - 1920x1080 source → 3840x2160 timeline
    - 3840x2160 source → 7680x4320 timeline
    """
    project = ctx.project

    # Compute timeline resolution from source
    from chads_davinci.build_worker import _parse_resolution
    src_w, src_h = _parse_resolution(source_resolution)
    tl_w = src_w * 2
    tl_h = src_h * 2

    # Timeline resolution
    project.SetSetting("timelineResolutionWidth", str(tl_w))
    project.SetSetting("timelineResolutionHeight", str(tl_h))

    # Timeline frame rate
    project.SetSetting("timelineFrameRate", frame_rate)

    # Video monitoring format MUST match timeline resolution exactly
    if tl_w == 7680:  # 8K UHD (7680x4320)
        monitor_fmt = f"8K UHD 4320p {frame_rate}"
    elif tl_w == 3840:  # 4K UHD (3840x2160)
        monitor_fmt = f"UHD 2160p {frame_rate}"
    elif tl_w == 1920:  # HD
        monitor_fmt = f"HD 1080p {frame_rate}"
    else:
        monitor_fmt = f"UHD 2160p {frame_rate}"
    r_monitor = project.SetSetting("videoMonitorFormat", monitor_fmt)

    # Color management — defaults to Rec.2100 ST2084, user can override
    project.SetSetting("colorScienceMode", "davinciYRGB")
    project.SetSetting("colorSpaceTimeline", timeline_color_space)
    project.SetSetting("colorSpaceOutput", output_color_space)
    project.SetSetting("separateColorSpaceAndGamma", "0")

    # Image scaling settings
    project.SetSetting("imageResizeMode", "sharper")
    project.SetSetting("imageDeinterlaceQuality", "normal")
    project.SetSetting("timelineInputResMismatchBehavior", "centerCrop")
    project.SetSetting("timelineOutputResMatchTimelineRes", "1")
    project.SetSetting("timelineOutputResMismatchBehavior", "centerCrop")

    # Video monitoring options for Dolby Vision testing
    project.SetSetting("videoMonitorUse444SDI", "1")
    project.SetSetting("videoMonitorSDIConfiguration", "quad_link")
    # 4K and 8K formats: Square Division Quad Split (SQ), not Sample Interleave (SI).
    # Try known key names — Resolve's API isn't publicly documented for this setting.
    # If the API can't set it, build_main falls back to UI automation (AppleScript).
    sq_set = False
    for key, val in [
        ("videoMonitor4K8KTransport", "square_division"),
        ("videoMonitorSDI4KTransport", "square_division"),
        ("videoMonitorQuadSplitMode", "square_division"),
    ]:
        if project.SetSetting(key, val):
            sq_set = True
            console.print(f"  [dim]4K/8K transport set via key '{key}'[/dim]")
            break
    if not sq_set:
        console.print(
            "  [yellow]Could not set 4K/8K format to SQ via API — "
            "will fall back to UI automation[/yellow]"
        )
    ctx._sq_set_via_api = sq_set  # type: ignore[attr-defined]
    project.SetSetting("videoDataLevels", "Full")

    # Try 12-bit (requires compatible SDI hardware), fall back to 10-bit, then 8-bit
    project.SetSetting("videoMonitorBitDepth", "12")
    actual_depth = project.GetSetting("videoMonitorBitDepth")
    if actual_depth != "12":
        project.SetSetting("videoMonitorBitDepth", "10")
        actual_depth = project.GetSetting("videoMonitorBitDepth")
        if actual_depth != "10":
            project.SetSetting("videoMonitorBitDepth", "8")
            actual_depth = project.GetSetting("videoMonitorBitDepth")

    console.print(f"Project settings: {tl_w}x{tl_h} @ {frame_rate}fps (source: {source_resolution})")
    console.print(f"  Video monitoring: {monitor_fmt} ({'set' if r_monitor else 'failed'})")
    console.print("  4:4:4 SDI: enabled, SDI config: Quad link, 4K/8K: SQ, Data levels: Full")
    console.print(f"  Video bit depth: {actual_depth} bit (12 attempted, requires SDI hardware)")
    console.print(
        f"  Color: DaVinci YRGB, Timeline: {timeline_color_space}, Output: {output_color_space}"
    )


def create_bin_structure(
    ctx: ResolveContext,
    custom_structure: list[tuple[str, list[str]]] | None = None,
) -> dict[str, Any]:
    """Create the bin/folder structure in the media pool.

    Args:
        ctx: Resolve context
        custom_structure: Optional custom bin structure. If None, uses default BIN_STRUCTURE.

    Returns a dict mapping bin path strings (e.g. "HW5/Target_795") to folder objects.
    """
    media_pool = ctx.media_pool
    root_folder = media_pool.GetRootFolder()
    bin_map: dict[str, Any] = {"": root_folder}

    structure = custom_structure if custom_structure is not None else BIN_STRUCTURE
    console.print("[bold]Creating bin structure...[/bold]")

    for top_bin, sub_bins in structure:
        # Navigate to root first
        media_pool.SetCurrentFolder(root_folder)

        # Create top-level bin (retry on failure — API sometimes needs a moment)
        import time as _time
        top_folder = None
        for _try in range(3):
            top_folder = media_pool.AddSubFolder(root_folder, top_bin)
            if top_folder is not None:
                break
            top_folder = _find_subfolder(root_folder, top_bin)
            if top_folder is not None:
                break
            if _try < 2:
                _time.sleep(1)
        if top_folder is None:
            console.print(f"  [red]Failed to create bin: {top_bin}[/red]")
            continue

        bin_map[top_bin] = top_folder
        console.print(f"  Created bin: [cyan]{top_bin}[/cyan]")

        # Create sub-bins (supports nested paths like "Generic TV/HDMIScrambled")
        for sub_path in sub_bins:
            parts = sub_path.split("/")
            parent = top_folder
            current_path = top_bin

            for part in parts:
                current_path = f"{current_path}/{part}"
                sub_folder = media_pool.AddSubFolder(parent, part)
                if sub_folder is None:
                    sub_folder = _find_subfolder(parent, part)
                if sub_folder is None:
                    console.print(f"  [red]Failed to create bin: {current_path}[/red]")
                    break
                bin_map[current_path] = sub_folder
                parent = sub_folder

            if current_path in bin_map:
                console.print(f"  Created bin: [cyan]{current_path}[/cyan]")

    return bin_map


def _find_subfolder(parent_folder: Any, name: str) -> Any | None:
    """Find an existing subfolder by name."""
    subfolders = parent_folder.GetSubFolderList()
    if subfolders:
        for folder in subfolders:
            if folder.GetName() == name:
                return folder
    return None


# Image-sequence file extensions Resolve auto-detects as numbered frames
_IMAGE_SEQUENCE_EXTS = {
    ".dpx", ".tif", ".tiff", ".exr", ".jpg", ".jpeg", ".jp2", ".j2k",
    ".png", ".tga", ".bmp", ".hdr", ".cin", ".insp",
}


def _is_image_sequence_frame(file_str: str) -> bool:
    """Heuristic: True if `file_str` looks like one frame of a numbered
    image sequence (e.g. `frame_001234.tif`)."""
    p = Path(file_str)
    if p.suffix.lower() not in _IMAGE_SEQUENCE_EXTS:
        return False
    # Check that the filename ends in digits before the extension
    stem = p.stem
    return bool(stem) and stem[-1].isdigit()


def _import_one_file(media_pool: Any, media_storage: Any, file_str: str) -> Any | None:
    """Try every Resolve API path for importing a single file. Returns the
    new MediaPoolItem on success, None on failure.

    Quirk: `MediaPool.ImportMedia([path])` sometimes silently auto-detects
    files whose names end with a `<digits>-<digits>` pattern as the first
    frame of an image sequence and refuses to import them. The lower-level
    `MediaStorage.AddItemListToMediaPool([path])` doesn't trigger that
    detection, so when the primary call returns empty we retry with it.

    Image-sequence speedup: when the input looks like a frame of a
    numbered sequence, we hand the *folder* to MediaStorage first instead
    of the first frame. This skips Resolve's "is this a sequence?"
    auto-detection step (it knows it's a folder of frames) and is
    measurably faster on large sequences.
    """
    # Image-sequence fast path: pass the parent FOLDER directly to
    # MediaStorage so Resolve doesn't have to walk the folder twice
    # (once to detect, once to import).
    if _is_image_sequence_frame(file_str) and media_storage is not None:
        folder = str(Path(file_str).parent)
        try:
            imported = media_storage.AddItemListToMediaPool(folder)
            if imported and len(imported) > 0:
                # The first item is the sequence clip Resolve built.
                return imported[0]
        except Exception as e:
            console.print(
                f"  [yellow]Sequence fast-path AddItemListToMediaPool raised: "
                f"{e} — falling back to per-file ImportMedia[/yellow]"
            )

    # Retry loop — the Resolve API sometimes fails on the first attempt
    # after a fresh subprocess connection. A short delay + retry fixes it.
    import time as _time
    for attempt in range(3):
        if attempt > 0:
            console.print(f"  [dim]Import retry {attempt + 1}/3 after 2s delay...[/dim]")
            _time.sleep(2)

        # Method 1: MediaPool.ImportMedia (the primary path)
        try:
            imported = media_pool.ImportMedia([file_str])
            if imported and len(imported) > 0:
                return imported[0]
        except Exception as e:
            if attempt == 0:
                console.print(f"  [yellow]ImportMedia raised: {e}[/yellow]")

        # Method 2: MediaStorage.AddItemListToMediaPool (sequence-detection-free fallback)
        if media_storage is not None:
            try:
                imported = media_storage.AddItemListToMediaPool(file_str)
                if imported and len(imported) > 0:
                    console.print(
                        "  [dim]ImportMedia returned empty; succeeded via "
                        "MediaStorage.AddItemListToMediaPool fallback[/dim]"
                    )
                    return imported[0]
            except Exception as e:
                if attempt == 0:
                    console.print(
                        f"  [yellow]AddItemListToMediaPool raised: {e}[/yellow]"
                    )

        # Method 3: ImportMedia with a clip-info dict (forces single-file mode)
        try:
            imported = media_pool.ImportMedia([{"FilePath": file_str}])
            if imported and len(imported) > 0:
                console.print(
                    "  [dim]ImportMedia(list) returned empty; succeeded via "
                    "ImportMedia(dict) fallback[/dim]"
                )
                return imported[0]
        except Exception as e:
            if attempt == 0:
                console.print(f"  [yellow]ImportMedia(dict) raised: {e}[/yellow]")

    return None


def import_media_files(
    ctx: ResolveContext,
    assignments: list[TrackAssignment],
    bin_map: dict[str, Any],
) -> dict[TrackRole, Any]:
    """Import assigned video files into the correct media pool bins.

    Returns map of role to MediaPoolItem.
    """
    media_pool = ctx.media_pool
    media_items: dict[TrackRole, Any] = {}

    # MediaStorage is the lower-level "path-based" importer that bypasses
    # ImportMedia's auto-sequence-detection quirk.
    try:
        media_storage = ctx.resolve.GetMediaStorage()
    except Exception:
        media_storage = None

    # De-dupe imports by file path. The typical workflow assigns the
    # same source file (often a 30K-frame TIFF sequence) to all 6
    # tracks. Without de-duping, Resolve re-scans the folder for every
    # call to _import_one_file — 6 imports × ~5s each = 30s wasted.
    # Importing each unique path ONCE and reusing the same MediaPoolItem
    # for every track that points to it collapses that to one import.
    cache: dict[str, Any] = {}

    for assignment in assignments:
        if assignment.file_path is None:
            continue
        if not assignment.file_path.exists():
            console.print(
                f"  [red]Skipping (file does not exist): {assignment.file_path}[/red]"
            )
            continue

        file_str = str(assignment.file_path)

        # Determine target bin for this track
        target_bin_path = TRACK_BIN_MAP.get(assignment.role, "")
        target_folder = bin_map.get(target_bin_path)

        if target_folder is None:
            console.print(
                f"  [yellow]Bin '{target_bin_path}' not found, importing to root[/yellow]"
            )
            target_folder = media_pool.GetRootFolder()

        cached = cache.get(file_str)
        if cached is not None:
            # Reuse the already-imported clip — no extra Resolve I/O.
            media_items[assignment.role] = cached
            bin_label = target_bin_path or "Master (root)"
            console.print(
                f"  Reused: [cyan]{cached.GetName()}[/cyan] "
                f"-> {assignment.role.value} [dim]({bin_label}, "
                f"already imported)[/dim]"
            )
            continue

        size_mb = assignment.file_path.stat().st_size / (1024 * 1024)
        media_pool.SetCurrentFolder(target_folder)
        console.print(
            f"  [dim]Importing ({size_mb:.0f} MB): {file_str}[/dim]"
        )

        item = _import_one_file(media_pool, media_storage, file_str)
        if item is not None:
            media_items[assignment.role] = item
            cache[file_str] = item
            bin_label = target_bin_path or "Master (root)"
            console.print(
                f"  Imported: [cyan]{item.GetName()}[/cyan] "
                f"-> {assignment.role.value} [dim]({bin_label})[/dim]"
            )
        else:
            console.print(
                f"  [red]Failed to import (all 3 API paths returned empty): "
                f"{assignment.file_path.name}[/red]"
            )

    return media_items


def create_quad_timeline(
    ctx: ResolveContext,
    assignments: list[TrackAssignment],
    media_items: dict[TrackRole, Any],
    timeline_name: str = "Dolby Quad View",
    track_names: dict[TrackRole, str] | None = None,
    start_timecode: str = "00:00:00:00",
) -> Any:
    """Create a timeline with 7 video tracks and quad transforms applied."""
    media_pool = ctx.media_pool

    # Create empty timeline
    timeline = media_pool.CreateEmptyTimeline(timeline_name)
    if timeline is None:
        console.print("[red]Failed to create timeline[/red]")
        raise SystemExit(1)

    ctx.project.SetCurrentTimeline(timeline)
    ctx.timeline = timeline

    # Set timeline start timecode
    timeline.SetStartTimecode(start_timecode)

    # Ensure we have 7 video tracks
    current_track_count = timeline.GetTrackCount("video")
    for _ in range(7 - current_track_count):
        timeline.AddTrack("video")

    console.print(f"Created timeline: [green]{timeline_name}[/green] with 7 video tracks")
    console.print(f"  Start timecode: {start_timecode}")

    # Apply custom track names
    if track_names:
        _apply_track_names(ctx, track_names)

    # Place clips on tracks and apply transforms
    _place_clips_on_tracks(ctx, assignments, media_items)

    return timeline


def _apply_track_names(ctx: ResolveContext, track_names: dict[TrackRole, str]) -> None:
    """Set custom names on video tracks."""
    timeline = ctx.timeline
    if timeline is None:
        return

    for role, name in track_names.items():
        track_num = list(TrackRole).index(role) + 1
        timeline.SetTrackName("video", track_num, name)
        console.print(f"  Track V{track_num} named: [cyan]{name}[/cyan]")


def _place_clips_on_tracks(
    ctx: ResolveContext,
    assignments: list[TrackAssignment],
    media_items: dict[TrackRole, Any],
) -> None:
    """Place media items on their assigned tracks and apply quad transforms.

    Uses per-track auto-selection to ensure clips land on the correct track.
    """
    timeline = ctx.timeline
    if timeline is None:
        return

    # First, disable auto-select on ALL video tracks
    track_count = timeline.GetTrackCount("video")
    for t in range(1, track_count + 1):
        timeline.SetTrackEnable("video", t, True)

    # Create V1 transform templates FIRST (InsertGenerator ripple-pushes all tracks,
    # so we do it before placing any media clips). Duration from media pool items.
    for assignment in assignments:
        if assignment.role == TrackRole.QUAD_TEMPLATE:
            _create_transform_templates(ctx, assignment.track_number, media_items)
            break

    # Place media clips on V2-V7, compensating for ripple offset
    for assignment in assignments:
        if assignment.role == TrackRole.QUAD_TEMPLATE:
            continue

        if assignment.file_path is None or assignment.role not in media_items:
            continue

        track_num = assignment.track_number
        item = media_items[assignment.role]

        timeline.SetCurrentTimecode(timeline.GetStartTimecode())

        clip_info = {
            "mediaPoolItem": item,
            "trackIndex": track_num,
            "recordFrame": timeline.GetStartFrame(),
        }
        result = ctx.media_pool.AppendToTimeline([clip_info])

        if not result:
            clip_info = {
                "mediaPoolItem": item,
                "trackIndex": track_num,
            }
            result = ctx.media_pool.AppendToTimeline([clip_info])

        if result:
            console.print(f"  Placed [cyan]{item.GetName()}[/cyan] on track V{track_num}")

            if assignment.role in models.QUAD_TRANSFORMS:
                _apply_transform(ctx, track_num, assignment.role)
        else:
            console.print(f"  [red]Failed to place clip on track V{track_num}[/red]")

    # Disable optional tracks (V1, V2, V7)
    for assignment in assignments:
        if not assignment.enabled:
            timeline.SetTrackEnable("video", assignment.track_number, False)
            console.print(f"  Track V{assignment.track_number} disabled")


def _create_transform_templates(
    ctx: ResolveContext,
    track_number: int,
    media_items: dict[TrackRole, Any] | None = None,
) -> None:
    """Create V1 with 4 Solid Color compound clips (Quad 1-4) with quad transforms.

    Inserts 4 generators on V1, converts each to a compound clip, applies
    the matching quad transform, and colors it Orange. All on the main timeline.
    """
    timeline = ctx.timeline
    media_pool = ctx.media_pool
    if timeline is None or media_pool is None:
        return

    root_folder = media_pool.GetRootFolder()
    media_pool.SetCurrentFolder(root_folder)

    # Get total video duration — try timeline clips first, then media pool items
    quad_roles = [TrackRole.HW2_300_NIT, TrackRole.L1SHW_300,
                  TrackRole.HW2_795_STRETCH_1500, TrackRole.L1SHW_795_STRETCH_1500]
    total_frames = 0

    # Try from timeline clips
    for role in quad_roles:
        track_num = list(TrackRole).index(role) + 1
        clips = timeline.GetItemListInTrack("video", track_num)
        if clips:
            total_frames = clips[-1].GetEnd()
            break

    # Fallback: get duration from media pool items
    if total_frames == 0 and media_items:
        for role in quad_roles:
            mpi = media_items.get(role)
            if mpi:
                props = mpi.GetClipProperty()
                frames_str = props.get("Frames", "0")
                try:
                    total_frames = int(frames_str)
                except (ValueError, TypeError):
                    pass
                if total_frames > 0:
                    break

    if total_frames == 0:
        console.print("  [yellow]Could not determine video duration for V1 templates[/yellow]")
        return

    quad_duration = total_frames // 4
    generators_per_quad = (quad_duration // 120) + 1
    console.print(
        f"  V1 templates: {total_frames} total frames, "
        f"{quad_duration} per quad ({generators_per_quad} generators each)"
    )

    quad_names = ["Quad 1", "Quad 2", "Quad 3", "Quad 4"]

    for i, name in enumerate(quad_names):
        # Track how many clips are on V1 before we insert
        clips_before = timeline.GetItemListInTrack("video", track_number) or []
        count_before = len(clips_before)

        # Insert N generators to build up to target duration
        for _ in range(generators_per_quad):
            timeline.InsertGeneratorIntoTimeline("Solid Color")

        # Get the new generators we just inserted
        clips_after = timeline.GetItemListInTrack("video", track_number) or []
        new_gens = clips_after[count_before:]

        if not new_gens:
            console.print(f"  [red]Failed to insert generators for {name}[/red]")
            continue

        # Create one Compound Clip from all the generators
        compound = timeline.CreateCompoundClip(new_gens, {"name": name})
        if compound is None:
            console.print(f"  [red]Failed to create compound clip for {name}[/red]")
            continue

        # Apply quad transform
        transform = models.QUAD_TRANSFORMS.get(quad_roles[i])
        if transform:
            compound.SetProperty("ZoomX", transform.zoom_x)
            compound.SetProperty("ZoomY", transform.zoom_y)
            compound.SetProperty("Pan", transform.position_x)
            compound.SetProperty("Tilt", transform.position_y)
            compound.SetProperty("RotationAngle", transform.rotation_angle)
            compound.SetProperty("AnchorPointX", transform.anchor_point_x)
            compound.SetProperty("AnchorPointY", transform.anchor_point_y)
            compound.SetProperty("Pitch", transform.pitch)
            compound.SetProperty("Yaw", transform.yaw)
            compound.SetProperty("FlipX", bool(transform.flip_h))
            compound.SetProperty("FlipY", bool(transform.flip_v))

        # Color Orange
        compound.SetClipColor("Orange")

        console.print(f"  {name}: {compound.GetDuration()} frames, Orange, transform applied")


def add_extra_tracks(ctx: ResolveContext, extras: list[dict]) -> None:
    """Import extra video files into a Master/Extras bin and add them as
    additional video tracks above the existing tracks. No transform applied.

    `extras` is a list of {"name": str, "file_path": str} dicts.
    """
    timeline = ctx.timeline
    media_pool = ctx.media_pool
    if timeline is None or media_pool is None or not extras:
        return

    # Ensure Extras bin exists under Master root
    root_folder = media_pool.GetRootFolder()
    extras_folder = _find_subfolder(root_folder, "Extras")
    if extras_folder is None:
        media_pool.SetCurrentFolder(root_folder)
        extras_folder = media_pool.AddSubFolder(root_folder, "Extras")
    if extras_folder is None:
        console.print("  [red]Failed to create Extras bin[/red]")
        return

    media_pool.SetCurrentFolder(extras_folder)

    # Iterate in REVERSE: extras[0] is the picker's topmost (newest). Since
    # AddTrack always places the new track at the top of the stack, we add
    # extras[-1] (oldest) first and extras[0] (newest) last so the picker's
    # topmost ends up as the highest video track number in Resolve.
    for ex in reversed(extras):
        file_path = ex.get("file_path")
        name = ex.get("name") or "Extra"
        if not file_path:
            continue
        if not Path(file_path).exists():
            console.print(f"  [yellow]Skipping missing file: {file_path}[/yellow]")
            continue

        # Import file
        imported = media_pool.ImportMedia([str(file_path)])
        if not imported:
            console.print(f"  [red]Failed to import: {file_path}[/red]")
            continue
        item = imported[0]

        # Add a new video track at the TOP of the stack (highest track number).
        # Capture count before+after so the new index is unambiguous regardless
        # of whether AddTrack appends or inserts.
        count_before = timeline.GetTrackCount("video")
        timeline.AddTrack("video")
        count_after = timeline.GetTrackCount("video")
        if count_after <= count_before:
            console.print("  [red]AddTrack failed (count did not increase)[/red]")
            continue
        new_track_num = count_after  # new track is always the topmost (highest index)

        # Place clip on the new track
        timeline.SetCurrentTimecode(timeline.GetStartTimecode())
        result = media_pool.AppendToTimeline([{
            "mediaPoolItem": item,
            "trackIndex": new_track_num,
            "recordFrame": timeline.GetStartFrame(),
        }])
        if not result:
            result = media_pool.AppendToTimeline([{
                "mediaPoolItem": item,
                "trackIndex": new_track_num,
            }])

        # Name the new track
        timeline.SetTrackName("video", new_track_num, name)

        if result:
            console.print(
                f"  Added extra: [cyan]{name}[/cyan] -> V{new_track_num} "
                f"[dim]({Path(file_path).name})[/dim]"
            )
        else:
            console.print(f"  [red]Failed to place clip on V{new_track_num}[/red]")


def _apply_transform(ctx: ResolveContext, track_number: int, role: TrackRole) -> None:
    """Apply quad position/scale transform to a clip on the given track."""
    timeline = ctx.timeline
    if timeline is None:
        return

    transform = models.QUAD_TRANSFORMS.get(role)
    if transform is None:
        return

    clips = timeline.GetItemListInTrack("video", track_number)
    if not clips:
        return

    for clip in clips:
        clip.SetProperty("ZoomX", transform.zoom_x)
        clip.SetProperty("ZoomY", transform.zoom_y)
        clip.SetProperty("Pan", transform.position_x)
        clip.SetProperty("Tilt", transform.position_y)
        clip.SetProperty("RotationAngle", transform.rotation_angle)
        clip.SetProperty("AnchorPointX", transform.anchor_point_x)
        clip.SetProperty("AnchorPointY", transform.anchor_point_y)
        clip.SetProperty("Pitch", transform.pitch)
        clip.SetProperty("Yaw", transform.yaw)
        clip.SetProperty("FlipX", bool(transform.flip_h))
        clip.SetProperty("FlipY", bool(transform.flip_v))

    console.print(
        f"  Transform applied: zoom={transform.zoom_x}, "
        f"pos=({transform.position_x}, {transform.position_y})"
    )
