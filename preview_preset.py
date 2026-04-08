#!/usr/bin/env python3
"""Live INTERACTIVE preview for the preset row layout in Chad's DaVinci Script.

Uses the REAL build_preset_row() function from chads_davinci.file_picker so
the preview matches the live picker pixel-for-pixel — no more standalone-vs-
real mismatch.

Run:    python3 preview_preset.py

Drag the three sliders. Each change rebuilds the row using the actual
production code path. When you find values you like, paste them back into
the PRESET_*_GAP constants in src/chads_davinci/file_picker.py (or just
tell Claude).
"""

import sys
from pathlib import Path

# Make src/ importable
sys.path.insert(0, str(Path(__file__).parent / "src"))

from AppKit import (
    NSApplication, NSWindow, NSTextField, NSColor, NSMakeRect,
    NSBackingStoreBuffered, NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSFont, NSObject, NSSlider,
)
import objc

from chads_davinci import file_picker as fp


WIN_W      = 720
WIN_H      = 320
RIGHT_PAD  = 20


def make_label(text, frame, bold=True, size=11):
    f = NSTextField.alloc().initWithFrame_(frame)
    f.setStringValue_(text)
    f.setBezeled_(False)
    f.setDrawsBackground_(False)
    f.setEditable_(False)
    f.setSelectable_(False)
    if bold:
        f.setFont_(NSFont.boldSystemFontOfSize_(size))
    else:
        f.setFont_(NSFont.systemFontOfSize_(size))
    return f


class Controller(NSObject):
    def initWithContentView_(self, content):
        self = objc.super(Controller, self).init()
        if self is None:
            return None
        self.content = content
        self.row_views = []
        self.value_labels = {}
        return self

    def rebuild_row(self):
        for v in self.row_views:
            v.removeFromSuperview()
        self.row_views = []

        right_x = WIN_W - RIGHT_PAD
        row_y   = WIN_H - 60
        # Real production code path:
        views = fp.build_preset_row(self.content, right_x, row_y)
        self.row_views = list(views)

        for name, lbl in self.value_labels.items():
            current = getattr(fp, name)
            lbl.setStringValue_(f"{current:>4d}")

        print(
            f"PRESET_LABEL_POPUP_GAP={fp.PRESET_LABEL_POPUP_GAP:>4d}  "
            f"PRESET_POPUP_BUTTON_GAP={fp.PRESET_POPUP_BUTTON_GAP:>4d}  "
            f"PRESET_BUTTON_BUTTON_GAP={fp.PRESET_BUTTON_BUTTON_GAP:>4d}"
        )

    def labelPopupChanged_(self, sender):
        fp.PRESET_LABEL_POPUP_GAP = int(round(sender.doubleValue()))
        self.rebuild_row()

    def popupButtonChanged_(self, sender):
        fp.PRESET_POPUP_BUTTON_GAP = int(round(sender.doubleValue()))
        self.rebuild_row()

    def buttonButtonChanged_(self, sender):
        fp.PRESET_BUTTON_BUTTON_GAP = int(round(sender.doubleValue()))
        self.rebuild_row()


def make_slider(controller, action, value, frame):
    s = NSSlider.alloc().initWithFrame_(frame)
    s.setMinValue_(-15.0)
    s.setMaxValue_(15.0)
    s.setDoubleValue_(float(value))
    s.setNumberOfTickMarks_(31)
    s.setAllowsTickMarkValuesOnly_(True)
    s.setContinuous_(True)
    s.setTarget_(controller)
    s.setAction_(action)
    return s


_live_controller = None


def main():
    global _live_controller
    app = NSApplication.sharedApplication()
    style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(200, 400, WIN_W, WIN_H), style, NSBackingStoreBuffered, False
    )
    win.setTitle_("Preset Row Live Preview — uses real build_preset_row()")
    content = win.contentView()

    controller = Controller.alloc().initWithContentView_(content)

    rows = [
        ("PRESET_LABEL_POPUP_GAP",   "labelPopupChanged:",   "Preset:  →  popup"),
        ("PRESET_POPUP_BUTTON_GAP",  "popupButtonChanged:",  "popup    →  Save"),
        ("PRESET_BUTTON_BUTTON_GAP", "buttonButtonChanged:", "Save     →  Delete"),
    ]
    base_y = WIN_H - 130
    for i, (name, action, desc) in enumerate(rows):
        y = base_y - i * 50
        content.addSubview_(make_label(desc, NSMakeRect(20, y + 4, 180, 18),
                                       bold=False, size=12))
        slider = make_slider(controller, action, getattr(fp, name),
                             NSMakeRect(210, y, 380, 24))
        content.addSubview_(slider)
        val = make_label(f"{getattr(fp, name):>4d}",
                         NSMakeRect(600, y + 4, 60, 18), bold=True, size=14)
        content.addSubview_(val)
        controller.value_labels[name] = val

    hint = make_label(
        "Range -15 to 15 (frame px). Renders via the REAL build_preset_row().",
        NSMakeRect(20, 10, WIN_W - 40, 16),
        bold=False, size=10,
    )
    hint.setTextColor_(NSColor.secondaryLabelColor())
    content.addSubview_(hint)

    controller.rebuild_row()
    _live_controller = controller

    win.makeKeyAndOrderFront_(None)
    win.orderFrontRegardless()
    app.activateIgnoringOtherApps_(True)
    app.run()


if __name__ == "__main__":
    main()
