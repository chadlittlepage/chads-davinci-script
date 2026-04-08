"""Floating progress window for the build pipeline.

Shows a spinning indicator + a status label that the build script
updates at each phase. The window is at NSFloatingWindowLevel so it
stays above DaVinci Resolve, signaling to the user "don't touch
anything until this completes."

Pumps the Cocoa run loop briefly on every status update so the
window actually repaints during synchronous work in build_main.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSColor,
    NSFont,
    NSMakeRect,
    NSProgressIndicator,
    NSProgressIndicatorStyleSpinning,
    NSTextField,
    NSWindow,
    NSWindowStyleMaskTitled,
)
from Foundation import NSDate, NSDefaultRunLoopMode, NSRunLoop

# Module-level retention so the window object isn't GC'd while it's visible.
_RETAINED: list = []

# NSWindow.level constants — kept here so we don't pull in extra symbols.
_NS_FLOATING_WINDOW_LEVEL = 3


class ProgressWindow:
    """A small, always-on-top progress window with a spinner and status label.

    Usage:
        progress = ProgressWindow()
        progress.show()
        progress.set_status("Extracting metadata…")
        ...do work...
        progress.set_status("Building Resolve project…")
        ...do more work...
        progress.close()
    """

    def __init__(self, title: str = "Chad's DaVinci Script — Working…") -> None:
        win_w, win_h = 480, 150
        style = NSWindowStyleMaskTitled

        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, win_w, win_h),
            style,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_(title)
        self.window.center()
        self.window.setLevel_(_NS_FLOATING_WINDOW_LEVEL)
        # User can't close it from the title bar — only the script can.
        try:
            self.window.standardWindowButton_(0).setHidden_(True)  # close
            self.window.standardWindowButton_(1).setHidden_(True)  # minimize
            self.window.standardWindowButton_(2).setHidden_(True)  # zoom
        except Exception:
            pass

        content = self.window.contentView()

        # Spinner
        self.spinner = NSProgressIndicator.alloc().initWithFrame_(
            NSMakeRect(24, 70, 32, 32)
        )
        self.spinner.setStyle_(NSProgressIndicatorStyleSpinning)
        self.spinner.setIndeterminate_(True)
        self.spinner.setDisplayedWhenStopped_(True)
        content.addSubview_(self.spinner)

        # Status label (large)
        self.status = NSTextField.alloc().initWithFrame_(
            NSMakeRect(68, 72, win_w - 92, 28)
        )
        self.status.setBezeled_(False)
        self.status.setDrawsBackground_(False)
        self.status.setEditable_(False)
        self.status.setSelectable_(False)
        self.status.setStringValue_("Starting…")
        self.status.setFont_(NSFont.systemFontOfSize_(14))
        content.addSubview_(self.status)

        # Sub-status label (small, gray) — used for per-file progress detail
        self.sub_status = NSTextField.alloc().initWithFrame_(
            NSMakeRect(68, 50, win_w - 92, 18)
        )
        self.sub_status.setBezeled_(False)
        self.sub_status.setDrawsBackground_(False)
        self.sub_status.setEditable_(False)
        self.sub_status.setSelectable_(False)
        self.sub_status.setStringValue_("")
        self.sub_status.setFont_(NSFont.systemFontOfSize_(11))
        try:
            self.sub_status.setTextColor_(NSColor.secondaryLabelColor())
        except Exception:
            pass
        content.addSubview_(self.sub_status)

        # Help footer
        help_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(24, 14, win_w - 48, 24)
        )
        help_label.setBezeled_(False)
        help_label.setDrawsBackground_(False)
        help_label.setEditable_(False)
        help_label.setSelectable_(False)
        help_label.setStringValue_(
            "Please don't click in DaVinci Resolve until this completes."
        )
        help_label.setFont_(NSFont.systemFontOfSize_(11))
        try:
            help_label.setTextColor_(NSColor.secondaryLabelColor())
        except Exception:
            pass
        content.addSubview_(help_label)

        _RETAINED.append(self.window)

    # ---- Public API -----------------------------------------------------

    def show(self) -> None:
        self.window.makeKeyAndOrderFront_(None)
        try:
            NSApp.activateIgnoringOtherApps_(True)
        except Exception:
            pass
        self.spinner.startAnimation_(None)
        self.pump()

    def set_status(self, text: str, sub: str | None = None) -> None:
        """Update the main status line (and optionally the sub-status line)
        and pump the run loop so the window repaints immediately."""
        try:
            self.status.setStringValue_(text)
            if sub is not None:
                self.sub_status.setStringValue_(sub)
            self.window.displayIfNeeded()
            self.pump()
        except Exception:
            pass

    def set_sub_status(self, text: str) -> None:
        try:
            self.sub_status.setStringValue_(text)
            self.window.displayIfNeeded()
            self.pump()
        except Exception:
            pass

    def pump(self) -> None:
        """Run the Cocoa run loop briefly so the window animates and repaints
        during synchronous work in the calling code. Cheap to call repeatedly."""
        try:
            NSRunLoop.currentRunLoop().runMode_beforeDate_(
                NSDefaultRunLoopMode,
                NSDate.dateWithTimeIntervalSinceNow_(0.02),
            )
        except Exception:
            pass

    def close(self) -> None:
        try:
            self.spinner.stopAnimation_(None)
            self.window.orderOut_(None)
            self.window.close()
        except Exception:
            pass
        # Leave the object in _RETAINED until the process exits — no harm.
