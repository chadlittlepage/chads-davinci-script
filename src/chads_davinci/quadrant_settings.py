"""Quadrant Settings dialog — assign tracks to quadrants and customize transforms.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import re

import objc
from AppKit import (
    NSApp,
    NSAppearance,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSButton,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSMakeRect,
    NSObject,
    NSPopUpButton,
    NSScrollView,
    NSString,
    NSTableColumn,
    NSTableView,
    NSTextField,
    NSTextFieldRoundedBezel,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSIndexSet

from chads_davinci.models import (
    DEFAULT_TRACK_QUADRANTS,
    Quadrant,
    SELECTABLE_TRACKS,
    TrackRole,
    quadrant_offsets,
)
from chads_davinci.theme import BG_DARK, FIELD_BG, TEXT_DIM, TEXT_WHITE

_RETAINED = []


class QuadPreviewView(NSView):
    """Draws a 16:9 quad-view monitor showing which quadrant is active."""

    def init(self):
        self = objc.super(QuadPreviewView, self).init()
        if self is not None:
            self._active_quad = None  # "Q1", "Q2", "Q3", "Q4" or None
            self._track_name = ""
        return self

    def set_active(self, quad_str, track_name=""):
        self._active_quad = quad_str
        self._track_name = track_name or ""
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        frame = self.bounds()
        fw, fh = float(frame.size.width), float(frame.size.height)

        # Draw within a 16:9 aspect ratio centered in the view
        aspect = 16.0 / 9.0
        if fw / fh > aspect:
            draw_h = fh - 4
            draw_w = draw_h * aspect
        else:
            draw_w = fw - 4
            draw_h = draw_w / aspect
        ox = (fw - draw_w) / 2.0
        oy = (fh - draw_h) / 2.0

        # Background (dark screen)
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.08, 0.08, 0.08, 1.0).set()
        NSBezierPath.bezierPathWithRect_(NSMakeRect(ox, oy, draw_w, draw_h)).fill()

        half_w = draw_w / 2.0
        half_h = draw_h / 2.0

        # Quadrant rects (Cocoa Y is bottom-up)
        quads = {
            "Q1": NSMakeRect(ox, oy + half_h, half_w, half_h),           # top-left
            "Q2": NSMakeRect(ox + half_w, oy + half_h, half_w, half_h),  # top-right
            "Q3": NSMakeRect(ox, oy, half_w, half_h),                     # bottom-left
            "Q4": NSMakeRect(ox + half_w, oy, half_w, half_h),           # bottom-right
        }

        # Draw active quadrant highlight
        if self._active_quad in quads:
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.0, 0.4, 0.85, 0.35).set()
            NSBezierPath.bezierPathWithRect_(quads[self._active_quad]).fill()

        # Draw grid lines
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.4, 0.4, 0.38, 1.0).set()
        vline = NSBezierPath.bezierPath()
        vline.moveToPoint_((ox + half_w, oy))
        vline.lineToPoint_((ox + half_w, oy + draw_h))
        vline.setLineWidth_(1.0)
        vline.stroke()
        hline = NSBezierPath.bezierPath()
        hline.moveToPoint_((ox, oy + half_h))
        hline.lineToPoint_((ox + draw_w, oy + half_h))
        hline.setLineWidth_(1.0)
        hline.stroke()

        # Border
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.5, 0.5, 0.48, 1.0).set()
        border = NSBezierPath.bezierPathWithRect_(NSMakeRect(ox, oy, draw_w, draw_h))
        border.setLineWidth_(1.5)
        border.stroke()

        # Quad labels + active track name
        dim_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.5, 0.5, 0.48, 1.0)
        bright_color = NSColor.whiteColor()
        label_font = NSFont.systemFontOfSize_(10)
        name_font = NSFont.boldSystemFontOfSize_(11)

        for q_name, q_rect in quads.items():
            is_active = (q_name == self._active_quad)
            qx = float(q_rect.origin.x)
            qy = float(q_rect.origin.y)
            qw = float(q_rect.size.width)
            qh = float(q_rect.size.height)

            attrs = {
                NSFontAttributeName: label_font,
                NSForegroundColorAttributeName: bright_color if is_active else dim_color,
            }
            label_str = NSString.stringWithString_(q_name)
            lx = qx + qw / 2.0 - 8
            ly = qy + qh / 2.0
            label_str.drawAtPoint_withAttributes_((lx, ly), attrs)

            if is_active and self._track_name:
                name_attrs = {
                    NSFontAttributeName: name_font,
                    NSForegroundColorAttributeName: bright_color,
                }
                name_str = NSString.stringWithString_(self._track_name)
                name_size = name_str.sizeWithAttributes_(name_attrs)
                nx = qx + (qw - float(name_size.width)) / 2.0
                ny = ly - 18
                name_str.drawAtPoint_withAttributes_((nx, ny), name_attrs)

# Module-level reference to the currently-open dialog controller, so the
# file picker can live-update the track list when + Add Video Track or the
# delete button are used while the dialog is open.
_CURRENT_DIALOG = None


def get_current_dialog():
    """Return the active QuadrantSettingsController, or None."""
    return _CURRENT_DIALOG

# Transform field definitions: (key, label, default_value)
_FLOAT_FIELDS = [
    ("zoom_x", "Zoom X", 1.0),
    ("zoom_y", "Zoom Y", 1.0),
    ("position_x", "Position X", 0.0),
    ("position_y", "Position Y", 0.0),
    ("rotation_angle", "Rotation Angle", 0.0),
    ("anchor_point_x", "Anchor Point X", 0.0),
    ("anchor_point_y", "Anchor Point Y", 0.0),
    ("pitch", "Pitch", 0.0),
    ("yaw", "Yaw", 0.0),
]


def _current_timeline_size() -> tuple[int, int]:
    """Read the source resolution from user_settings.json and return
    the timeline size (source × 2). Falls back to 8K if not set."""
    try:
        from chads_davinci.settings_io import load_user_settings
        s = load_user_settings() or {}
        src = s.get("source_resolution", "")
        m = re.search(r"(\d+)\s*x\s*(\d+)", src)
        if m:
            sw, sh = int(m.group(1)), int(m.group(2))
            return sw * 2, sh * 2
    except Exception:
        pass
    return 7680, 4320


def _make_label(text, frame, bold=False, size=13.0):
    label = NSTextField.alloc().initWithFrame_(frame)
    label.setStringValue_(text)
    label.setBezeled_(False)
    label.setDrawsBackground_(False)
    label.setEditable_(False)
    label.setSelectable_(False)
    label.setTextColor_(TEXT_WHITE)
    if bold:
        label.setFont_(NSFont.boldSystemFontOfSize_(size))
    else:
        label.setFont_(NSFont.systemFontOfSize_(size))
    return label


def _make_field(text, frame):
    field = NSTextField.alloc().initWithFrame_(frame)
    field.setStringValue_(str(text))
    field.setBezelStyle_(NSTextFieldRoundedBezel)
    field.setBezeled_(True)
    field.setEditable_(True)
    field.setBackgroundColor_(FIELD_BG)
    field.setTextColor_(TEXT_WHITE)
    field.setFont_(NSFont.systemFontOfSize_(12))
    return field


def _default_track_config(role_or_name, tl_w: int, tl_h: int) -> dict:
    """Build the default config dict for a track (built-in or extra)."""
    if isinstance(role_or_name, TrackRole):
        quad = DEFAULT_TRACK_QUADRANTS.get(role_or_name, Quadrant.Q1)
    else:
        quad = Quadrant.Q1  # extras default to Q1
    px, py = quadrant_offsets(quad, tl_w, tl_h)
    return {
        "quadrant": quad.value,
        "zoom_x": 1.0,
        "zoom_y": 1.0,
        "position_x": px,
        "position_y": py,
        "rotation_angle": 0.0,
        "anchor_point_x": 0.0,
        "anchor_point_y": 0.0,
        "pitch": 0.0,
        "yaw": 0.0,
        "flip_h": False,
        "flip_v": False,
    }


# ---------------------------------------------------------------------------
# Table data source
# ---------------------------------------------------------------------------

class TrackListDataSource(NSObject):
    def init(self):
        self = objc.super(TrackListDataSource, self).init()
        if self is not None:
            self.entries = []  # list of (key, display_name)
        return self

    @objc.signature(b"q@:@")
    def numberOfRowsInTableView_(self, table_view):
        return len(self.entries)

    def tableView_objectValueForTableColumn_row_(self, table_view, column, row):
        if row < 0 or row >= len(self.entries):
            return ""
        return self.entries[row][1]


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class QuadrantSettingsController(NSObject):
    def init(self):
        self = objc.super(QuadrantSettingsController, self).init()
        if self is not None:
            self.window = None
            self.table_view = None
            self.data_source = None
            self.working = {}  # {key: config dict}  key = TrackRole.name or "extra:name"
            self.entries = []  # list of (key, display_name) in table order
            self.extras_data = []  # list of {"name": str, "file_path": str|None}
            self.field_refs = {}
            self.quad_popup = None
            self.flip_h_check = None
            self.flip_v_check = None
            self._updating_fields = False
            self._current_row = -1
            self.tl_w = 7680
            self.tl_h = 4320
            self.quad_preview = None  # QuadPreviewView
        return self

    # ---- Loading ---------------------------------------------------------

    def _load_working(self):
        """Build the entries list and working dict from saved files.

        Order matches the picker + Resolve stacking: extras first (newest
        at top, matching picker visual), then built-in tracks in
        SELECTABLE_TRACKS order.
        """
        from chads_davinci.settings_io import load_quadrant_settings, load_user_settings

        self.tl_w, self.tl_h = _current_timeline_size()

        saved_quad = load_quadrant_settings() or {}
        quad_tracks = saved_quad.get("tracks", {}) if isinstance(saved_quad, dict) else {}
        quad_extras = saved_quad.get("extras", []) if isinstance(saved_quad, dict) else []

        self.entries = []
        self.working = {}

        # Extras from user_settings.json (file picker) — topmost first
        us = load_user_settings() or {}
        self.extras_data = list(us.get("extras") or [])

        # Match quad_extras by name to pick up saved transform configs
        quad_extras_by_name = {e.get("name"): e for e in quad_extras if isinstance(e, dict)}

        for i, extra in enumerate(self.extras_data):
            name = (extra or {}).get("name") or f"Extra {i + 1}"
            key = f"extra:{name}"
            if name in quad_extras_by_name:
                cfg = _default_track_config(name, self.tl_w, self.tl_h)
                cfg.update({k: v for k, v in quad_extras_by_name[name].items() if k != "name"})
            else:
                cfg = _default_track_config(name, self.tl_w, self.tl_h)
            self.working[key] = cfg
            self.entries.append((key, name))

        # Built-in tracks (in SELECTABLE_TRACKS order)
        for role in SELECTABLE_TRACKS:
            key = role.name
            display = role.value
            if key in quad_tracks:
                cfg = _default_track_config(role, self.tl_w, self.tl_h)
                cfg.update(quad_tracks[key])
            else:
                cfg = _default_track_config(role, self.tl_w, self.tl_h)
            self.working[key] = cfg
            self.entries.append((key, display))

    def refresh_from_picker(self, extras_data: list[dict]):
        """Re-sync the track list from the picker's current extras.

        Preserves any in-progress edits to working configs by keeping
        existing entries that still exist, removing deleted ones, and
        adding new ones with default transforms.
        """
        # Save current row's field edits first
        self._save_current_fields()

        # Rebuild entries list from scratch to match picker order
        new_entries = []
        new_working = {}

        # Keep track of picker extras in top-to-bottom order
        for i, extra in enumerate(extras_data or []):
            name = (extra or {}).get("name") or f"Extra {i + 1}"
            key = f"extra:{name}"
            # Preserve existing transform config if present
            if key in self.working:
                new_working[key] = self.working[key]
            else:
                new_working[key] = _default_track_config(name, self.tl_w, self.tl_h)
            new_entries.append((key, name))

        # Built-in tracks (preserve existing configs)
        for role in SELECTABLE_TRACKS:
            key = role.name
            if key in self.working:
                new_working[key] = self.working[key]
            else:
                new_working[key] = _default_track_config(role, self.tl_w, self.tl_h)
            new_entries.append((key, role.value))

        self.entries = new_entries
        self.working = new_working
        self.extras_data = list(extras_data or [])

        # Refresh the table
        if self.data_source is not None:
            self.data_source.entries = list(self.entries)
        if self.table_view is not None:
            self.table_view.reloadData()
            # Try to restore selection to the same key if still present
            selected_key = self._selected_key()
            target_row = 0
            if selected_key is not None:
                for i, (k, _) in enumerate(self.entries):
                    if k == selected_key:
                        target_row = i
                        break
            if self.entries:
                self.table_view.selectRowIndexes_byExtendingSelection_(
                    NSIndexSet.indexSetWithIndex_(target_row), False
                )
            self._populate_detail()

    def _refresh_table(self):
        if self.data_source is not None:
            self.data_source.entries = list(self.entries)
        if self.table_view is not None:
            self.table_view.reloadData()

    # ---- Row helpers -----------------------------------------------------

    def _key_for_row(self, row: int) -> str | None:
        if row < 0 or row >= len(self.entries):
            return None
        return self.entries[row][0]

    def _selected_key(self) -> str | None:
        if self.table_view is None:
            return None
        return self._key_for_row(self.table_view.selectedRow())

    # ---- Detail panel ----------------------------------------------------

    def _save_row_fields(self, row: int):
        key = self._key_for_row(row)
        if key is None or key not in self.working:
            return
        cfg = self.working[key]
        for k, _, _ in _FLOAT_FIELDS:
            fld = self.field_refs.get(k)
            if fld:
                try:
                    cfg[k] = float(fld.stringValue())
                except (ValueError, TypeError):
                    pass
        if self.flip_h_check:
            cfg["flip_h"] = bool(self.flip_h_check.state())
        if self.flip_v_check:
            cfg["flip_v"] = bool(self.flip_v_check.state())
        if self.quad_popup:
            cfg["quadrant"] = str(self.quad_popup.titleOfSelectedItem())

    def _save_current_fields(self):
        self._save_row_fields(self._current_row)

    def _populate_detail(self):
        key = self._selected_key()
        if key is None or key not in self.working:
            return
        self._updating_fields = True
        cfg = self.working[key]
        if self.quad_popup:
            self.quad_popup.selectItemWithTitle_(cfg.get("quadrant", "Q1"))
        for k, _, _ in _FLOAT_FIELDS:
            fld = self.field_refs.get(k)
            if fld:
                val = cfg.get(k, 0.0)
                fld.setStringValue_(f"{val:.3f}")
        if self.flip_h_check:
            self.flip_h_check.setState_(1 if cfg.get("flip_h") else 0)
        if self.flip_v_check:
            self.flip_v_check.setState_(1 if cfg.get("flip_v") else 0)
        self._updating_fields = False
        if self.table_view is not None:
            self._current_row = self.table_view.selectedRow()
        self._update_quad_preview()

    def _update_quad_preview(self):
        if self.quad_preview is None:
            return
        key = self._selected_key()
        if key is None or key not in self.working:
            self.quad_preview.set_active(None, "")
            return
        cfg = self.working[key]
        q_str = cfg.get("quadrant", "Q1")
        # Get display name
        display_name = ""
        if self._current_row >= 0 and self._current_row < len(self.entries):
            display_name = self.entries[self._current_row][1]
        self.quad_preview.set_active(q_str, display_name)

    # ---- Actions ---------------------------------------------------------

    def tableViewSelectionDidChange_(self, notification):
        self._save_current_fields()
        self._populate_detail()

    def quadrantChanged_(self, sender):
        if self._updating_fields:
            return
        key = self._selected_key()
        if key is None or key not in self.working:
            return
        cfg = self.working[key]
        q_str = str(sender.titleOfSelectedItem())
        cfg["quadrant"] = q_str
        try:
            quad = Quadrant(q_str)
        except ValueError:
            return
        px, py = quadrant_offsets(quad, self.tl_w, self.tl_h)
        cfg["position_x"] = px
        cfg["position_y"] = py
        if self.field_refs.get("position_x"):
            self.field_refs["position_x"].setStringValue_(f"{px:.3f}")
        if self.field_refs.get("position_y"):
            self.field_refs["position_y"].setStringValue_(f"{py:.3f}")
        self._update_quad_preview()

    def windowWillClose_(self, notification):
        """Clear the module-level reference when the dialog closes."""
        global _CURRENT_DIALOG
        _CURRENT_DIALOG = None

    def saveClicked_(self, sender):
        self._save_current_fields()
        from chads_davinci.settings_io import (
            load_user_settings, save_quadrant_settings, save_user_settings,
        )

        # Split working dict into tracks vs extras
        tracks_out = {}
        extras_out = []
        for key, cfg in self.working.items():
            if key.startswith("extra:"):
                name = key[len("extra:"):]
                entry = dict(cfg)
                entry["name"] = name
                extras_out.append(entry)
            else:
                tracks_out[key] = cfg

        save_quadrant_settings({
            "version": 1,
            "tracks": tracks_out,
            "extras": extras_out,
        })

        # Persist the extras list to user_settings.json so the file picker
        # sees any tracks added from this dialog on next open.
        us = load_user_settings() or {}
        us["extras"] = self.extras_data
        save_user_settings(us)

        if self.window:
            self.window.close()

    def cancelClicked_(self, sender):
        if self.window:
            self.window.close()

    def resetDefaultsClicked_(self, sender):
        from chads_davinci.settings_io import reset_quadrant_settings
        reset_quadrant_settings()
        # Reset built-in tracks only; leave extras in place but reset their transforms
        for role in SELECTABLE_TRACKS:
            self.working[role.name] = _default_track_config(role, self.tl_w, self.tl_h)
        for extra in self.extras_data:
            name = extra.get("name") or ""
            key = f"extra:{name}"
            if key in self.working:
                self.working[key] = _default_track_config(name, self.tl_w, self.tl_h)
        self._populate_detail()


# ---------------------------------------------------------------------------
# Show the dialog
# ---------------------------------------------------------------------------

def show_quadrant_settings() -> None:
    """Open the Settings dialog. Only one instance at a time."""
    global _CURRENT_DIALOG
    # If already open, just bring it to front
    if _CURRENT_DIALOG is not None and _CURRENT_DIALOG.window is not None:
        _CURRENT_DIALOG.window.makeKeyAndOrderFront_(None)
        if hasattr(NSApp, "activate"):
            NSApp.activate()
        else:
            NSApp.activateIgnoringOtherApps_(True)
        return

    controller = QuadrantSettingsController.alloc().init()
    controller._load_working()

    win_w, win_h = 820, 640
    style = (
        NSWindowStyleMaskTitled
        | NSWindowStyleMaskClosable
        | NSWindowStyleMaskMiniaturizable
    )

    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(200, 200, win_w, win_h),
        style,
        NSBackingStoreBuffered,
        False,
    )
    window.setTitle_("Quadrant Settings")
    window.center()
    window.setBackgroundColor_(BG_DARK)
    dark_appearance = NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua")
    if dark_appearance:
        window.setAppearance_(dark_appearance)
    controller.window = window

    content = window.contentView()
    margin = 16
    btn_h = 28

    # --- Title ---
    title = _make_label(
        "Quadrant Settings",
        NSMakeRect(margin, win_h - margin - 24, win_w - 2 * margin, 24),
        bold=True, size=16,
    )
    content.addSubview_(title)

    # --- Left panel: track list ---
    list_w = 220
    list_top = win_h - margin - 34
    list_bottom = margin + btn_h + 16
    list_h = list_top - list_bottom

    scroll = NSScrollView.alloc().initWithFrame_(
        NSMakeRect(margin, list_bottom, list_w, list_h)
    )
    scroll.setHasVerticalScroller_(True)
    scroll.setBorderType_(2)  # NSBezelBorder

    table = NSTableView.alloc().initWithFrame_(
        NSMakeRect(0, 0, list_w - 20, list_h)
    )
    col = NSTableColumn.alloc().initWithIdentifier_("track")
    col.setWidth_(list_w - 24)
    col.headerCell().setStringValue_("Track")
    table.addTableColumn_(col)
    table.setHeaderView_(None)
    table.setRowHeight_(24)
    table.setBackgroundColor_(FIELD_BG)

    data_source = TrackListDataSource.alloc().init()
    data_source.entries = list(controller.entries)
    table.setDataSource_(data_source)
    table.setDelegate_(controller)
    table.reloadData()

    scroll.setDocumentView_(table)
    content.addSubview_(scroll)
    controller.table_view = table
    controller.data_source = data_source

    # --- Right panel: detail area ---
    detail_x = margin + list_w + 12
    detail_w = win_w - detail_x - margin

    # Quadrant dropdown
    y = list_top - 4
    content.addSubview_(_make_label(
        "Quadrant:", NSMakeRect(detail_x, y, 100, 20), bold=True, size=12
    ))
    quad_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(detail_x + 105, y - 2, 100, 24), False
    )
    quad_popup.addItemsWithTitles_(["Q1", "Q2", "Q3", "Q4"])
    quad_popup.setTarget_(controller)
    quad_popup.setAction_("quadrantChanged:")
    content.addSubview_(quad_popup)
    controller.quad_popup = quad_popup

    # Transform header
    y -= 40
    content.addSubview_(_make_label(
        "Transform", NSMakeRect(detail_x, y, detail_w, 20), bold=True, size=14
    ))

    # Float fields — two-column layout
    y -= 10
    label_w = 110
    field_w = 120
    row_h = 32
    col2_offset = label_w + field_w + 20

    controller.field_refs = {}

    def _add_row(i, key, label, default, side):
        """side: 0=left, 1=right"""
        lx = detail_x if side == 0 else detail_x + col2_offset
        content.addSubview_(_make_label(
            label + ":", NSMakeRect(lx, y + 4, label_w, 18), size=11
        ))
        fld = _make_field(f"{default:.3f}", NSMakeRect(lx + label_w, y, field_w, 24))
        content.addSubview_(fld)
        controller.field_refs[key] = fld

    # Row 1: Zoom X / Zoom Y
    y -= row_h
    _add_row(0, "zoom_x", "Zoom X", 1.0, 0)
    _add_row(1, "zoom_y", "Zoom Y", 1.0, 1)

    # Row 2: Position X / Y
    y -= row_h
    _add_row(2, "position_x", "Position X", 0.0, 0)
    _add_row(3, "position_y", "Position Y", 0.0, 1)

    # Row 3: Rotation Angle (solo)
    y -= row_h
    _add_row(4, "rotation_angle", "Rotation Angle", 0.0, 0)

    # Row 4: Anchor Point X / Y
    y -= row_h
    _add_row(5, "anchor_point_x", "Anchor Point X", 0.0, 0)
    _add_row(6, "anchor_point_y", "Anchor Point Y", 0.0, 1)

    # Row 5: Pitch / Yaw
    y -= row_h
    _add_row(7, "pitch", "Pitch", 0.0, 0)
    _add_row(8, "yaw", "Yaw", 0.0, 1)

    # Flip checkboxes
    y -= row_h + 4
    flip_h = NSButton.alloc().initWithFrame_(
        NSMakeRect(detail_x, y, 150, 24)
    )
    flip_h.setButtonType_(3)  # NSSwitchButton
    flip_h.setTitle_("Flip Horizontal")
    content.addSubview_(flip_h)
    controller.flip_h_check = flip_h

    flip_v = NSButton.alloc().initWithFrame_(
        NSMakeRect(detail_x + col2_offset, y, 150, 24)
    )
    flip_v.setButtonType_(3)
    flip_v.setTitle_("Flip Vertical")
    content.addSubview_(flip_v)
    controller.flip_v_check = flip_v

    # Note about resolution
    y -= 28
    note = _make_label(
        f"Positions shown for current timeline ({controller.tl_w}x{controller.tl_h}).",
        NSMakeRect(detail_x, y, detail_w, 16),
        size=10,
    )
    note.setTextColor_(TEXT_DIM)
    content.addSubview_(note)

    # --- Quad Preview ---
    y -= 10
    preview_h = 140
    preview = QuadPreviewView.alloc().initWithFrame_(
        NSMakeRect(detail_x, y - preview_h, detail_w, preview_h)
    )
    content.addSubview_(preview)
    controller.quad_preview = preview
    y -= preview_h

    # --- Bottom buttons ---
    reset_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(margin, margin, 130, btn_h)
    )
    reset_btn.setTitle_("Reset Defaults")
    reset_btn.setBezelStyle_(1)
    reset_btn.setTarget_(controller)
    reset_btn.setAction_("resetDefaultsClicked:")
    content.addSubview_(reset_btn)

    cancel_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(win_w - margin - 190, margin, 90, btn_h)
    )
    cancel_btn.setTitle_("Cancel")
    cancel_btn.setBezelStyle_(1)
    cancel_btn.setKeyEquivalent_("\x1b")  # ESC key
    cancel_btn.setTarget_(controller)
    cancel_btn.setAction_("cancelClicked:")
    content.addSubview_(cancel_btn)

    # Hidden Cmd+. cancel shortcut (standard macOS cancel)
    cmd_dot_btn = NSButton.alloc().initWithFrame_(NSMakeRect(-100, -100, 1, 1))
    cmd_dot_btn.setKeyEquivalent_(".")
    cmd_dot_btn.setKeyEquivalentModifierMask_(1 << 20)  # Cmd
    cmd_dot_btn.setTarget_(controller)
    cmd_dot_btn.setAction_("cancelClicked:")
    content.addSubview_(cmd_dot_btn)

    save_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(win_w - margin - 90, margin, 90, btn_h)
    )
    save_btn.setTitle_("Save")
    save_btn.setBezelStyle_(1)
    save_btn.setKeyEquivalent_("\r")
    save_btn.setTarget_(controller)
    save_btn.setAction_("saveClicked:")
    content.addSubview_(save_btn)

    # Select first track and populate
    if controller.entries:
        table.selectRowIndexes_byExtendingSelection_(
            NSIndexSet.indexSetWithIndex_(0), False
        )
        controller._populate_detail()

    # Wire up window delegate so we know when it closes
    window.setDelegate_(controller)

    # Publish as the current dialog so the picker can push updates
    _CURRENT_DIALOG = controller

    window.makeKeyAndOrderFront_(None)
    if hasattr(NSApp, "activate"):
        NSApp.activate()
    else:
        NSApp.activateIgnoringOtherApps_(True)

    _RETAINED.append((controller, window, data_source))
