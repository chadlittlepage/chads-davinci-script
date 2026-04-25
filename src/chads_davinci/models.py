"""Data models for track assignments and metadata results.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class TrackRole(Enum):
    """Role of each video track in the quad layout."""

    QUAD_TEMPLATE = "QUAD Template"
    REEL_SOURCE = "REEL SOURCE"
    L1SHW_795_STRETCH_1500 = "L15HW 795 Stretch 1500"
    HW2_795_STRETCH_1500 = "HW2 795 Stretch 1500"
    L1SHW_300 = "L15HW 300"
    HW2_300_NIT = "HW2 300"
    L1SHW_HDMI = "L15HW HDMI"


# Tracks the user selects files for (V1 Quad Template is auto-generated)
SELECTABLE_TRACKS = [
    TrackRole.L1SHW_HDMI,
    TrackRole.HW2_300_NIT,
    TrackRole.L1SHW_300,
    TrackRole.HW2_795_STRETCH_1500,
    TrackRole.L1SHW_795_STRETCH_1500,
    TrackRole.REEL_SOURCE,
]

REQUIRED_TRACKS = {
    TrackRole.L1SHW_795_STRETCH_1500,
    TrackRole.HW2_795_STRETCH_1500,
    TrackRole.L1SHW_300,
    TrackRole.HW2_300_NIT,
}
OPTIONAL_TRACKS = {TrackRole.REEL_SOURCE, TrackRole.L1SHW_HDMI}


@dataclass
class TrackAssignment:
    """Maps a track role to a selected file path."""

    role: TrackRole
    file_path: Path | None = None
    enabled: bool = True

    @property
    def is_optional(self) -> bool:
        return self.role in OPTIONAL_TRACKS

    @property
    def track_number(self) -> int:
        """1-based track number in the timeline."""
        return list(TrackRole).index(self.role) + 1


class Quadrant(Enum):
    """Quadrant position in the quad-view layout."""

    Q1 = "Q1"  # top-left
    Q2 = "Q2"  # top-right
    Q3 = "Q3"  # bottom-left
    Q4 = "Q4"  # bottom-right


@dataclass
class QuadTransform:
    """Full DaVinci Resolve Transform for a quadrant clip."""

    zoom_x: float = 1.0
    zoom_y: float = 1.0
    position_x: float = 0.0
    position_y: float = 0.0
    rotation_angle: float = 0.0
    anchor_point_x: float = 0.0
    anchor_point_y: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    flip_h: bool = False
    flip_v: bool = False


# Default quadrant assignment for each track.
DEFAULT_TRACK_QUADRANTS: dict[TrackRole, Quadrant] = {
    TrackRole.L1SHW_795_STRETCH_1500: Quadrant.Q1,
    TrackRole.REEL_SOURCE: Quadrant.Q2,
    TrackRole.HW2_795_STRETCH_1500: Quadrant.Q2,
    TrackRole.L1SHW_300: Quadrant.Q3,
    TrackRole.HW2_300_NIT: Quadrant.Q4,
    TrackRole.L1SHW_HDMI: Quadrant.Q4,
}


def quadrant_offsets(quadrant: Quadrant, timeline_w: int, timeline_h: int) -> tuple[float, float]:
    """Return (position_x, position_y) for the given quadrant."""
    ox = timeline_w / 2
    oy = timeline_h / 2
    return {
        Quadrant.Q1: (-ox, oy),
        Quadrant.Q2: (ox, oy),
        Quadrant.Q3: (-ox, -oy),
        Quadrant.Q4: (ox, -oy),
    }[quadrant]


# Computed quad transforms — call get_quad_transforms(timeline_w, timeline_h) to get them.
# Timeline is always 2x source, so each quad fills exactly one quadrant at zoom=1.0.
# Pan/Tilt offsets = timeline_dimension / 2 (positive=right/up, negative=left/down).
# V3=Q1 (top-left), V4=Q2 (top-right), V5=Q3 (bottom-left), V6=Q4 (bottom-right).


def get_quad_transforms(
    timeline_w: int,
    timeline_h: int,
    custom: dict[str, dict] | None = None,
) -> dict[TrackRole, QuadTransform]:
    """Compute quad transforms for the given timeline resolution.

    If `custom` is provided (keyed by TrackRole.name), those values override
    the defaults. Custom entries store a quadrant label plus explicit transform
    fields. Position values are recomputed from the quadrant assignment for the
    given resolution unless the custom entry has position values that differ
    from the default 8K offsets (manual override).

    Q1 top-left, Q2 top-right, Q3 bottom-left, Q4 bottom-right.
    """
    result: dict[TrackRole, QuadTransform] = {}

    for role in SELECTABLE_TRACKS:
        quad = DEFAULT_TRACK_QUADRANTS.get(role, Quadrant.Q1)
        px, py = quadrant_offsets(quad, timeline_w, timeline_h)
        transform = QuadTransform(position_x=px, position_y=py)

        if custom and role.name in custom:
            cfg = custom[role.name]
            # Determine quadrant (may have been reassigned)
            q_str = cfg.get("quadrant")
            if q_str:
                try:
                    quad = Quadrant(q_str)
                except ValueError:
                    pass
            # Recompute position for actual resolution from quadrant
            px, py = quadrant_offsets(quad, timeline_w, timeline_h)
            # Check if the user manually overrode position (differs from
            # the 8K default for this quadrant). If so, use stored values.
            default_8k_px, default_8k_py = quadrant_offsets(quad, 7680, 4320)
            stored_px = cfg.get("position_x", default_8k_px)
            stored_py = cfg.get("position_y", default_8k_py)
            if (stored_px != default_8k_px) or (stored_py != default_8k_py):
                px, py = stored_px, stored_py

            transform = QuadTransform(
                zoom_x=cfg.get("zoom_x", 1.0),
                zoom_y=cfg.get("zoom_y", 1.0),
                position_x=px,
                position_y=py,
                rotation_angle=cfg.get("rotation_angle", 0.0),
                anchor_point_x=cfg.get("anchor_point_x", 0.0),
                anchor_point_y=cfg.get("anchor_point_y", 0.0),
                pitch=cfg.get("pitch", 0.0),
                yaw=cfg.get("yaw", 0.0),
                flip_h=cfg.get("flip_h", False),
                flip_v=cfg.get("flip_v", False),
            )

        result[role] = transform

    return result


# Default transforms (8K) — kept for backwards compatibility
QUAD_TRANSFORMS: dict[TrackRole, QuadTransform] = get_quad_transforms(7680, 4320)


@dataclass
class DolbyVisionMeta:
    """Dolby Vision metadata extracted from a video file."""

    profile: int | None = None
    level: int | None = None
    rpu_present: bool = False
    bl_signal_compatibility_id: int | None = None
    el_type: str | None = None


@dataclass
class HDR10Meta:
    """HDR10 static metadata extracted from a video file."""

    max_cll: int | None = None
    max_fall: int | None = None
    master_display: str | None = None
    color_primaries: str | None = None
    transfer_characteristics: str | None = None
    matrix_coefficients: str | None = None


@dataclass
class FileMetadata:
    """Combined metadata for a single video file."""

    file_path: Path
    codec: str = ""
    resolution: str = ""
    frame_rate: str = ""
    bit_depth: int | None = None
    color_space: str = ""
    dolby_vision: DolbyVisionMeta = field(default_factory=DolbyVisionMeta)
    hdr10: HDR10Meta = field(default_factory=HDR10Meta)
    raw_mediainfo: dict[str, str] = field(default_factory=dict)
    raw_ffprobe: dict[str, str] = field(default_factory=dict)


@dataclass
class MetadataConfig:
    """Configuration for metadata extraction tools."""

    use_mediainfo: bool = True
    use_ffprobe: bool = True


# Fixed bin structure matching the Chad_Template.drp layout.
# Each entry: (bin_path, sub_bins) where bin_path is relative to Master.
BIN_STRUCTURE: list[tuple[str, list[str]]] = [
    ("HW5", ["Target_795", "Generic TV"]),
    ("LWL15", ["Target_795", "GenericTV"]),
    ("HWL15", ["Generic TV/HDMIScrambled", "Target_795", "Target_300"]),
    ("SOURCE", ["Long Plata Reel", "Short Plata Reel"]),
    ("HW2", ["Target_795", "Generic TV", "Target_300"]),
]

# Maps each track role to its target bin path (relative to Master).
# Files are imported into these bins.
TRACK_BIN_MAP: dict[TrackRole, str] = {
    TrackRole.REEL_SOURCE: "SOURCE",
    TrackRole.HW2_300_NIT: "HW2/Target_300",
    TrackRole.L1SHW_300: "HWL15/Target_300",
    TrackRole.HW2_795_STRETCH_1500: "HW2/Target_795",
    TrackRole.L1SHW_795_STRETCH_1500: "HWL15/Target_795",
    TrackRole.L1SHW_HDMI: "HWL15/Generic TV/HDMIScrambled",
}


# ---------------------------------------------------------------------------
# Supported file formats
# ---------------------------------------------------------------------------
#
# This list documents what Chad's DaVinci Script + DaVinci Resolve can
# handle. The picker accepts ANY file extension (no filtering on the
# drag-drop or Browse panel), so the source of truth is what Resolve's
# scripting API can ingest, not what we whitelist.
#
# Container formats (single-file video):
SUPPORTED_VIDEO_EXTENSIONS: set[str] = {
    # QuickTime / MPEG-4 family
    ".mov", ".mp4", ".m4v", ".mkv", ".avi", ".webm",
    # Broadcast / pro container
    ".mxf", ".ts", ".m2t", ".m2ts", ".mts",
    # Camera RAW / vendor formats
    ".braw",   # Blackmagic RAW
    ".r3d",    # RED REDCODE RAW
    ".ari", ".arx",  # ARRIRAW
    ".crm", ".rmf",  # Canon Cinema RAW Light
    ".dng",    # CinemaDNG
    ".cine",   # Phantom Cine (Vision Research)
    ".nev",    # Nikon N-RAW (Z8 / Z9, 12-bit RAW)
    # 360 / VR formats
    ".insv",   # Insta360 stitched 360° video (X3/X4/RS/ONE X)
    # Camera-generated proxies / sidecars (rarely the user's intent
    # but accept them anyway)
    ".lrv",    # Low-resolution proxy (GoPro, Insta360, others)
    ".lrf",    # Low-resolution proxy (DJI Osmo, Mavic, Inspire, drones)
    # Other
    ".3gp", ".vob", ".ogv",
}

# Image formats — each can be either a single still OR part of a sequence.
# Resolve auto-detects sequences when you import a single frame from a
# folder containing matching frames.
IMAGE_SEQUENCE_EXTENSIONS: set[str] = {
    ".dpx",         # Digital Picture Exchange (SMPTE 268M)
    ".tif", ".tiff",
    ".exr",         # OpenEXR
    ".jpg", ".jpeg",
    ".jp2", ".j2k", ".jpf", ".jpx",  # JPEG 2000
    ".png",
    ".tga",         # Targa
    ".bmp",
    ".hdr",         # Radiance HDR
    ".cin",         # Cineon
    ".insp",        # Insta360 360° photo
}

# Supported audio (kept here for completeness; the picker is video-focused)
SUPPORTED_AUDIO_EXTENSIONS: set[str] = {
    ".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a", ".aac",
}

# Convenience union of every extension Resolve can handle.
ALL_SUPPORTED_EXTENSIONS: set[str] = (
    SUPPORTED_VIDEO_EXTENSIONS
    | IMAGE_SEQUENCE_EXTENSIONS
    | SUPPORTED_AUDIO_EXTENSIONS
)


def is_image_sequence_format(file_path: Path) -> bool:
    """Return True if the file's extension is an image format (i.e. it
    might be part of a multi-frame sequence)."""
    return file_path.suffix.lower() in IMAGE_SEQUENCE_EXTENSIONS


def _normalize_for_matching(s: str) -> str:
    """Lowercase and strip every non-alphanumeric character so that
    keyword matching works regardless of how the user separates words
    in their filenames. Examples:

      "DVP1.0_HW2_300nit_v002.mov"   → "dvp10hw2300nitv002mov"
      "DVP1.0_HW_2_300_nit_v002.mov" → "dvp10hw2300nitv002mov"
      "DVP1.0-HW2-300nit-v002.mov"   → "dvp10hw2300nitv002mov"
      "DVP1.0 HW2 300nit v002.mov"   → "dvp10hw2300nitv002mov"

    All four normalize to the same string, so "hw2" and "300nit"
    both match cleanly via substring lookup regardless of which
    separator the source naming convention used.
    """
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _tokens_for_matching(name: str) -> list[str]:
    """Extract significant matching tokens from a track name (or any
    label string). Splits on non-alphanumeric runs, lowercases, drops
    tokens shorter than 2 chars (avoids accidental matches on "v",
    "a", etc.).

    Examples:
      "HW2 300 nit"             → ["hw2", "300", "nit"]
      "L1SHW 795 Stretch 1500"  → ["l1shw", "795", "stretch", "1500"]
      "Sony BVM-X300 (300nit)"  → ["sony", "bvm", "x300", "300nit"]
    """
    import re
    return [t for t in re.findall(r"[a-z0-9]+", name.lower()) if len(t) >= 2]


def route_filename_to_role(
    filename: str,
    custom_names: "dict[TrackRole, str] | None" = None,
) -> "TrackRole | None":
    """Best-effort match: figure out which TrackRole a filename looks
    like it belongs to. Returns None if no clear match.

    Two-phase matching:

    PHASE 1: TOKEN-BASED matching against the user's CURRENT track names.
      If `custom_names` is provided (a dict of TrackRole → current
      display name), the matcher tokenizes each track name into
      significant words and counts how many tokens appear as substrings
      in the filename. The track with the highest score (≥ 2) wins.
      This is the path that lights up when the user has CUSTOMIZED
      their track names — e.g. renamed "HW2 300 nit" to "Sony BVM 300"
      and named their files `Sony_BVM_300_v001.mov`.

    PHASE 2: HARD-CODED keyword pattern fallback.
      If phase 1 finds no clear winner (best score < 2), fall back to
      the original keyword patterns that know about the default
      Resolve/Dolby workflow vocabulary (HW2, L1SHW, L15HW, HWL15,
      300, 300nit, 795, 1500, stretch, hdmi, reel, source). This
      preserves the legacy behavior for users who never customize.

    Examples that all route to HW2_300_NIT (default track names):
      DVP1.0_Plata_Reel_HW2_300nit_v002.mov
      DVP1.0_HW_2_300_nit_v002.mov
      DVP1.0-HW2-300nit-v002.mov
      DVP1.0 HW2 300 nit v002.mov

    Examples for the other default-named roles:
      L15HW_Default_Plata_300_v002.mp4               → L1SHW_300
      DVP1.0_Reel_HW2_795_Stretch_1500_v002.mov      → HW2_795_STRETCH_1500
      L15HW_Default_Plata_HWL15_795_1500_v002.mp4    → L1SHW_795_STRETCH_1500
      Reel_HDMI_Generic_TV.mov                       → L1SHW_HDMI
      CHARTSONLY_Reel_2020_ProResXQ.mov              → REEL_SOURCE

    Custom-name example (user renamed HW2 300 nit → Sony BVM 300):
      Sony_BVM_300_v001.mov                          → HW2_300_NIT
      (matches via tokens [sony, bvm, 300] from the custom track name)

    Note: HDMI is checked FIRST in the hard-coded fallback because
    L1SHW HDMI files often also contain "L1SHW", "HW2", or "L15HW".
    """
    name = _normalize_for_matching(filename)

    # ----- PHASE 1: Token-based matching using current track names ------
    if custom_names:
        # For each role, score = how many of its name tokens appear in
        # the normalized filename. Tie-break by total token count
        # (more tokens = more specific match).
        scores: list[tuple[int, int, "TrackRole"]] = []
        for role, label in custom_names.items():
            tokens = _tokens_for_matching(label)
            if not tokens:
                continue
            score = sum(1 for t in tokens if t in name)
            if score > 0:
                scores.append((score, len(tokens), role))
        if scores:
            # Sort by (score desc, token-count desc, then enum order
            # for determinism). Pick the winner.
            scores.sort(key=lambda x: (x[0], x[1]), reverse=True)
            best_score, _, best_role = scores[0]
            # Require score >= 2 OR a unique high-confidence single
            # token match (no other role tied)
            if best_score >= 2:
                return best_role
            if len(scores) >= 2 and scores[0][0] > scores[1][0]:
                return best_role
            # otherwise fall through to phase 2

    # ----- PHASE 2: Hard-coded keyword fallback (legacy default vocab) -

    # HDMI is most specific — check first
    if "hdmi" in name:
        return TrackRole.L1SHW_HDMI

    # The 795/1500/stretch family
    is_stretch = ("795" in name) or ("1500" in name) or ("stretch" in name)

    # Distinguish HW2 (the L15-HW2 hardware variants) from L1SHW
    # (the L15 software / HWL15 variants)
    is_hw2 = "hw2" in name
    is_l1shw = ("l1shw" in name) or ("l15hw" in name) or ("hwl15" in name)

    if is_hw2 and is_stretch:
        return TrackRole.HW2_795_STRETCH_1500
    if is_l1shw and is_stretch:
        return TrackRole.L1SHW_795_STRETCH_1500

    # The 300-nit family
    is_300 = ("300" in name) or ("300nit" in name)
    if is_hw2 and is_300:
        return TrackRole.HW2_300_NIT
    if is_l1shw and is_300:
        return TrackRole.L1SHW_300

    # REEL SOURCE — typically contains "reel" or "source"
    if "source" in name or "reel" in name:
        return TrackRole.REEL_SOURCE

    return None


def detect_image_sequence(file_path: Path) -> tuple[int, str] | None:
    """If `file_path` looks like a single frame from a numbered image
    sequence, return (frame_count, pattern_label) for the whole sequence.
    Otherwise return None.

    A "sequence" is detected by:
    1. The file's extension is in IMAGE_SEQUENCE_EXTENSIONS
    2. The filename contains at least one run of digits before the extension
    3. There are 2+ files in the same folder with the same prefix +
       same digit-run length + same extension

    Example:
        frame.0001.dpx → looks for frame.NNNN.dpx siblings
        clip_v002_0-9239.tif → looks for clip_v002_0-NNNN.tif siblings
    """
    import re

    if not is_image_sequence_format(file_path):
        return None
    if not file_path.exists():
        return None

    parent = file_path.parent
    stem = file_path.stem
    suffix = file_path.suffix.lower()

    # Find the LAST run of digits in the stem — that's the frame number.
    matches = list(re.finditer(r"\d+", stem))
    if not matches:
        return None
    last = matches[-1]
    digit_count = last.end() - last.start()
    prefix = stem[: last.start()]
    suffix_after = stem[last.end():]

    # Build a regex that matches sibling frames
    pattern = re.compile(
        r"^" + re.escape(prefix) + r"\d{" + str(digit_count) + r"}"
        + re.escape(suffix_after) + re.escape(suffix) + r"$",
        re.IGNORECASE,
    )

    # Count siblings via os.scandir (no per-entry stat) instead of
    # iterdir, so a 30K-frame network folder takes ~100ms instead of
    # ~2 seconds. We don't need any file metadata, just the names.
    import os
    try:
        count = 0
        with os.scandir(parent) as it:
            for entry in it:
                if pattern.match(entry.name):
                    count += 1
    except OSError:
        return None

    if count < 2:
        return None

    pattern_label = (
        f"{prefix}[{'#' * digit_count}]{suffix_after}{suffix}"
    )
    return (count, pattern_label)
