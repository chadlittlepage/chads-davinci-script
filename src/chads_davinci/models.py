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
    HW2_300_NIT = "HW2 300 nit"
    L1SHW_300 = "L1SHW 300"
    HW2_795_STRETCH_1500 = "HW2 795 Stretch 1500"
    L1SHW_795_STRETCH_1500 = "L1SHW 795 Stretch 1500"
    L1SHW_HDMI = "L1SHW HDMI"


# Tracks the user selects files for (V1 Quad1 is auto-generated)
SELECTABLE_TRACKS = [
    TrackRole.REEL_SOURCE,
    TrackRole.HW2_300_NIT,
    TrackRole.L1SHW_300,
    TrackRole.HW2_795_STRETCH_1500,
    TrackRole.L1SHW_795_STRETCH_1500,
    TrackRole.L1SHW_HDMI,
]

REQUIRED_TRACKS = {
    TrackRole.HW2_300_NIT,
    TrackRole.L1SHW_300,
    TrackRole.HW2_795_STRETCH_1500,
    TrackRole.L1SHW_795_STRETCH_1500,
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


@dataclass
class QuadTransform:
    """Position and scale for a quadrant in the 8K canvas."""

    zoom_x: float
    zoom_y: float
    position_x: float
    position_y: float


# Computed quad transforms — call get_quad_transforms(timeline_w, timeline_h) to get them.
# Timeline is always 2x source, so each quad fills exactly one quadrant at zoom=1.0.
# Pan/Tilt offsets = timeline_dimension / 4 (positive=right/up, negative=left/down).
# V3=Q1 (top-left), V4=Q2 (top-right), V5=Q3 (bottom-left), V6=Q4 (bottom-right).


def get_quad_transforms(timeline_w: int, timeline_h: int) -> dict[TrackRole, QuadTransform]:
    """Compute quad transforms for the given timeline resolution.

    Resolve auto-scales source to fill the timeline, so the clip is at full
    timeline size. To make each clip show only one quadrant, we offset each
    by ±timeline_dim / 2 so 3/4 of the clip is pushed off-screen and only
    the desired quadrant remains visible. Zoom stays at 1.0.

    Q1 top-left: clip pushed to top-left → see its bottom-right quarter
    Q2 top-right: clip pushed to top-right → see its bottom-left quarter
    Q3 bottom-left: clip pushed to bottom-left → see its top-right quarter
    Q4 bottom-right: clip pushed to bottom-right → see its top-left quarter
    """
    ox = timeline_w / 2
    oy = timeline_h / 2
    return {
        TrackRole.HW2_300_NIT: QuadTransform(zoom_x=1.0, zoom_y=1.0, position_x=-ox, position_y=oy),
        TrackRole.L1SHW_300: QuadTransform(zoom_x=1.0, zoom_y=1.0, position_x=ox, position_y=oy),
        TrackRole.HW2_795_STRETCH_1500: QuadTransform(zoom_x=1.0, zoom_y=1.0, position_x=-ox, position_y=-oy),
        TrackRole.L1SHW_795_STRETCH_1500: QuadTransform(zoom_x=1.0, zoom_y=1.0, position_x=ox, position_y=-oy),
    }


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
