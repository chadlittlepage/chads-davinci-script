"""About window with carbon-nanotube background image.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

from pathlib import Path

import objc
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSFont,
    NSImage,
    NSImageView,
    NSImageScaleAxesIndependently,
    NSMakeRect,
    NSObject,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)

from chads_davinci import __version__

# Module-level retention to prevent GC
_RETAINED = []


def _find_asset(name: str) -> Path | None:
    """Find an asset file by name. Looks in package resources and dev path."""
    # Try package resource path (when bundled by py2app)
    try:
        import sys
        if hasattr(sys, "_MEIPASS"):  # PyInstaller fallback
            p = Path(sys._MEIPASS) / "assets" / name
            if p.exists():
                return p
    except Exception:
        pass

    # Try py2app Resources folder
    here = Path(__file__).resolve()
    candidates = [
        # Inside .app bundle: .app/Contents/Resources/assets/
        here.parent.parent.parent.parent.parent / "Resources" / "assets" / name,
        # Dev mode: project_root/assets/
        here.parent.parent.parent.parent / "assets" / name,
        # Alternative dev paths
        Path.cwd() / "assets" / name,
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


class AboutController(NSObject):
    """Controller for the About window."""

    def init(self):
        self = objc.super(AboutController, self).init()
        if self is not None:
            self.window = None
        return self

    def closeClicked_(self, sender):
        if self.window:
            self.window.close()


def show_about_window() -> None:
    """Show the About window. Non-modal so user can close anytime."""
    controller = AboutController.alloc().init()

    win_w, win_h = 640, 480
    style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable

    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, win_w, win_h),
        style,
        NSBackingStoreBuffered,
        False,
    )
    window.setTitle_("About Chad's DaVinci Script")
    window.center()
    controller.window = window

    content = window.contentView()

    # Background image
    bg_path = _find_asset("about_background.jpg")
    if bg_path is not None:
        bg_image = NSImage.alloc().initByReferencingFile_(str(bg_path))
        if bg_image is not None:
            image_view = NSImageView.alloc().initWithFrame_(NSMakeRect(0, 0, win_w, win_h))
            image_view.setImage_(bg_image)
            image_view.setImageScaling_(NSImageScaleAxesIndependently)
            image_view.setAutoresizingMask_(2 | 16)  # flexible W + H
            content.addSubview_(image_view)

    # Semi-transparent dark overlay covering the entire window for text readability.
    # Use Quartz CGColorCreateGenericRGB so PyObjC's bridge knows the type
    # (avoids ObjCPointerWarning that NSColor.CGColor() triggers).
    from Quartz import CGColorCreateGenericRGB
    overlay = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, win_w, win_h))
    overlay.setWantsLayer_(True)
    overlay.layer().setBackgroundColor_(CGColorCreateGenericRGB(0.0, 0.0, 0.0, 0.65))
    overlay.setAutoresizingMask_(2 | 16)
    content.addSubview_(overlay)

    # Dark overlay text container — labels stacked vertically, centered
    def add_label(text: str, y: float, size: float, bold: bool = False) -> NSTextField:
        label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(20, y, win_w - 40, size + 8)
        )
        label.setStringValue_(text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(True)
        label.setTextColor_(NSColor.whiteColor())
        label.setAlignment_(2)  # NSCenterTextAlignment
        if bold:
            label.setFont_(NSFont.boldSystemFontOfSize_(size))
        else:
            label.setFont_(NSFont.systemFontOfSize_(size))
        label.setAutoresizingMask_(2 | 8)  # flexible width + bottom margin
        content.addSubview_(label)
        return label

    # Title and credits — vertical stack from top
    add_label("Chad's DaVinci Script", win_h - 80, 32, bold=True)
    add_label(f"Version {__version__}", win_h - 120, 16)
    add_label("DaVinci Resolve Quad-View Tool", win_h - 165, 14)

    add_label("Created by Chad Littlepage", win_h - 240, 16, bold=True)
    add_label("chad.littlepage@gmail.com", win_h - 270, 13)
    add_label("323.974.0444", win_h - 295, 13)

    add_label("© 2026 Chad Littlepage", win_h - 360, 11)

    # Close button
    close_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect((win_w - 100) / 2, 30, 100, 32)
    )
    close_btn.setTitle_("Close")
    close_btn.setBezelStyle_(1)
    close_btn.setKeyEquivalent_("\r")
    close_btn.setTarget_(controller)
    close_btn.setAction_("closeClicked:")
    close_btn.setAutoresizingMask_(1 | 4 | 32)  # left + right + top margin flex
    content.addSubview_(close_btn)

    window.makeKeyAndOrderFront_(None)
    NSApp.activateIgnoringOtherApps_(True)

    _RETAINED.append((controller, window))
