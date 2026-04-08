"""Native Cocoa file picker with drag-and-drop support.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

from rich.console import Console
from pathlib import Path

import objc
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSDragOperationCopy,
    NSDragOperationNone,
    NSFilenamesPboardType,
    NSFont,
    NSLineBreakByTruncatingHead,
    NSMakeRect,
    NSObject,
    NSOpenPanel,
    NSPopUpButton,
    NSTextField,
    NSTextFieldRoundedBezel,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
)

from chads_davinci.models import (
    OPTIONAL_TRACKS,
    SELECTABLE_TRACKS,
    TrackAssignment,
    TrackRole,
)

# Single module-level Console reused by every hot-path call site
# (drag-drop, _set_file, etc.) instead of instantiating per-event.
_module_console = Console()

FRAME_RATES = ["23.976", "24", "25", "29.97", "30", "48", "50", "59.94", "60"]

# Vertical gap between the extras section and adjacent rows (matches the gap
# between fixed file rows: row_h(36) - field_h(24) = 12).
EXTRAS_GAP = 12

# Source resolution presets — timeline will be 2x source so quads fit at 1:1
SOURCE_RESOLUTIONS = [
    "1920x1080 HD (timeline 4K)",
    "3840x2160 UHD (timeline 8K)",
]

# Metadata report file formats
REPORT_FORMATS = [
    "None",
    "Text (.txt)",
    "CSV (.csv)",
    "JSON (.json)",
    "HTML (.html)",
    "All formats",
]

# Resolve marker output options
MARKER_OPTIONS = [
    "None",
    "Add to Timeline",
    "Export as EDL file",
    "Both (Timeline + EDL)",
]

# Resolve 20.3.2 color space presets — verified via API.
# Both Timeline and Output accept the same set of values at the project-setting level.
COLOR_SPACES = [
    "Rec.2100 ST2084",
    "Rec.2100 HLG",
    "Rec.709 (Scene)",
    "Rec.709 Gamma 2.2",
    "Rec.709 Gamma 2.4",
    "Rec.709-A",
    "Rec.2020 Gamma 2.4",
    "P3-D60",
    "P3-D65",
    "P3-DCI",
    "sRGB",
    "Linear",
    "Cineon Film Log",
    "ACEScc",
    "ACEScct",
    "ACEScg",
    "ARRI LogC3",
    "ARRI LogC4",
    "Blackmagic Design Film Gen 5",
    "S-Gamut3/S-Log3",
    "S-Gamut3.Cine/S-Log3",
    "Canon Cinema Gamut/Canon Log 3",
    "Canon Cinema Gamut/Canon Log",
    "REDWideGamutRGB/Log3G10",
    "Panasonic V-Gamut/V-Log",
]


@dataclass
class PickerResult:
    """Result from the file picker dialog."""

    assignments: list[TrackAssignment]
    track_names: dict[TrackRole, str]
    database_name: str
    folder_name: str
    project_name: str
    frame_rate: str = "23.976"
    start_timecode: str = "00:00:00:00"
    # Source resolution: "1920x1080" or "3840x2160" — timeline will be 2x this
    source_resolution: str = "1920x1080"
    # Color management
    timeline_color_space: str = "Rec.2100 ST2084"
    output_color_space: str = "Rec.2100 ST2084"
    # Metadata extraction tool toggles
    use_mediainfo: bool = True
    use_ffprobe: bool = True
    # Metadata report output format
    report_format: str = "None"
    # Resolve marker option
    marker_option: str = "None"
    # Metadata-only mode: skip Resolve build, just extract metadata + reports/EDL
    metadata_only: bool = False
    # User-selected output directory for metadata export (None = default app-support/reports)
    export_directory: str | None = None
    # Custom bin structure: list of (top_bin_name, list_of_subbin_paths)
    # If None, uses the default BIN_STRUCTURE from models.py
    bin_structure: list[tuple[str, list[str]]] | None = None
    # Map of original bin path -> new bin path (for tracking renames)
    bin_rename_map: dict[str, str] | None = None
    # Extra user-added video tracks: list of {"name": str, "file_path": str|None}
    extras: list[dict] = field(default_factory=list)


def _get_resolve_databases() -> list[dict[str, str]]:
    """Connect to Resolve and fetch the database list. Returns empty list on failure."""
    import sys

    script_paths = [
        "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
        str(
            Path.home()
            / "Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
        ),
    ]
    for p in script_paths:
        if p not in sys.path:
            sys.path.append(p)

    try:
        import DaVinciResolveScript as dvr  # type: ignore[import-untyped]
    except ImportError:
        return []

    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        # Auto-launch Resolve and wait up to 90s for the scripting API
        try:
            from chads_davinci.resolve_connection import (
                _is_resolve_running,
                _launch_resolve_and_wait,
            )
            if not _is_resolve_running():
                if _launch_resolve_and_wait():
                    resolve = dvr.scriptapp("Resolve")
        except Exception:
            pass
    if resolve is None:
        return []
    pm = resolve.GetProjectManager()
    return pm.GetDatabaseList() or []


# ---------------------------------------------------------------------------
# DropTextField — NSTextField subclass that accepts file drops from Finder.
# Uses explicit @objc.signature decorators so Cocoa's runtime can dispatch.
# ---------------------------------------------------------------------------


# Modern UTI for file URLs (macOS 10.6+, preferred on macOS 14+).
# NSFilenamesPboardType is deprecated and Finder on macOS 15 sometimes
# only sends public.file-url, so we register for BOTH.
_FILE_URL_UTI = "public.file-url"


def _file_paths_from_pasteboard(pasteboard) -> list[str]:
    """Extract ALL file paths from a drag pasteboard.

    Returns a list (possibly empty) of POSIX path strings. The list
    is in pasteboard order (which is usually alphabetical when the
    user multi-selects in Finder).

    Tries the canonical modern NSURL API first, falls back to
    per-item parsing of `public.file-url`, then to the legacy
    `NSFilenamesPboardType`. Only logs on errors and on total
    failure — never on the happy path.
    """
    from AppKit import NSURL

    paths: list[str] = []

    # Method 1: NSPasteboard.readObjectsForClasses:options: (modern, fastest)
    # This returns an NSArray of NSURL objects — one per dragged item.
    try:
        urls = pasteboard.readObjectsForClasses_options_([NSURL], None)
        if urls:
            for url in urls:
                if url is None or not url.isFileURL():
                    continue
                p = url.path()
                if p:
                    paths.append(str(p))
    except Exception as e:
        _module_console.print(f"[yellow]Drag drop method 1 (NSURL) raised: {e}[/yellow]")

    if paths:
        return paths

    # Method 2: per-item public.file-url
    try:
        for item in pasteboard.pasteboardItems() or []:
            s = item.stringForType_(_FILE_URL_UTI)
            if not s:
                continue
            url = NSURL.URLWithString_(s)
            if url is not None and url.isFileURL():
                p = url.path()
                if p:
                    paths.append(str(p))
    except Exception as e:
        _module_console.print(
            f"[yellow]Drag drop method 2 (pasteboardItems) raised: {e}[/yellow]"
        )

    if paths:
        return paths

    # Method 3: legacy NSFilenamesPboardType (returns an NSArray of strings)
    types = list(pasteboard.types() or [])
    if NSFilenamesPboardType in types:
        try:
            files = pasteboard.propertyListForType_(NSFilenamesPboardType)
            if files:
                for f in files:
                    if f:
                        paths.append(str(f))
        except Exception as e:
            _module_console.print(
                f"[yellow]Drag drop method 3 (NSFilenamesPboardType) raised: {e}[/yellow]"
            )

    if not paths:
        _module_console.print(
            f"[yellow]Drag drop: could not extract any file paths. "
            f"Available pasteboard types: {types}[/yellow]"
        )
    return paths


class DropTextField(NSTextField):
    """NSTextField that accepts file drops from Finder."""

    def initWithFrame_(self, frame):
        self = objc.super(DropTextField, self).initWithFrame_(frame)
        if self is not None:
            self._drop_target = None
            self._drop_action = None
            # Register for BOTH legacy and modern pasteboard types.
            # macOS 15's Finder no longer reliably populates the legacy
            # NSFilenamesPboardType — without public.file-url here, the
            # drag session never resolves and the main thread can hang.
            self.registerForDraggedTypes_([NSFilenamesPboardType, _FILE_URL_UTI])
            # Path fields hold long POSIX paths. Truncate at the HEAD so the
            # filename (most informative part) stays visible instead of the
            # default leading-truncation that shows just "/Volumes/foo/".
            self.cell().setLineBreakMode_(NSLineBreakByTruncatingHead)
            # Default tooltip explains how to see the full path. Replaced with
            # the actual path the moment one is assigned.
            self.setToolTip_(
                "Drag a file from Finder or click Browse. "
                "Hover this field to see the full path."
            )
        return self

    def setStringValue_(self, value):
        """Always update the tooltip whenever the field's text changes,
        so the COMPLETE file path is visible on hover regardless of how
        long it is or how the field is rendered. There is no code path
        in the picker that can set a path on this field without also
        setting the tooltip — drag, paste, Browse, preset load, settings
        restore, _set_extras — they all funnel through this override."""
        objc.super(DropTextField, self).setStringValue_(value)
        try:
            text = str(value or "")
            if text:
                self.setToolTip_(text)
            else:
                self.setToolTip_(
                    "Drag a file from Finder or click Browse. "
                    "Hover this field to see the full path."
                )
        except Exception:
            pass

    def setDropTarget_action_(self, target, action):
        self._drop_target = target
        self._drop_action = action

    def _set_drag_highlight(self, on):
        self.setWantsLayer_(True)
        layer = self.layer()
        if layer is None:
            return
        if on:
            # Use CGColorCreateGenericRGB so PyObjC's bridge knows the type
            # (avoids ObjCPointerWarning that NSColor.CGColor() triggers).
            from Quartz import CGColorCreateGenericRGB
            # Apple's controlAccentColor (~ macOS blue) in sRGB.
            border = CGColorCreateGenericRGB(0.0, 0.478, 1.0, 1.0)
            layer.setBorderColor_(border)
            layer.setBorderWidth_(2.0)
            layer.setCornerRadius_(5.0)
        else:
            layer.setBorderWidth_(0.0)

    @objc.signature(b"Q@:@")
    def draggingEntered_(self, sender):
        types = sender.draggingPasteboard().types() or []
        if NSFilenamesPboardType in types or _FILE_URL_UTI in types:
            self._set_drag_highlight(True)
            return NSDragOperationCopy
        return NSDragOperationNone

    def draggingExited_(self, sender):
        self._set_drag_highlight(False)

    @objc.signature(b"B@:@")
    def prepareForDragOperation_(self, sender):
        return True

    @objc.signature(b"B@:@")
    def performDragOperation_(self, sender):
        self._set_drag_highlight(False)
        try:
            paths = _file_paths_from_pasteboard(sender.draggingPasteboard())
        except Exception as e:
            _module_console.print(f"[yellow]Drag drop extraction failed: {e}[/yellow]")
            return False
        if not paths:
            return False

        # Multi-file drop: route every file by filename pattern. The
        # row that received the drop is irrelevant — each file goes
        # to whichever row matches its name.
        if len(paths) > 1:
            if self._drop_target and hasattr(
                self._drop_target, "routeMultipleFiles_"
            ):
                self._drop_target.routeMultipleFiles_(paths)
            return True

        path = paths[0]

        # Folder drop: hand the folder to the controller's auto-router
        # so it can scan the contents and fill all matching rows.
        try:
            if Path(path).is_dir():
                if self._drop_target and hasattr(
                    self._drop_target, "routeDroppedFolder_"
                ):
                    self._drop_target.routeDroppedFolder_(path)
                return True
        except Exception:
            pass

        # Single-file drop: existing behavior — fill the row that
        # received the drop, no surprises.
        self.setStringValue_(path)
        if self._drop_target and self._drop_action:
            self._drop_target.performSelector_withObject_(self._drop_action, self)
        return True


# ---------------------------------------------------------------------------
# Window controller — manages all UI state and actions
# ---------------------------------------------------------------------------


class FilePickerController(NSObject):
    """Controller for the file picker window."""

    def init(self):
        self = objc.super(FilePickerController, self).init()
        if self is not None:
            self.window = None
            self.assignments = {role: None for role in SELECTABLE_TRACKS}
            self.name_fields = {}
            self.path_fields = {}
            # Map button object_id -> role for browse/clear lookups
            # Map NSControl tag (int) -> TrackRole. Tags are stable across PyObjC calls.
            self.button_roles = {}
            self.db_list = []
            self.db_type_popup = None
            self.db_name_popup = None
            self.connect_btn = None
            self.connect_status = None
            self.resolve_connected = False
            self.folder_field = None
            self.project_field = None
            self.fps_popup = None
            self.source_res_popup = None
            self.tc_field = None
            self.mediainfo_check = None
            self.ffprobe_check = None
            self.report_format_popup = None
            self.marker_popup = None
            self.timeline_cs_popup = None
            self.output_cs_popup = None
            self.status_label = None
            self.preset_popup = None
            self.result = None
            # Dynamic extra tracks. Extras live BETWEEN the column headers and
            # REEL SOURCE. extras[0] is the topmost (newest), extras[-1] is the
            # bottom-most (oldest, sitting just above REEL SOURCE).
            self.extras = []  # list of dicts: name_field, path_field, browse_btn, del_btn
            # upper_views = views that should stay visually fixed at the top of
            # the window as extras are added. Includes header + preset row +
            # column headers (NOT file rows — those stay at fixed content y and
            # move down visually as the window grows).
            self.upper_views = []
            self.col_headers_y_initial = None  # content y of column headers in the initial layout
            self.row_h_for_extras = 36
            self.win_w_for_extras = 780
            self.next_extra_tag = 5000
            self.bin_roots = None  # populated when user opens bin editor
        return self

    # --- Actions ---

    def browseClicked_(self, sender):
        """Browse button clicked — open file dialog."""
        role = self.button_roles.get(int(sender.tag()))
        if role is None:
            return
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(False)
        panel.setMessage_(f"Select file for {self.name_fields[role].stringValue()}")

        if panel.runModal():
            urls = panel.URLs()
            if urls and len(urls) > 0:
                filepath = str(urls[0].path())
                self.path_fields[role].setStringValue_(filepath)
                self._set_file(role, filepath)

    def clearClicked_(self, sender):
        """Clear button clicked — reset path field."""
        role = self.button_roles.get(int(sender.tag()))
        if role is None:
            return
        self.assignments[role] = None
        self.path_fields[role].setStringValue_("")

    def pathFieldChanged_(self, sender):
        """Called when a path field changes (drop or manual entry).
        Reads the value verbatim — `_set_file` is the SOLE place where
        any whitespace handling happens."""
        for role, fld in self.path_fields.items():
            if fld is sender:
                val = str(sender.stringValue())
                if val.strip():
                    self._set_file(role, val)
                else:
                    self.assignments[role] = None
                break

    def _current_track_names(self) -> dict:
        """Snapshot the picker's current track-name fields as a dict
        of `TrackRole → display name`. Used by `_route_paths` to feed
        the auto-router with the user's CURRENT (possibly customized)
        track names so filename matching works against renamed tracks
        as well as the defaults."""
        names = {}
        for role, fld in self.name_fields.items():
            try:
                value = str(fld.stringValue()).strip()
            except Exception:
                value = ""
            if value:
                names[role] = value
        return names

    def _route_paths(self, candidates: list[Path], source_label: str) -> None:
        """Shared routing logic for routeDroppedFolder_ and
        routeMultipleFiles_. Given a list of candidate file Paths,
        route each one to a TrackRole by filename pattern and update
        the matching row in the picker.

        Rules:
        - Files in `candidates` are processed in the order given (callers
          should pre-sort alphabetically for deterministic results).
        - Hidden files (`.foo`) and directories are skipped.
        - Files with unsupported extensions are skipped.
        - If multiple files match the same role, the FIRST one wins.
        - Files that don't match any role are silently ignored.
        - Matching uses the user's CURRENT track names first
          (customized or default), then falls back to the hard-coded
          keyword vocabulary.

        See `models.route_filename_to_role` for the matching rules.
        """
        from chads_davinci.models import (
            ALL_SUPPORTED_EXTENSIONS,
            route_filename_to_role,
        )

        # Snapshot the picker's current track names for token-based
        # matching. If the user customized "HW2 300 nit" → "Sony BVM 300"
        # and dropped a file named "Sony_BVM_300_v001.mov", the matcher
        # picks it up via the {sony, bvm, 300} tokens from the custom
        # name. Default-named tracks fall through to the hard-coded
        # keyword fallback (which knows about L15HW/HWL15 synonyms).
        custom_names = self._current_track_names()

        scanned = 0
        applied: list[tuple[TrackRole, Path]] = []
        seen_roles: set[TrackRole] = set()

        for entry in candidates:
            try:
                if entry.is_dir() or entry.name.startswith("."):
                    continue
            except OSError:
                continue
            if entry.suffix.lower() not in ALL_SUPPORTED_EXTENSIONS:
                continue
            scanned += 1
            role = route_filename_to_role(entry.name, custom_names=custom_names)
            if role is None or role in seen_roles or role not in self.path_fields:
                continue
            seen_roles.add(role)
            self.path_fields[role].setStringValue_(str(entry))
            self.assignments[role] = entry
            applied.append((role, entry))

        if applied:
            summary = ", ".join(role.value for role, _ in applied)
            self._set_status_ok(
                f"Auto-routed {len(applied)} of {scanned} file(s) "
                f"from {source_label}: {summary}"
            )
        else:
            self._set_status(
                f"No files from {source_label} matched a track pattern. "
                f"Drop individual files instead, or rename them to include "
                f"keywords like 'HW2', 'L1SHW', '300', '795', '1500', or 'HDMI'."
            )

    def routeDroppedFolder_(self, folder_path):
        """Auto-fill picker rows by scanning a dropped folder for video
        files and matching each one to a track role by filename pattern.
        Delegates to _route_paths for the actual routing."""
        folder = Path(str(folder_path))
        if not folder.is_dir():
            return
        try:
            entries = sorted(folder.iterdir(), key=lambda p: p.name.lower())
        except OSError as e:
            self._set_status(f"Could not read folder: {e}")
            return
        self._route_paths(entries, folder.name)

    def routeMultipleFiles_(self, paths):
        """Auto-fill picker rows when the user drops MULTIPLE files at
        once (multi-select in Finder, then drag the selection onto the
        picker). Each file is routed to its matching row by filename
        pattern. Delegates to _route_paths for the actual routing."""
        candidates = sorted(
            [Path(str(p)) for p in paths],
            key=lambda p: p.name.lower(),
        )
        self._route_paths(candidates, f"{len(candidates)} dropped file(s)")

    def connectClicked_(self, sender):
        """Connect to Resolve and populate database list."""
        self.connect_status.setStringValue_("Connecting...")
        self.connect_status.setTextColor_(NSColor.grayColor())

        # Temporarily elevate our window above Resolve's splash screen
        # (which is borderless and ignores normal app activation).
        from AppKit import NSScreenSaverWindowLevel, NSNormalWindowLevel
        win = self.window if hasattr(self, "window") else sender.window()
        prior_level = None
        try:
            prior_level = win.level()
            win.setLevel_(NSScreenSaverWindowLevel)
        except Exception:
            pass

        try:
            self.db_list = _get_resolve_databases()
        finally:
            try:
                if prior_level is not None:
                    win.setLevel_(prior_level)
                else:
                    win.setLevel_(NSNormalWindowLevel)
            except Exception:
                pass
        if not self.db_list:
            self.connect_status.setStringValue_(
                "Connected (no DB list, defaulting to Local Database)"
            )
            self.connect_status.setTextColor_(NSColor.orangeColor())
            self.resolve_connected = True
            self.db_name_popup.removeAllItems()
            self.db_name_popup.addItemWithTitle_("Local Database")
        else:
            self.resolve_connected = True
            self.connect_status.setStringValue_(
                f"Connected ({len(self.db_list)} database(s) found)"
            )
            self.connect_status.setTextColor_(NSColor.systemGreenColor())
            self._filter_databases()

        sender.setTitle_("Refresh")

    def dbTypeChanged_(self, sender):
        """Database type dropdown changed — re-filter database list."""
        self._filter_databases()

    def _filter_databases(self):
        if not self.db_list:
            return
        type_str = str(self.db_type_popup.titleOfSelectedItem()).lower()
        type_map = {"local": "Disk", "network": "PostgreSQL", "cloud": "Cloud"}
        resolve_type = type_map.get(type_str, "")

        filtered = [
            db.get("DbName", "")
            for db in self.db_list
            if db.get("DbType", "") == resolve_type
        ]

        self.db_name_popup.removeAllItems()
        if filtered:
            self.db_name_popup.addItemsWithTitles_(filtered)

    def editBinsClicked_(self, sender):
        """Open the bin editor side window."""
        from chads_davinci.bin_editor import default_bin_tree, show_bin_editor

        # Use existing roots if user already edited, otherwise default
        roots = self.bin_roots if self.bin_roots is not None else default_bin_tree()

        def on_complete(result):
            if result is not None:
                self.bin_roots = result

        show_bin_editor(roots, on_complete)

    def metadataOnlyClicked_(self, sender):
        """Metadata Export: extract metadata from any assigned files, skip Resolve build."""
        # Pick up any pasted/dropped paths — read verbatim, _set_file
        # is the sole point of any whitespace handling.
        for role in SELECTABLE_TRACKS:
            if self.assignments[role] is None:
                val = str(self.path_fields[role].stringValue())
                if val.strip():
                    self._set_file(role, val)

        # Need at least one file
        any_file = any(self.assignments[role] is not None for role in SELECTABLE_TRACKS)
        if not any_file:
            self._set_status("Assign at least one file for metadata extraction")
            return

        # Need either a report format or markers selected
        if (str(self.report_format_popup.titleOfSelectedItem()) == "None"
                and str(self.marker_popup.titleOfSelectedItem()) == "None"):
            self._set_status("Choose a Metadata Report format or Resolve Markers option")
            return

        # Show folder picker for save destination
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(False)
        panel.setCanChooseDirectories_(True)
        panel.setCanCreateDirectories_(True)
        panel.setAllowsMultipleSelection_(False)
        panel.setMessage_("Choose where to save the metadata export files")
        panel.setPrompt_("Export Here")

        if not panel.runModal():
            return  # user cancelled the folder picker

        urls = panel.URLs()
        if not urls or len(urls) == 0:
            return

        export_dir = str(urls[0].path())

        track_assignments, track_names = self._build_assignments(all_disabled=True)
        self.result = PickerResult(
            assignments=track_assignments,
            track_names=track_names,
            database_name="",
            folder_name="",
            project_name=str(self.project_field.stringValue()).strip() or "Metadata",
            frame_rate=str(self.fps_popup.titleOfSelectedItem()),
            start_timecode="00:00:00:00",
            source_resolution="1920x1080",
            use_mediainfo=bool(self.mediainfo_check.state()),
            use_ffprobe=bool(self.ffprobe_check.state()),
            report_format=str(self.report_format_popup.titleOfSelectedItem()),
            marker_option=str(self.marker_popup.titleOfSelectedItem()),
            metadata_only=True,
            export_directory=export_dir,
            extras=self._capture_extras(),
        )

        self._save_user_settings_from_form()
        if self.window:
            self.window.close()
        NSApp.stop_(None)

    def cancelClicked_(self, sender):
        self.result = None
        if self.window:
            self.window.close()
        NSApp.stop_(None)

    def okClicked_(self, sender):
        # Last-chance: pick up any pasted/dropped paths — read verbatim,
        # _set_file is the sole point of any whitespace handling.
        for role in SELECTABLE_TRACKS:
            if self.assignments[role] is None:
                val = str(self.path_fields[role].stringValue())
                if val.strip():
                    self._set_file(role, val)

        # Validate required tracks
        missing = []
        for role in SELECTABLE_TRACKS:
            if role not in OPTIONAL_TRACKS and self.assignments[role] is None:
                missing.append(str(self.name_fields[role].stringValue()))

        if missing:
            self._set_status(f"Missing required: {', '.join(missing)}")
            return

        if not self.resolve_connected:
            self._set_status("Please connect to Resolve first")
            return

        db_name = ""
        if self.db_name_popup.numberOfItems() > 0:
            db_name = str(self.db_name_popup.titleOfSelectedItem())
        if not db_name:
            self._set_status("Please select a database")
            return

        project_name = str(self.project_field.stringValue()).strip()
        if not project_name:
            self._set_status("Project name is required")
            return

        # Pre-flight: check that all assigned files exist and have
        # consistent metadata (frame rate, resolution, color space,
        # bit depth). If anything looks wrong, ask the user before
        # spending 30+ seconds on a build that's probably going to be
        # meaningless. Pre-flight is also captured in console.log.
        self._set_status_info("Pre-flight check…")
        try:
            warnings = self._run_preflight()
        except Exception as e:
            _module_console.print(f"[yellow]Pre-flight raised: {e}[/yellow]")
            warnings = []
        if warnings:
            self._set_status(
                f"Pre-flight found {len(warnings)} possible issue(s) — see dialog"
            )
            if not self._show_preflight_dialog(warnings):
                # User clicked Cancel — leave the picker open so they
                # can fix the assignments.
                self._set_status("Cancelled — fix the highlighted issues and try again")
                return

        track_assignments, track_names = self._build_assignments(all_disabled=False)

        # Convert edited bin tree to the BIN_STRUCTURE format if user edited it
        bin_structure = None
        bin_rename_map = None
        if self.bin_roots is not None:
            from chads_davinci.bin_editor import build_rename_map, tree_to_structure
            bin_structure = tree_to_structure(self.bin_roots)
            bin_rename_map = build_rename_map(self.bin_roots)

        # Parse source resolution from the dropdown title
        source_res_label = str(self.source_res_popup.titleOfSelectedItem())
        if source_res_label.startswith("3840"):
            source_resolution = "3840x2160"
        else:
            source_resolution = "1920x1080"

        self.result = PickerResult(
            assignments=track_assignments,
            track_names=track_names,
            database_name=db_name,
            folder_name=str(self.folder_field.stringValue()).strip(),
            project_name=project_name,
            frame_rate=str(self.fps_popup.titleOfSelectedItem()),
            start_timecode=str(self.tc_field.stringValue()).strip(),
            source_resolution=source_resolution,
            timeline_color_space=str(self.timeline_cs_popup.titleOfSelectedItem()),
            output_color_space=str(self.output_cs_popup.titleOfSelectedItem()),
            use_mediainfo=bool(self.mediainfo_check.state()),
            use_ffprobe=bool(self.ffprobe_check.state()),
            report_format=str(self.report_format_popup.titleOfSelectedItem()),
            marker_option=str(self.marker_popup.titleOfSelectedItem()),
            bin_structure=bin_structure,
            bin_rename_map=bin_rename_map,
            extras=self._capture_extras(),
        )

        self._save_user_settings_from_form()
        if self.window:
            self.window.close()
        NSApp.stop_(None)

    # --- Extras (dynamic extra video tracks) ---

    def _resize_window_for_extras(self, delta):
        """Grow/shrink the window by delta points (top edge fixed in screen coords)."""
        if not self.window:
            return
        frame = self.window.frame()
        new_h = frame.size.height + delta
        new_y = frame.origin.y - delta  # keep top edge fixed
        self.window.setFrame_display_animate_(
            NSMakeRect(frame.origin.x, new_y, frame.size.width, new_h),
            True, False,
        )

    def _shift_upper_views(self, delta):
        """Shift all 'upper' subviews (header, file rows, extras) up by delta in content y."""
        for v in self.upper_views:
            f = v.frame()
            v.setFrameOrigin_((f.origin.x, f.origin.y + delta))
        for row in self.extras:
            for key in ("name_field", "path_field", "browse_btn", "del_btn"):
                v = row.get(key)
                if v is None:
                    continue
                f = v.frame()
                v.setFrameOrigin_((f.origin.x, f.origin.y + delta))

    def _layout_extras(self):
        """Re-position all extras based on their current order. extras[0] is
        the topmost (just below the column headers); extras[-1] sits just above
        REEL SOURCE — both gaps are EXTRAS_GAP px so the spacing matches the
        inter-file-row spacing.
        """
        if self.col_headers_y_initial is None:
            return
        n = len(self.extras)
        row_h = self.row_h_for_extras
        for j, row in enumerate(self.extras):
            # extras[-1] (bottom) sits EXTRAS_GAP above REEL SOURCE.
            # extras[0]  (top)    sits row_h*(n-1) above extras[-1].
            target_y = self.col_headers_y_initial + EXTRAS_GAP + (n - 1 - j) * row_h
            for key in ("name_field", "path_field", "browse_btn", "del_btn"):
                v = row.get(key)
                if v is None:
                    continue
                f = v.frame()
                v.setFrameOrigin_((f.origin.x, target_y))

    def _build_extra_row(self, y, name_text="", path_text=""):
        """Construct widgets for a single extra row at content y. Returns dict."""
        margin = 20
        label_w = 180
        field_w = 580
        btn_w = 90
        tag_browse = self.next_extra_tag
        tag_del = self.next_extra_tag + 1
        self.next_extra_tag += 2

        name_field = _make_textfield(name_text or f"Extra {len(self.extras) + 1}",
                                     NSMakeRect(margin, y, label_w, 24))

        path_field = DropTextField.alloc().initWithFrame_(
            NSMakeRect(margin + label_w + 10, y, field_w, 24)
        )
        path_field.setStringValue_(path_text)
        path_field.setBezelStyle_(NSTextFieldRoundedBezel)
        path_field.setBezeled_(True)
        path_field.setEditable_(True)
        path_field.setPlaceholderString_("Drop file here or click Browse")
        path_field.setTarget_(self)
        path_field.setAction_("extraPathFieldChanged:")
        path_field.setDropTarget_action_(self, "extraPathFieldChanged:")

        browse_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(margin + label_w + 10 + field_w + 10, y, btn_w, 24)
        )
        browse_btn.setTitle_("Browse...")
        browse_btn.setBezelStyle_(1)
        browse_btn.setTag_(tag_browse)
        browse_btn.setTarget_(self)
        browse_btn.setAction_("extraBrowseClicked:")

        del_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(margin + label_w + 10 + field_w + 10 + btn_w + 5, y, 60, 24)
        )
        del_btn.setTitle_("Delete")
        del_btn.setBezelStyle_(1)
        del_btn.setToolTip_("Remove this extra track row")
        del_btn.setTag_(tag_del)
        del_btn.setTarget_(self)
        del_btn.setAction_("deleteExtraTrackClicked:")

        content = self.window.contentView()
        content.addSubview_(name_field)
        content.addSubview_(path_field)
        content.addSubview_(browse_btn)
        content.addSubview_(del_btn)

        return {
            "name_field": name_field,
            "path_field": path_field,
            "browse_btn": browse_btn,
            "del_btn": del_btn,
            "tag_browse": tag_browse,
            "tag_del": tag_del,
        }

    def _add_extra_row(self, name_text="", path_text=""):
        """Add a new extra row at the TOP of the extras section (just below
        the column headers, ABOVE REEL SOURCE). File rows shift down visually
        to make room."""
        if self.col_headers_y_initial is None or self.window is None:
            return
        row_h = self.row_h_for_extras
        # On the FIRST extra we grow by row_h + EXTRAS_GAP so the section has
        # breathing room above REEL SOURCE; subsequent adds grow by row_h only.
        delta = row_h + (EXTRAS_GAP if not self.extras else 0)
        self._resize_window_for_extras(delta)
        for v in self.upper_views:
            f = v.frame()
            v.setFrameOrigin_((f.origin.x, f.origin.y + delta))
        new_row = self._build_extra_row(self.col_headers_y_initial, name_text, path_text)
        self.extras.insert(0, new_row)
        self._layout_extras()

    def addExtraTrackClicked_(self, sender):
        self._add_extra_row()

    def deleteExtraTrackClicked_(self, sender):
        tag = int(sender.tag())
        idx = None
        for i, row in enumerate(self.extras):
            if row.get("tag_del") == tag:
                idx = i
                break
        if idx is None:
            return
        row = self.extras.pop(idx)
        for key in ("name_field", "path_field", "browse_btn", "del_btn"):
            v = row.get(key)
            if v is not None:
                v.removeFromSuperview()
        # Shrink window and shift upper section down. When removing the LAST
        # extra (count goes 1→0) the EXTRAS_GAP buffer also goes away.
        row_h = self.row_h_for_extras
        delta = row_h + (EXTRAS_GAP if not self.extras else 0)
        self._resize_window_for_extras(-delta)
        for v in self.upper_views:
            f = v.frame()
            v.setFrameOrigin_((f.origin.x, f.origin.y - delta))
        self._layout_extras()

    def extraBrowseClicked_(self, sender):
        tag = int(sender.tag())
        row = None
        for r in self.extras:
            if r.get("tag_browse") == tag:
                row = r
                break
        if row is None:
            return
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(False)
        panel.setMessage_(f"Select file for {row['name_field'].stringValue()}")
        if panel.runModal():
            urls = panel.URLs()
            if urls and len(urls) > 0:
                row["path_field"].setStringValue_(str(urls[0].path()))

    def extraPathFieldChanged_(self, sender):
        # No-op: value is read directly from the field at submit time.
        return

    def _clear_extras(self):
        """Remove all extra rows (no resize/shift; caller handles)."""
        for row in self.extras:
            for key in ("name_field", "path_field", "browse_btn", "del_btn"):
                v = row.get(key)
                if v is not None:
                    v.removeFromSuperview()
        self.extras = []

    def _set_extras(self, extras_data):
        """Replace current extras with the given list of {name, file_path}."""
        # First, remove existing extras and shrink window/shift back to baseline
        old_count = len(self.extras)
        if old_count > 0:
            row_h = self.row_h_for_extras
            self._clear_extras()
            total_delta = old_count * row_h + EXTRAS_GAP
            self._resize_window_for_extras(-total_delta)
            for v in self.upper_views:
                f = v.frame()
                v.setFrameOrigin_((f.origin.x, f.origin.y - total_delta))
        # Now add new extras one at a time
        for ex in (extras_data or []):
            self._add_extra_row(
                name_text=ex.get("name", ""),
                path_text=ex.get("file_path") or "",
            )

    def _capture_extras(self):
        """Snapshot extras into a list of {name, file_path} dicts."""
        out = []
        for row in self.extras:
            name = str(row["name_field"].stringValue()).strip()
            path = str(row["path_field"].stringValue()).strip()
            out.append({"name": name, "file_path": path or None})
        return out

    def _apply_settings(self, d):
        """Apply a settings dict to all form controls."""
        track_names = d.get("track_names") or {}
        for role, fld in self.name_fields.items():
            fld.setStringValue_(track_names.get(role.name, role.value))
        if self.folder_field and "folder_name" in d:
            self.folder_field.setStringValue_(d["folder_name"])
        if self.project_field and "project_name" in d:
            self.project_field.setStringValue_(d["project_name"])
        if self.source_res_popup and "source_resolution" in d:
            self.source_res_popup.selectItemWithTitle_(d["source_resolution"])
        if self.fps_popup and "frame_rate" in d:
            self.fps_popup.selectItemWithTitle_(d["frame_rate"])
        if self.tc_field and "start_timecode" in d:
            self.tc_field.setStringValue_(d["start_timecode"])
        if self.timeline_cs_popup and "timeline_color_space" in d:
            self.timeline_cs_popup.selectItemWithTitle_(d["timeline_color_space"])
        if self.output_cs_popup and "output_color_space" in d:
            self.output_cs_popup.selectItemWithTitle_(d["output_color_space"])
        if self.mediainfo_check and "use_mediainfo" in d:
            self.mediainfo_check.setState_(1 if d["use_mediainfo"] else 0)
        if self.ffprobe_check and "use_ffprobe" in d:
            self.ffprobe_check.setState_(1 if d["use_ffprobe"] else 0)
        if self.report_format_popup and "report_format" in d:
            self.report_format_popup.selectItemWithTitle_(d["report_format"])
        if self.marker_popup and "marker_option" in d:
            self.marker_popup.selectItemWithTitle_(d["marker_option"])
        if "extras" in d:
            self._set_extras(d.get("extras") or [])

    def resetDefaultsClicked_(self, sender):
        """Wipe saved settings + bin structure, then re-populate form with factory defaults."""
        from chads_davinci.settings_io import DEFAULT_SETTINGS, reset_user_settings
        reset_user_settings()
        self.bin_roots = None
        self._apply_settings(DEFAULT_SETTINGS)
        if self.status_label:
            self.status_label.setStringValue_("Reset to factory defaults")
            self.status_label.setTextColor_(NSColor.systemGreenColor())

    def _refresh_preset_popup(self, select=None):
        from chads_davinci.settings_io import load_presets
        if not self.preset_popup:
            return
        presets = load_presets()
        self.preset_popup.removeAllItems()
        self.preset_popup.addItemWithTitle_("— Select Preset —")
        for name in sorted(presets.keys()):
            self.preset_popup.addItemWithTitle_(name)
        if select and select in presets:
            self.preset_popup.selectItemWithTitle_(select)

    def presetSelected_(self, sender):
        from chads_davinci.settings_io import load_presets
        idx = sender.indexOfSelectedItem()
        if idx <= 0:
            return
        name = str(sender.titleOfSelectedItem())
        presets = load_presets()
        if name in presets:
            self._apply_settings(presets[name])
            if self.status_label:
                self.status_label.setStringValue_(f"Loaded preset: {name}")
                self.status_label.setTextColor_(NSColor.systemGreenColor())

    def savePresetClicked_(self, sender):
        from chads_davinci.settings_io import load_presets, save_preset
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Save Preset")
        alert.setInformativeText_("Enter a name for this preset:")
        alert.addButtonWithTitle_("Save")
        alert.addButtonWithTitle_("Cancel")
        input_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 240, 24))
        input_field.setBezeled_(True)
        input_field.setEditable_(True)
        existing = load_presets()
        # Pre-fill with currently selected preset name (if any)
        if self.preset_popup and self.preset_popup.indexOfSelectedItem() > 0:
            input_field.setStringValue_(str(self.preset_popup.titleOfSelectedItem()))
        alert.setAccessoryView_(input_field)
        if alert.runModal() != NSAlertFirstButtonReturn:
            return
        name = str(input_field.stringValue()).strip()
        if not name:
            return
        if name in existing:
            confirm = NSAlert.alloc().init()
            confirm.setMessageText_(f'Overwrite preset "{name}"?')
            confirm.addButtonWithTitle_("Overwrite")
            confirm.addButtonWithTitle_("Cancel")
            if confirm.runModal() != NSAlertFirstButtonReturn:
                return
        save_preset(name, self._capture_form_settings())
        self._refresh_preset_popup(select=name)
        if self.status_label:
            self.status_label.setStringValue_(f"Saved preset: {name}")
            self.status_label.setTextColor_(NSColor.systemGreenColor())

    def deletePresetClicked_(self, sender):
        from chads_davinci.settings_io import delete_preset
        if not self.preset_popup or self.preset_popup.indexOfSelectedItem() <= 0:
            return
        name = str(self.preset_popup.titleOfSelectedItem())
        confirm = NSAlert.alloc().init()
        confirm.setMessageText_(f'Delete preset "{name}"?')
        confirm.addButtonWithTitle_("Delete")
        confirm.addButtonWithTitle_("Cancel")
        if confirm.runModal() != NSAlertFirstButtonReturn:
            return
        delete_preset(name)
        self._refresh_preset_popup()
        if self.status_label:
            self.status_label.setStringValue_(f"Deleted preset: {name}")
            self.status_label.setTextColor_(NSColor.systemGreenColor())

    def _capture_form_settings(self) -> dict:
        """Snapshot current form state into a settings dict."""
        return {
            "track_names": {
                role.name: str(self.name_fields[role].stringValue()).strip()
                for role in self.name_fields
            },
            "folder_name": str(self.folder_field.stringValue()).strip() if self.folder_field else "",
            "project_name": str(self.project_field.stringValue()).strip() if self.project_field else "",
            "source_resolution": str(self.source_res_popup.titleOfSelectedItem()) if self.source_res_popup else "",
            "frame_rate": str(self.fps_popup.titleOfSelectedItem()) if self.fps_popup else "",
            "start_timecode": str(self.tc_field.stringValue()).strip() if self.tc_field else "",
            "timeline_color_space": str(self.timeline_cs_popup.titleOfSelectedItem()) if self.timeline_cs_popup else "",
            "output_color_space": str(self.output_cs_popup.titleOfSelectedItem()) if self.output_cs_popup else "",
            "use_mediainfo": bool(self.mediainfo_check.state()) if self.mediainfo_check else True,
            "use_ffprobe": bool(self.ffprobe_check.state()) if self.ffprobe_check else True,
            "report_format": str(self.report_format_popup.titleOfSelectedItem()) if self.report_format_popup else "None",
            "marker_option": str(self.marker_popup.titleOfSelectedItem()) if self.marker_popup else "None",
            "extras": self._capture_extras(),
        }

    def _save_user_settings_from_form(self):
        from chads_davinci.settings_io import save_user_settings
        try:
            save_user_settings(self._capture_form_settings())
        except Exception:
            pass

    # --- Helpers ---

    def _build_assignments(self, all_disabled: bool):
        """Build (track_assignments, track_names) lists for the result.

        If all_disabled, every track is created with enabled=False (metadata-only mode).
        Otherwise required tracks are enabled, optional tracks are disabled.
        """
        track_assignments = [
            TrackAssignment(role=TrackRole.QUAD_TEMPLATE, file_path=None, enabled=False)
        ]
        for role in SELECTABLE_TRACKS:
            enabled = False if all_disabled else (role not in OPTIONAL_TRACKS)
            track_assignments.append(
                TrackAssignment(role=role, file_path=self.assignments[role], enabled=enabled)
            )
        track_names = {
            role: str(self.name_fields[role].stringValue()).strip()
            for role in SELECTABLE_TRACKS
        }
        track_names[TrackRole.QUAD_TEMPLATE] = "QUAD Template"
        return track_assignments, track_names

    def _set_file(self, role, filepath):
        """Store a file path on the assignment dict.

        Strips ONLY leading/trailing whitespace (which can sneak in via
        accidental copy-paste). Deliberately does NOT strip quotes,
        braces, or any other characters that might appear in a
        legitimate filename (e.g. `'commentary'.mov` or `{notes}.mov`).
        """
        cleaned = filepath.strip()
        if cleaned:
            self.assignments[role] = Path(cleaned)

    def _set_status(self, msg):
        # Always log status messages — these are validation errors shown
        # to the user (e.g. "missing required tracks", "select a database")
        # and we want them captured in console.log too.
        _module_console.print(f"[yellow]Picker status: {msg}[/yellow]")
        if self.status_label:
            self.status_label.setStringValue_(msg)
            self.status_label.setTextColor_(NSColor.systemRedColor())

    def _set_status_ok(self, msg):
        """Green confirmation message in the status bar (informational, not error)."""
        _module_console.print(f"[green]Picker status: {msg}[/green]")
        if self.status_label:
            self.status_label.setStringValue_(msg)
            self.status_label.setTextColor_(NSColor.systemGreenColor())

    def _set_status_info(self, msg):
        """Plain informational status (gray). Used during pre-flight."""
        _module_console.print(f"[dim]Picker status: {msg}[/dim]")
        if self.status_label:
            self.status_label.setStringValue_(msg)
            self.status_label.setTextColor_(NSColor.secondaryLabelColor())

    # ----- Pre-flight validation ------------------------------------------

    def _run_preflight(self) -> list[str]:
        """Inspect the assigned files and return a list of warning strings.
        Each warning is a one-line description of a likely setup error.
        Empty list = all good.

        Checks:
          1. Every assigned file actually exists on disk
          2. Frame rate matches across all enabled rows
          3. Resolution matches
          4. Color space matches
          5. Bit depth matches

        Mediainfo runs once per file (cached after first hit). Total
        time is ~1-2 seconds for 6 files.
        """
        from chads_davinci.metadata import extract_mediainfo

        warnings: list[str] = []

        # 1. File existence — most common gotcha (unmounted volume)
        missing = []
        for role in SELECTABLE_TRACKS:
            path = self.assignments.get(role)
            if path is None:
                continue
            try:
                exists = path.exists()
            except OSError:
                exists = False
            if not exists:
                missing.append((role, path))
        if missing:
            for role, path in missing:
                warnings.append(
                    f"⚠️ {role.value}: file does not exist on disk\n"
                    f"   {path}\n"
                    f"   (volume may be unmounted, or the file was moved/deleted)"
                )
            # No point checking metadata if files are missing
            return warnings

        # 2-5. Mediainfo sweep across all assigned files
        metas: dict[TrackRole, object] = {}
        for role in SELECTABLE_TRACKS:
            path = self.assignments.get(role)
            if path is None:
                continue
            try:
                metas[role] = extract_mediainfo(path)
            except Exception:
                pass

        if len(metas) < 2:
            return warnings  # need at least 2 to compare

        def _check_field(field_name: str, label: str) -> None:
            values = {
                role: getattr(m, field_name)
                for role, m in metas.items()
                if getattr(m, field_name)
            }
            unique = set(values.values())
            if len(unique) > 1:
                detail = "\n".join(
                    f"   • {role.value:25}  {val}"
                    for role, val in values.items()
                )
                warnings.append(
                    f"⚠️ {label} mismatch across files:\n{detail}"
                )

        _check_field("frame_rate", "Frame rate")
        _check_field("resolution", "Resolution")
        _check_field("color_space", "Color space")

        # Bit depth is an int, special-case it
        depths = {
            role: m.bit_depth for role, m in metas.items() if m.bit_depth
        }
        if len(set(depths.values())) > 1:
            detail = "\n".join(
                f"   • {role.value:25}  {bd} bit"
                for role, bd in depths.items()
            )
            warnings.append(f"⚠️ Bit depth mismatch across files:\n{detail}")

        return warnings

    def _show_preflight_dialog(self, warnings: list[str]) -> bool:
        """Show a dialog listing the pre-flight warnings.
        Returns True if the user clicks Continue Anyway, False on Cancel."""
        body = (
            "Pre-flight check found possible setup issues:\n\n"
            + "\n\n".join(warnings)
            + "\n\nThese might be intentional, but most of the time they "
            "indicate that the wrong file was assigned to a row, the "
            "wrong project was selected for the source clip, or a "
            "volume is unmounted.\n\nContinue with the build anyway?"
        )

        def _esc(s: str) -> str:
            return (
                s.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\r")
            )

        title = "Pre-flight check found possible issues"
        script = (
            f'display dialog "{_esc(body)}" '
            f'with title "{_esc(title)}" '
            f'buttons {{"Cancel", "Continue Anyway"}} '
            f'default button "Cancel" '
            f'cancel button "Cancel" '
            f'with icon caution'
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
        except Exception as e:
            _module_console.print(
                f"[yellow]Pre-flight dialog failed: {e}[/yellow]"
            )
            return True  # don't block the user if the dialog itself broke

        return result.returncode == 0 and "Continue Anyway" in (result.stdout or "")


# ---------------------------------------------------------------------------
# Window builder helpers
# ---------------------------------------------------------------------------


def _make_label(text, frame, bold=False, size=13.0):
    label = NSTextField.alloc().initWithFrame_(frame)
    label.setStringValue_(text)
    label.setBezeled_(False)
    label.setDrawsBackground_(False)
    label.setEditable_(False)
    label.setSelectable_(False)
    if bold:
        label.setFont_(NSFont.boldSystemFontOfSize_(size))
    else:
        label.setFont_(NSFont.systemFontOfSize_(size))
    return label


def _make_textfield(text, frame):
    field = NSTextField.alloc().initWithFrame_(frame)
    field.setStringValue_(text)
    field.setBezelStyle_(NSTextFieldRoundedBezel)
    field.setBezeled_(True)
    field.setEditable_(True)
    return field


def pick_files():
    """Show the native Cocoa file picker. Returns PickerResult or None."""
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

    # Install the macOS menu bar now that NSApp is initialized
    try:
        from chads_davinci.menu_bar import setup_menu_bar
        setup_menu_bar()
    except Exception:
        pass

    controller = FilePickerController.alloc().init()

    # Window dimensions
    win_w, win_h = 980, 1010
    style = (
        NSWindowStyleMaskTitled
        | NSWindowStyleMaskClosable
        | NSWindowStyleMaskMiniaturizable
    )

    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(100, 100, win_w, win_h),
        style,
        NSBackingStoreBuffered,
        False,
    )
    window.setTitle_("Chad's DaVinci Script - File Assignment")
    window.center()
    controller.window = window

    # Load saved user settings (or empty dict if none)
    from chads_davinci.settings_io import DEFAULT_SETTINGS, load_user_settings
    saved = load_user_settings()
    # Merge saved over defaults
    settings = {**DEFAULT_SETTINGS, **saved}
    saved_track_names = settings.get("track_names") or {}
    controller.saved_settings = settings  # for reset button

    content = window.contentView()

    margin = 20
    row_h = 36
    label_w = 180
    field_w = 580
    btn_w = 90

    controller.row_h_for_extras = row_h
    controller.win_w_for_extras = win_w

    y = win_h - margin - 30

    # Header
    header = _make_label(
        "Assign video files to tracks",
        NSMakeRect(margin, y, 360, 24),
        bold=True, size=16,
    )
    content.addSubview_(header)
    controller.upper_views.append(header)

    # Preset controls (top right): label, popup, Save, Delete
    preset_y = y - 2
    preset_label = _make_label(
        "Preset:", NSMakeRect(win_w - margin - 360, preset_y + 4, 50, 18),
        bold=True, size=11,
    )
    content.addSubview_(preset_label)
    controller.upper_views.append(preset_label)
    preset_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(win_w - margin - 305, preset_y, 180, 24), False
    )
    preset_popup.setTarget_(controller)
    preset_popup.setAction_("presetSelected:")
    content.addSubview_(preset_popup)
    controller.preset_popup = preset_popup
    controller.upper_views.append(preset_popup)

    preset_save_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(win_w - margin - 120, preset_y, 60, 24)
    )
    preset_save_btn.setTitle_("Save")
    preset_save_btn.setBezelStyle_(1)
    preset_save_btn.setToolTip_("Save current settings as a named preset")
    preset_save_btn.setTarget_(controller)
    preset_save_btn.setAction_("savePresetClicked:")
    content.addSubview_(preset_save_btn)
    controller.upper_views.append(preset_save_btn)

    preset_del_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(win_w - margin - 58, preset_y, 58, 24)
    )
    preset_del_btn.setTitle_("Delete")
    preset_del_btn.setBezelStyle_(1)
    preset_del_btn.setToolTip_("Delete the selected preset")
    preset_del_btn.setTarget_(controller)
    preset_del_btn.setAction_("deletePresetClicked:")
    content.addSubview_(preset_del_btn)
    controller.upper_views.append(preset_del_btn)

    controller._refresh_preset_popup()
    y -= 30

    # Column headers
    col_h1 = _make_label(
        "Track Name", NSMakeRect(margin, y, label_w, 18), bold=True, size=11
    )
    content.addSubview_(col_h1)
    controller.upper_views.append(col_h1)
    col_h2 = _make_label(
        "File or first frame of an image sequence (drag, paste, or Browse)",
        NSMakeRect(margin + label_w + 10, y, field_w, 18), bold=True, size=11
    )
    content.addSubview_(col_h2)
    controller.upper_views.append(col_h2)
    # Capture the column-header y in the *initial* layout — extras position
    # themselves relative to this anchor.
    controller.col_headers_y_initial = y
    y -= 24

    # File rows — assign unique tags so action handlers can identify which row
    next_tag = 1000
    for role in SELECTABLE_TRACKS:
        optional = role in OPTIONAL_TRACKS

        # Name field — use saved name if user customized it
        default_name = saved_track_names.get(role.name, role.value)
        name_field = _make_textfield(default_name, NSMakeRect(margin, y, label_w, 24))
        content.addSubview_(name_field)
        controller.name_fields[role] = name_field

        # Path field with drag-drop support via DropTextField subclass
        path_field = DropTextField.alloc().initWithFrame_(
            NSMakeRect(margin + label_w + 10, y, field_w, 24)
        )
        path_field.setStringValue_("")
        path_field.setBezelStyle_(NSTextFieldRoundedBezel)
        path_field.setBezeled_(True)
        path_field.setEditable_(True)
        path_field.setPlaceholderString_("Drop file here or click Browse")
        path_field.setTarget_(controller)
        path_field.setAction_("pathFieldChanged:")
        path_field.setDropTarget_action_(controller, "pathFieldChanged:")
        content.addSubview_(path_field)
        controller.path_fields[role] = path_field

        # Browse button — uses unique tag to identify row in handler
        browse_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(margin + label_w + 10 + field_w + 10, y, btn_w, 24)
        )
        browse_btn.setTitle_("Browse...")
        browse_btn.setBezelStyle_(1)
        browse_btn.setTarget_(controller)
        browse_btn.setAction_("browseClicked:")
        browse_btn.setTag_(next_tag)
        controller.button_roles[next_tag] = role
        next_tag += 1
        content.addSubview_(browse_btn)

        # Small ✕ clear button on every row
        clear_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(margin + label_w + 10 + field_w + 10 + btn_w + 5, y, 28, 24)
        )
        clear_btn.setTitle_("✕")
        clear_btn.setBezelStyle_(7)  # NSBezelStyleCircular
        clear_btn.setToolTip_("Clear file")
        clear_btn.setTarget_(controller)
        clear_btn.setAction_("clearClicked:")
        clear_btn.setTag_(next_tag)
        controller.button_roles[next_tag] = role
        next_tag += 1
        content.addSubview_(clear_btn)

        # NOTE: file rows are NOT in upper_views. Extras grow ABOVE the file rows
        # (between the column headers and REEL SOURCE), so file rows stay put in
        # content coords and naturally move down visually as the window grows.

        if optional:
            # Optional indicator under name field
            opt_label = _make_label(
                "(optional)",
                NSMakeRect(margin + label_w - 60, y - 14, 60, 12),
                size=9,
            )
            opt_label.setTextColor_(NSColor.grayColor())
            content.addSubview_(opt_label)

        y -= row_h

    y -= 10

    # + Add Video Track button (left side, below file rows section).
    # Lives in the LOWER group — does NOT shift when extras are added; the
    # window growing downward keeps it visually below all extras.
    add_track_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(margin - 6, y - 6, 156, 24)
    )
    add_track_btn.setTitle_("+ Add Video Track")
    add_track_btn.setBezelStyle_(1)
    add_track_btn.setToolTip_("Add an additional video track row")
    add_track_btn.setTarget_(controller)
    add_track_btn.setAction_("addExtraTrackClicked:")
    content.addSubview_(add_track_btn)
    y -= 30

    # Separator
    from Quartz import CGColorCreateGenericRGB
    sep_view = NSView.alloc().initWithFrame_(NSMakeRect(margin, y, win_w - 2 * margin, 1))
    sep_view.setWantsLayer_(True)
    sep_view.layer().setBackgroundColor_(CGColorCreateGenericRGB(0.5, 0.5, 0.5, 0.4))
    content.addSubview_(sep_view)
    y -= 20

    # Project Settings header
    proj_header = _make_label(
        "DaVinci Resolve Project Settings",
        NSMakeRect(margin, y, win_w - 2 * margin, 24),
        bold=True, size=16,
    )
    content.addSubview_(proj_header)
    y -= 30

    # Connect button + status (aligned with field column)
    content.addSubview_(_make_label(
        "Resolve:", NSMakeRect(margin, y + 4, label_w, 18), size=12
    ))
    # NSButton bezel adds ~6px inset; offset by -6 so the visible edge lines up
    connect_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(margin + label_w + 10 - 6, y, 166, 24)
    )
    connect_btn.setTitle_("Connect to Resolve")
    connect_btn.setBezelStyle_(1)
    connect_btn.setTarget_(controller)
    connect_btn.setAction_("connectClicked:")
    content.addSubview_(connect_btn)
    controller.connect_btn = connect_btn

    connect_status = _make_label(
        "Not connected to Resolve",
        NSMakeRect(margin + label_w + 10 + 170, y + 4, 280, 18),
        size=11,
    )
    connect_status.setTextColor_(NSColor.grayColor())
    content.addSubview_(connect_status)
    controller.connect_status = connect_status
    y -= row_h

    # Database Type
    content.addSubview_(_make_label(
        "Database Type:", NSMakeRect(margin, y + 4, label_w, 18), size=12
    ))
    db_type_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(margin + label_w + 10, y, field_w, 24), False
    )
    db_type_popup.addItemsWithTitles_(["Local", "Network", "Cloud"])
    db_type_popup.setTarget_(controller)
    db_type_popup.setAction_("dbTypeChanged:")
    content.addSubview_(db_type_popup)
    controller.db_type_popup = db_type_popup
    y -= row_h

    # Database name
    content.addSubview_(_make_label(
        "Database:", NSMakeRect(margin, y + 4, label_w, 18), size=12
    ))
    db_name_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(margin + label_w + 10, y, field_w, 24), False
    )
    content.addSubview_(db_name_popup)
    controller.db_name_popup = db_name_popup
    y -= row_h

    # Folder
    content.addSubview_(_make_label(
        "Folder:", NSMakeRect(margin, y + 4, label_w, 18), size=12
    ))
    folder_field = _make_textfield(settings["folder_name"], NSMakeRect(margin + label_w + 10, y, field_w, 24))
    content.addSubview_(folder_field)
    controller.folder_field = folder_field
    y -= row_h

    # Project Name
    content.addSubview_(_make_label(
        "Project Name:", NSMakeRect(margin, y + 4, label_w, 18), size=12
    ))
    project_field = _make_textfield(settings["project_name"], NSMakeRect(margin + label_w + 10, y, field_w, 24))
    content.addSubview_(project_field)
    controller.project_field = project_field
    y -= row_h

    # Bin structure editor button
    content.addSubview_(_make_label(
        "Bin Structure:", NSMakeRect(margin, y + 4, label_w, 18), size=12
    ))
    edit_bins_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(margin + label_w + 10 - 6, y, 156, 24)
    )
    edit_bins_btn.setTitle_("Edit Bins...")
    edit_bins_btn.setBezelStyle_(1)
    edit_bins_btn.setTarget_(controller)
    edit_bins_btn.setAction_("editBinsClicked:")
    content.addSubview_(edit_bins_btn)
    y -= row_h

    # Source Resolution
    content.addSubview_(_make_label(
        "Source Resolution:", NSMakeRect(margin, y + 4, label_w, 18), size=12
    ))
    source_res_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(margin + label_w + 10, y, field_w, 24), False
    )
    source_res_popup.addItemsWithTitles_(SOURCE_RESOLUTIONS)
    source_res_popup.selectItemWithTitle_(settings["source_resolution"])
    content.addSubview_(source_res_popup)
    controller.source_res_popup = source_res_popup
    y -= row_h

    # Frame Rate
    content.addSubview_(_make_label(
        "Frame Rate:", NSMakeRect(margin, y + 4, label_w, 18), size=12
    ))
    fps_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(margin + label_w + 10, y, field_w, 24), False
    )
    fps_popup.addItemsWithTitles_(FRAME_RATES)
    fps_popup.selectItemWithTitle_(settings["frame_rate"])
    content.addSubview_(fps_popup)
    controller.fps_popup = fps_popup
    y -= row_h

    # Start Timecode
    content.addSubview_(_make_label(
        "Start Timecode:", NSMakeRect(margin, y + 4, label_w, 18), size=12
    ))
    tc_field = _make_textfield(settings["start_timecode"], NSMakeRect(margin + label_w + 10, y, field_w, 24))
    content.addSubview_(tc_field)
    controller.tc_field = tc_field
    y -= row_h

    # Timeline Color Space
    content.addSubview_(_make_label(
        "Timeline Color Space:", NSMakeRect(margin, y + 4, label_w, 18), size=12
    ))
    timeline_cs_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(margin + label_w + 10, y, field_w, 24), False
    )
    timeline_cs_popup.addItemsWithTitles_(COLOR_SPACES)
    timeline_cs_popup.selectItemWithTitle_(settings["timeline_color_space"])
    content.addSubview_(timeline_cs_popup)
    controller.timeline_cs_popup = timeline_cs_popup
    y -= row_h

    # Output Color Space
    content.addSubview_(_make_label(
        "Output Color Space:", NSMakeRect(margin, y + 4, label_w, 18), size=12
    ))
    output_cs_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(margin + label_w + 10, y, field_w, 24), False
    )
    output_cs_popup.addItemsWithTitles_(COLOR_SPACES)
    output_cs_popup.selectItemWithTitle_(settings["output_color_space"])
    content.addSubview_(output_cs_popup)
    controller.output_cs_popup = output_cs_popup
    y -= row_h

    # Metadata extraction toggles
    content.addSubview_(_make_label(
        "Metadata Tools:", NSMakeRect(margin, y + 4, label_w, 18), size=12
    ))
    mediainfo_check = NSButton.alloc().initWithFrame_(
        NSMakeRect(margin + label_w + 10 - 4, y, 130, 24)
    )
    mediainfo_check.setButtonType_(3)  # NSSwitchButton (checkbox)
    mediainfo_check.setTitle_("MediaInfo")
    mediainfo_check.setState_(1 if settings["use_mediainfo"] else 0)
    content.addSubview_(mediainfo_check)
    controller.mediainfo_check = mediainfo_check

    ffprobe_check = NSButton.alloc().initWithFrame_(
        NSMakeRect(margin + label_w + 10 + 140, y, 130, 24)
    )
    ffprobe_check.setButtonType_(3)
    ffprobe_check.setTitle_("ffprobe")
    ffprobe_check.setState_(1 if settings["use_ffprobe"] else 0)
    content.addSubview_(ffprobe_check)
    controller.ffprobe_check = ffprobe_check
    y -= row_h

    # Metadata report format
    content.addSubview_(_make_label(
        "Metadata Report:", NSMakeRect(margin, y + 4, label_w, 18), size=12
    ))
    report_format_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(margin + label_w + 10, y, field_w, 24), False
    )
    report_format_popup.addItemsWithTitles_(REPORT_FORMATS)
    report_format_popup.selectItemWithTitle_(settings["report_format"])
    content.addSubview_(report_format_popup)
    controller.report_format_popup = report_format_popup
    y -= row_h

    # Resolve markers
    content.addSubview_(_make_label(
        "Resolve Markers:", NSMakeRect(margin, y + 4, label_w, 18), size=12
    ))
    marker_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(margin + label_w + 10, y, field_w, 24), False
    )
    marker_popup.addItemsWithTitles_(MARKER_OPTIONS)
    marker_popup.selectItemWithTitle_(settings["marker_option"])
    content.addSubview_(marker_popup)
    controller.marker_popup = marker_popup
    y -= row_h

    # Reset Defaults button (under Resolve Markers, aligned with field column)
    reset_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(margin + label_w + 10 - 6, y, 156, 24)
    )
    reset_btn.setTitle_("Reset Defaults")
    reset_btn.setBezelStyle_(1)
    reset_btn.setToolTip_("Reset all picker fields and bin structure to factory defaults")
    reset_btn.setTarget_(controller)
    reset_btn.setAction_("resetDefaultsClicked:")
    content.addSubview_(reset_btn)
    y -= row_h - 4

    # Status label
    status_label = _make_label("", NSMakeRect(margin, y, win_w - 2 * margin, 18), size=11)
    content.addSubview_(status_label)
    controller.status_label = status_label
    y -= 18

    # Metadata Export button (aligned with field column)
    meta_only_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(margin + label_w + 10 - 6, y - 10, 186, 30)
    )
    meta_only_btn.setTitle_("Metadata Export")
    meta_only_btn.setBezelStyle_(1)
    meta_only_btn.setToolTip_(
        "Extract metadata from any assigned files and save to a folder you choose"
    )
    meta_only_btn.setTarget_(controller)
    meta_only_btn.setAction_("metadataOnlyClicked:")
    content.addSubview_(meta_only_btn)

    # OK / Cancel buttons (bottom right)
    cancel_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(win_w - margin - 200, y - 10, 90, 30)
    )
    cancel_btn.setTitle_("Cancel")
    cancel_btn.setBezelStyle_(1)
    cancel_btn.setTarget_(controller)
    cancel_btn.setAction_("cancelClicked:")
    content.addSubview_(cancel_btn)

    ok_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(win_w - margin - 100, y - 10, 90, 30)
    )
    ok_btn.setTitle_("OK")
    ok_btn.setBezelStyle_(1)
    ok_btn.setKeyEquivalent_("\r")
    ok_btn.setTarget_(controller)
    ok_btn.setAction_("okClicked:")
    content.addSubview_(ok_btn)

    # Show window and run the app loop (non-modal so drag-drop works)
    # Restore any saved extra video tracks from user settings
    if settings.get("extras"):
        controller._set_extras(settings.get("extras") or [])

    window.makeKeyAndOrderFront_(None)
    NSApp.activateIgnoringOtherApps_(True)
    NSApp.run()

    return controller.result
