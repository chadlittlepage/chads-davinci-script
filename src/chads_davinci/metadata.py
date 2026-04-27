"""Metadata extraction using mediainfo and/or ffprobe.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import csv
import json
import subprocess
from datetime import datetime
from html import escape as html_escape
from pathlib import Path

from rich.console import Console
from rich.table import Table

from chads_davinci.paths import APP_SUPPORT_DIR
from chads_davinci.models import (
    DolbyVisionMeta,
    FileMetadata,
    HDR10Meta,
    MetadataConfig,
    MetadataResult,
    TrackAssignment,
)

# Force a wide rendering width so the metadata comparison table (7 columns)
# doesn't get truncated to ~80 chars when stdout is tee'd to a log file
# (no terminal → Rich falls back to its default 80-column width).
console = Console(width=240, force_terminal=False)


def _find_bundled_tool(name: str) -> str | None:
    """Find a CLI tool bundled inside the .app or in the dev bin/ folder."""
    here = Path(__file__).resolve()
    candidates = [
        # Inside .app bundle: Contents/Resources/bin/<name>
        here.parent.parent.parent.parent.parent / "Resources" / "bin" / name,
        # Dev mode: project_root/bin/<name>
        here.parent.parent.parent.parent / "bin" / name,
        # Alternative dev paths
        Path.cwd() / "bin" / name,
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return str(p)
    return None


_TOOL_CACHE: dict[str, str | None] = {}


def _resolve_tool(name: str) -> str | None:
    """Find a CLI tool: bundled first, then PATH. Cached after first lookup."""
    if name in _TOOL_CACHE:
        return _TOOL_CACHE[name]
    bundled = _find_bundled_tool(name)
    if bundled:
        _TOOL_CACHE[name] = bundled
        _log_tool_version_once(name, bundled)
        return bundled
    out = _run_cmd(["which", name])
    resolved = out.strip() if out else None
    _TOOL_CACHE[name] = resolved
    if resolved:
        _log_tool_version_once(name, resolved)
    return resolved


def _log_tool_version_once(name: str, path: str) -> None:
    """Best-effort: log the tool's version line on first use. Never raises."""
    try:
        from chads_davinci.diagnostics import log_tool_version
        log_tool_version(name, path)
    except Exception:
        pass


def _run_cmd(cmd: list[str]) -> str | None:
    """Run a command and return stdout, or None on failure.

    Always decodes as UTF-8 with errors="replace" — py2app bundles ship
    without LANG/LC_ALL, so the default Python encoding is ASCII and any
    non-ASCII byte in mediainfo/ffprobe output would crash the
    text-mode pipe in _translate_newlines.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def extract_mediainfo(file_path: Path) -> FileMetadata:
    """Extract metadata using mediainfo JSON output."""
    meta = FileMetadata(file_path=file_path)

    tool = _resolve_tool("mediainfo")
    if tool is None:
        return meta
    output = _run_cmd([tool, "--Output=JSON", str(file_path)])
    if not output:
        return meta

    try:
        data = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return meta

    if not data or not isinstance(data, dict):
        return meta

    media = data.get("media")
    if not media or not isinstance(media, dict):
        return meta

    tracks = media.get("track", [])

    for track in tracks:
        track_type = track.get("@type", "")

        if track_type == "Video":
            meta.codec = track.get("Format", "")
            width = track.get("Width", "")
            height = track.get("Height", "")
            meta.resolution = f"{width}x{height}" if width and height else ""
            meta.frame_rate = track.get("FrameRate", "")
            meta.bit_depth = int(track.get("BitDepth", 0)) or None
            meta.color_space = track.get("ColorSpace", "")

            # HDR10
            meta.hdr10.color_primaries = track.get("colour_primaries", "")
            meta.hdr10.transfer_characteristics = track.get("transfer_characteristics", "")
            meta.hdr10.matrix_coefficients = track.get("matrix_coefficients", "")
            meta.hdr10.master_display = track.get("MasteringDisplay_ColorPrimaries", "")

            maxcll = track.get("MaxCLL", "")
            if maxcll:
                try:
                    meta.hdr10.max_cll = int(str(maxcll).split()[0])
                except (ValueError, IndexError):
                    pass

            maxfall = track.get("MaxFALL", "")
            if maxfall:
                try:
                    meta.hdr10.max_fall = int(str(maxfall).split()[0])
                except (ValueError, IndexError):
                    pass

            # Dolby Vision
            dv_profile = track.get("HDR_Format_Profile", "")
            if "dvhe" in dv_profile.lower() or "dolby" in track.get("HDR_Format", "").lower():
                meta.dolby_vision.rpu_present = True
                # Parse profile number
                for part in dv_profile.replace(",", " ").split():
                    if part.isdigit():
                        meta.dolby_vision.profile = int(part)
                        break

                dv_level = track.get("HDR_Format_Level", "")
                for part in dv_level.replace(",", " ").split():
                    if part.isdigit():
                        meta.dolby_vision.level = int(part)
                        break

                compat = track.get("HDR_Format_Compatibility", "")
                meta.dolby_vision.bl_signal_compatibility_id = (
                    int(compat) if compat.isdigit() else None
                )

            meta.raw_mediainfo = {k: str(v) for k, v in track.items()}
            break  # First video track only

    return meta


def extract_ffprobe(file_path: Path) -> FileMetadata:
    """Extract metadata using ffprobe JSON output."""
    meta = FileMetadata(file_path=file_path)

    tool = _resolve_tool("ffprobe")
    if tool is None:
        return meta
    output = _run_cmd([
        tool,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        "-show_frames",
        "-read_intervals", "%+#1",  # Only first frame for side data
        str(file_path),
    ])
    if not output:
        return meta

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return meta

    # Find video stream
    for stream in data.get("streams", []):
        if stream.get("codec_type") != "video":
            continue

        meta.codec = stream.get("codec_name", "")
        meta.resolution = f"{stream.get('width', '')}x{stream.get('height', '')}"
        meta.frame_rate = stream.get("r_frame_rate", "")
        meta.bit_depth = int(stream.get("bits_per_raw_sample", 0)) or None
        meta.color_space = stream.get("color_space", "")

        # HDR10 from stream
        meta.hdr10.color_primaries = stream.get("color_primaries", "")
        meta.hdr10.transfer_characteristics = stream.get("color_transfer", "")
        meta.hdr10.matrix_coefficients = stream.get("color_space", "")

        # Side data (mastering display, content light level, Dolby Vision)
        for side in stream.get("side_data_list", []):
            sd_type = side.get("side_data_type", "")

            if "Mastering" in sd_type:
                r = side.get("red_x", ""), side.get("red_y", "")
                g = side.get("green_x", ""), side.get("green_y", "")
                b = side.get("blue_x", ""), side.get("blue_y", "")
                wp = side.get("white_point_x", ""), side.get("white_point_y", "")
                meta.hdr10.master_display = f"R({r[0]},{r[1]}) G({g[0]},{g[1]}) B({b[0]},{b[1]}) WP({wp[0]},{wp[1]})"
                lmax = side.get("max_luminance", "")
                lmin = side.get("min_luminance", "")
                if lmax:
                    meta.hdr10.master_display += f" L({lmax},{lmin})"

            elif "Content light" in sd_type:
                meta.hdr10.max_cll = int(side.get("max_content", 0)) or None
                meta.hdr10.max_fall = int(side.get("max_average", 0)) or None

            elif "Dolby Vision" in sd_type:
                meta.dolby_vision.rpu_present = True
                meta.dolby_vision.profile = int(side.get("dv_profile", 0)) or None
                meta.dolby_vision.level = int(side.get("dv_level", 0)) or None
                meta.dolby_vision.bl_signal_compatibility_id = (
                    int(side.get("dv_bl_signal_compatibility_id", 0)) or None
                )
                meta.dolby_vision.el_type = side.get("dv_el_type", None)

        # Also check frames for side data
        for frame in data.get("frames", []):
            if frame.get("media_type") != "video":
                continue
            for side in frame.get("side_data_list", []):
                sd_type = side.get("side_data_type", "")
                if "Dolby Vision" in sd_type and not meta.dolby_vision.rpu_present:
                    meta.dolby_vision.rpu_present = True
                    meta.dolby_vision.profile = int(side.get("dv_profile", 0)) or None
                    meta.dolby_vision.level = int(side.get("dv_level", 0)) or None

        meta.raw_ffprobe = {k: str(v) for k, v in stream.items()}
        break

    return meta


def merge_metadata(mi: FileMetadata, fp: FileMetadata) -> FileMetadata:
    """Merge mediainfo and ffprobe results, preferring non-empty values."""
    merged = FileMetadata(file_path=mi.file_path)

    merged.codec = mi.codec or fp.codec
    merged.resolution = mi.resolution or fp.resolution
    merged.frame_rate = mi.frame_rate or fp.frame_rate
    merged.bit_depth = mi.bit_depth or fp.bit_depth
    merged.color_space = mi.color_space or fp.color_space

    # HDR10 - prefer mediainfo but fill gaps from ffprobe
    merged.hdr10 = HDR10Meta(
        max_cll=mi.hdr10.max_cll or fp.hdr10.max_cll,
        max_fall=mi.hdr10.max_fall or fp.hdr10.max_fall,
        master_display=mi.hdr10.master_display or fp.hdr10.master_display,
        color_primaries=mi.hdr10.color_primaries or fp.hdr10.color_primaries,
        transfer_characteristics=mi.hdr10.transfer_characteristics or fp.hdr10.transfer_characteristics,
        matrix_coefficients=mi.hdr10.matrix_coefficients or fp.hdr10.matrix_coefficients,
    )

    # Dolby Vision - prefer ffprobe (more detailed side data) but fill from mediainfo
    merged.dolby_vision = DolbyVisionMeta(
        profile=fp.dolby_vision.profile or mi.dolby_vision.profile,
        level=fp.dolby_vision.level or mi.dolby_vision.level,
        rpu_present=fp.dolby_vision.rpu_present or mi.dolby_vision.rpu_present,
        bl_signal_compatibility_id=(
            fp.dolby_vision.bl_signal_compatibility_id or mi.dolby_vision.bl_signal_compatibility_id
        ),
        el_type=fp.dolby_vision.el_type or mi.dolby_vision.el_type,
    )

    merged.raw_mediainfo = mi.raw_mediainfo
    merged.raw_ffprobe = fp.raw_ffprobe

    return merged


def _resolve_folder_to_first_frame(folder: Path) -> Path | None:
    """If `folder` is a directory containing an image sequence, return
    the path to ANY one frame so mediainfo / ffprobe have a real file
    to read. Returns None if it's not a sequence folder.

    Used by extract_metadata so passing a folder path (e.g. user dropped
    a TIFF sequence folder onto a row) doesn't hang the tools for 30+
    seconds trying to read a directory.
    """
    import os
    sequence_exts = {
        ".dpx", ".tif", ".tiff", ".exr", ".jpg", ".jpeg", ".jp2", ".j2k",
        ".png", ".tga", ".bmp", ".hdr", ".cin", ".insp",
    }
    try:
        with os.scandir(folder) as it:
            for entry in it:
                name = entry.name
                if name.startswith("."):
                    continue
                dot = name.rfind(".")
                if dot < 1 or name[dot:].lower() not in sequence_exts:
                    continue
                if not name[dot - 1].isdigit():
                    continue
                try:
                    if entry.is_file():
                        return Path(entry.path)
                except OSError:
                    continue
    except OSError:
        pass
    return None


# Feature flag — set to False to disable parallel mediainfo+ffprobe
# extraction and revert to the original sequential behavior.
PARALLEL_METADATA_EXTRACTION = True


def extract_metadata(file_path: Path, config: MetadataConfig) -> MetadataResult:
    """Extract metadata using configured tools.

    If `file_path` points at a directory, transparently substitute the
    first numbered image-sequence frame inside it. Without this, calling
    mediainfo or ffprobe on a folder hangs for 30+ seconds while the
    tools probe for what to do with the directory entry.

    When both tools are enabled, runs them in parallel on a thread pool
    so the per-file cost is `max(mi, fp)` instead of `mi + fp`.
    """
    if file_path.is_dir():
        first_frame = _resolve_folder_to_first_frame(file_path)
        if first_frame is not None:
            file_path = first_frame
        else:
            # Folder with no frames inside — nothing to extract.
            return FileMetadata(file_path=file_path)

    # extract_mediainfo / extract_ffprobe each call _resolve_tool() which is
    # cached after the first hit, so we don't pay the lookup cost per file.
    if (
        PARALLEL_METADATA_EXTRACTION
        and config.use_mediainfo
        and config.use_ffprobe
    ):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_mi = ex.submit(extract_mediainfo, file_path)
            f_fp = ex.submit(extract_ffprobe, file_path)
            mi_meta = f_mi.result()
            fp_meta = f_fp.result()
    else:
        mi_meta = extract_mediainfo(file_path) if config.use_mediainfo else None
        fp_meta = extract_ffprobe(file_path) if config.use_ffprobe else None

    if mi_meta and fp_meta:
        merged = merge_metadata(mi_meta, fp_meta)
    elif mi_meta:
        merged = mi_meta
    elif fp_meta:
        merged = fp_meta
    else:
        merged = FileMetadata(file_path=file_path)
    return MetadataResult(merged=merged, mediainfo=mi_meta, ffprobe=fp_meta)


def _metadata_rows() -> list[tuple[str, callable]]:
    """Return the rows used in metadata comparison reports."""
    return [
        ("Codec", lambda m: m.codec),
        ("Resolution", lambda m: m.resolution),
        ("Frame Rate", lambda m: m.frame_rate),
        ("Bit Depth", lambda m: str(m.bit_depth or "")),
        ("Color Space", lambda m: m.color_space),
        ("Color Primaries", lambda m: m.hdr10.color_primaries or ""),
        ("Transfer", lambda m: m.hdr10.transfer_characteristics or ""),
        ("MaxCLL", lambda m: str(m.hdr10.max_cll or "")),
        ("MaxFALL", lambda m: str(m.hdr10.max_fall or "")),
        ("Master Display", lambda m: m.hdr10.master_display or ""),
        ("DV Present", lambda m: "Yes" if m.dolby_vision.rpu_present else "No"),
        ("DV Profile", lambda m: str(m.dolby_vision.profile or "")),
        ("DV Level", lambda m: str(m.dolby_vision.level or "")),
        ("DV Compat ID", lambda m: str(m.dolby_vision.bl_signal_compatibility_id or "")),
        ("DV EL Type", lambda m: m.dolby_vision.el_type or ""),
    ]


def print_metadata_comparison(
    assignments: list[TrackAssignment],
    config: MetadataConfig,
    pump: "callable | None" = None,
) -> list[tuple[TrackAssignment, MetadataResult]]:
    """Extract and display a comparison table. Returns (assignment, MetadataResult) pairs.

    MetadataResult contains .merged (combined), .mediainfo (MI-only), .ffprobe (FP-only)
    so callers can access per-tool data for markers and reports.
    """
    results: list[tuple[TrackAssignment, MetadataResult]] = []
    cache: dict[str, MetadataResult] = {}

    from chads_davinci.models import detect_image_sequence

    for assignment in assignments:
        if assignment.file_path is None:
            continue

        cache_key = str(assignment.file_path)
        cached = cache.get(cache_key)
        if cached is not None:
            console.print(
                f"Reusing metadata: [cyan]{assignment.file_path.name}[/cyan] "
                f"[dim](already extracted)[/dim]"
            )
            results.append((assignment, cached))
            continue

        seq = detect_image_sequence(assignment.file_path)
        if seq:
            frame_count, pattern = seq
            console.print(
                f"Extracting metadata: [cyan]{pattern}[/cyan] "
                f"[dim](image sequence, {frame_count} frames)[/dim]"
            )
        else:
            console.print(
                f"Extracting metadata: [cyan]{assignment.file_path.name}[/cyan]"
            )
        result = extract_metadata(assignment.file_path, config)
        cache[cache_key] = result
        results.append((assignment, result))

        if pump is not None:
            try:
                pump()
            except Exception:
                pass

    if not results:
        console.print("[yellow]No files to compare[/yellow]")
        return results

    # Summary table (uses merged data)
    table = Table(title="Metadata Comparison", show_lines=True)
    table.add_column("Property", style="bold")

    for assignment, _ in results:
        table.add_column(assignment.role.value, min_width=18)

    for label, getter in _metadata_rows():
        values = [getter(mr.merged) for _, mr in results]
        table.add_row(label, *values)

    console.print()
    console.print(table)
    return results


# ---------------------------------------------------------------------------
# Report writers — save metadata comparison to various file formats
# ---------------------------------------------------------------------------


REPORTS_DIR = APP_SUPPORT_DIR / "reports"


def _ensure_dir(custom_dir: Path | str | None = None) -> Path:
    """Return the output directory (custom or default), ensuring it exists."""
    target = Path(custom_dir) if custom_dir else REPORTS_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def save_report_text(
    results: list[tuple[TrackAssignment, MetadataResult]],
    project_name: str,
    out_dir: Path | str | None = None,
) -> Path:
    """Save metadata comparison as a plain text table."""
    out = _ensure_dir(out_dir) / f"{project_name}_metadata.txt"
    lines = [
        f"Metadata Report — {project_name}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 80,
        "",
    ]

    headers = ["Property"] + [a.role.value for a, _ in results]
    col_w = max(20, max(len(h) for h in headers) + 2)

    lines.append("  ".join(h.ljust(col_w) for h in headers))
    lines.append("-" * (col_w * len(headers)))

    for label, getter in _metadata_rows():
        row = [label] + [str(getter(mr.merged)) for _, mr in results]
        lines.append("  ".join(c.ljust(col_w) for c in row))

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def save_report_csv(
    results: list[tuple[TrackAssignment, MetadataResult]],
    project_name: str,
    out_dir: Path | str | None = None,
) -> Path:
    """Save metadata comparison as a CSV file."""
    out = _ensure_dir(out_dir) / f"{project_name}_metadata.csv"
    headers = ["Property"] + [a.role.value for a, _ in results]
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for label, getter in _metadata_rows():
            writer.writerow([label] + [str(getter(mr.merged)) for _, mr in results])
    return out


def save_report_json(
    results: list[tuple[TrackAssignment, MetadataResult]],
    project_name: str,
    out_dir: Path | str | None = None,
) -> Path:
    """Save metadata as a structured JSON file with per-tool raw data."""
    out = _ensure_dir(out_dir) / f"{project_name}_metadata.json"
    data = {
        "project": project_name,
        "generated": datetime.now().isoformat(),
        "tracks": [],
    }

    def _meta_to_dict(meta: FileMetadata) -> dict:
        return {
            "codec": meta.codec,
            "resolution": meta.resolution,
            "frame_rate": meta.frame_rate,
            "bit_depth": meta.bit_depth,
            "color_space": meta.color_space,
            "hdr10": {
                "max_cll": meta.hdr10.max_cll,
                "max_fall": meta.hdr10.max_fall,
                "master_display": meta.hdr10.master_display,
                "color_primaries": meta.hdr10.color_primaries,
                "transfer_characteristics": meta.hdr10.transfer_characteristics,
                "matrix_coefficients": meta.hdr10.matrix_coefficients,
            },
            "dolby_vision": {
                "present": meta.dolby_vision.rpu_present,
                "profile": meta.dolby_vision.profile,
                "level": meta.dolby_vision.level,
                "bl_signal_compatibility_id": meta.dolby_vision.bl_signal_compatibility_id,
                "el_type": meta.dolby_vision.el_type,
            },
        }

    for assignment, mr in results:
        entry = {
            "track": assignment.role.value,
            "file": str(assignment.file_path),
            "merged": _meta_to_dict(mr.merged),
        }
        if mr.mediainfo:
            entry["mediainfo"] = _meta_to_dict(mr.mediainfo)
            entry["mediainfo"]["raw"] = mr.mediainfo.raw_mediainfo
        if mr.ffprobe:
            entry["ffprobe"] = _meta_to_dict(mr.ffprobe)
            entry["ffprobe"]["raw"] = mr.ffprobe.raw_ffprobe
        data["tracks"].append(entry)
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out


def save_report_html(
    results: list[tuple[TrackAssignment, MetadataResult]],
    project_name: str,
    out_dir: Path | str | None = None,
) -> Path:
    """Save metadata comparison as an HTML file."""
    out = _ensure_dir(out_dir) / f"{project_name}_metadata.html"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    headers = "".join(f"<th>{html_escape(a.role.value)}</th>" for a, _ in results)
    rows_html = ""
    for label, getter in _metadata_rows():
        cells = "".join(f"<td>{html_escape(str(getter(mr.merged)))}</td>" for _, mr in results)
        rows_html += f"<tr><th>{html_escape(label)}</th>{cells}</tr>\n"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{html_escape(project_name)} — Metadata Report</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; padding: 20px; background: #1e1e1e; color: #ddd; }}
  h1 {{ color: #4a556c; }}
  table {{ border-collapse: collapse; margin-top: 20px; }}
  th, td {{ border: 1px solid #444; padding: 6px 12px; text-align: left; }}
  th {{ background: #2a2a2a; }}
  tr:nth-child(even) td {{ background: #252525; }}
</style></head><body>
<h1>Metadata Report — {html_escape(project_name)}</h1>
<p><em>Generated: {timestamp}</em></p>
<table>
  <thead><tr><th>Property</th>{headers}</tr></thead>
  <tbody>{rows_html}</tbody>
</table>
</body></html>
"""
    out.write_text(html, encoding="utf-8")
    return out


def save_report(
    results: list[tuple[TrackAssignment, MetadataResult]],
    project_name: str,
    fmt: str,
    out_dir: Path | str | None = None,
) -> list[Path]:
    """Save metadata report in the requested format. Returns list of saved paths."""
    if not results or fmt == "None":
        return []

    saved = []
    if "Text" in fmt or fmt == "All formats":
        saved.append(save_report_text(results, project_name, out_dir))
    if "CSV" in fmt or fmt == "All formats":
        saved.append(save_report_csv(results, project_name, out_dir))
    if "JSON" in fmt or fmt == "All formats":
        saved.append(save_report_json(results, project_name, out_dir))
    if "HTML" in fmt or fmt == "All formats":
        saved.append(save_report_html(results, project_name, out_dir))
    return saved


def export_edl_markers(
    results: list[tuple[TrackAssignment, MetadataResult]],
    project_name: str,
    frame_rate: str = "23.976",
    out_dir: Path | str | None = None,
) -> Path:
    """Export metadata as an EDL markers file that can be imported into Resolve.

    Each track gets a marker at the start with its metadata as the comment.
    """
    out = _ensure_dir(out_dir) / f"{project_name}_markers.edl"

    lines = [
        f"TITLE: {project_name} Metadata Markers",
        "FCM: NON-DROP FRAME",
        "",
    ]

    # Each track gets one marker at frame 0
    for i, (assignment, mr) in enumerate(results, start=1):
        meta = mr.merged
        track_name = assignment.role.value
        comment_parts = [
            f"{track_name}",
            f"Codec: {meta.codec}",
            f"Res: {meta.resolution}",
            f"FPS: {meta.frame_rate}",
            f"BitDepth: {meta.bit_depth or 'N/A'}",
            f"ColorSpace: {meta.color_space}",
            f"Primaries: {meta.hdr10.color_primaries or 'N/A'}",
            f"Transfer: {meta.hdr10.transfer_characteristics or 'N/A'}",
            f"Matrix: {meta.hdr10.matrix_coefficients or 'N/A'}",
            f"MaxCLL: {meta.hdr10.max_cll or 'N/A'}",
            f"MaxFALL: {meta.hdr10.max_fall or 'N/A'}",
            f"MasterDisp: {meta.hdr10.master_display or 'N/A'}",
            f"DV: {'Yes' if meta.dolby_vision.rpu_present else 'No'}",
        ]
        if meta.dolby_vision.rpu_present:
            comment_parts.extend([
                f"DV Profile: {meta.dolby_vision.profile}",
                f"DV Level: {meta.dolby_vision.level}",
                f"DV Compat: {meta.dolby_vision.bl_signal_compatibility_id}",
                f"DV EL: {meta.dolby_vision.el_type or 'N/A'}",
            ])

        comment = " | ".join(comment_parts)

        # EDL marker entry: "001  AX       V     C        00:00:00:00 00:00:00:01 00:00:00:00 00:00:00:01"
        # Followed by: " |C:ResolveColorPurple |M:Comment |D:1"
        lines.append(
            f"{i:03d}  AX       V     C        "
            f"00:00:00:00 00:00:00:01 00:00:00:00 00:00:00:01"
        )
        lines.append(f" |C:ResolveColorBlue |M:{comment} |D:1")
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    return out
