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
    NSBackingStoreBuffered,
    NSFont,
    NSMakeRect,
    NSPanel,
    NSProgressIndicator,
    NSProgressIndicatorStyleSpinning,
    NSTextField,
    NSWindowStyleMaskNonactivatingPanel,
    NSWindowStyleMaskTitled,
)
from Foundation import NSDate, NSDefaultRunLoopMode, NSRunLoop
from chads_davinci.theme import BG_DARK, TEXT_DIM, TEXT_WHITE

# Module-level retention so the window object isn't GC'd while it's visible.
_RETAINED: list = []

# NSWindow.level constants — kept here so we don't pull in extra symbols.
# DaVinci Resolve is a Qt application; its modal Project Settings dialog
# bypasses AppKit's normal level hierarchy and ends up well above
# NSPopUpMenuWindowLevel (101). We need to go higher than Qt's modal
# levels — NSScreenSaverWindowLevel (1000) is the highest user-accessible
# level on macOS short of system shielding. Apple's own software-update
# progress windows use this level for the same reason.
_NS_SCREEN_SAVER_WINDOW_LEVEL = 1000

# NSWindowCollectionBehavior bits we need:
#   1 << 0 = canJoinAllSpaces  — visible on every Space
#   1 << 4 = stationary        — doesn't slide away on Space switch
#   1 << 8 = fullScreenAuxiliary — visible above other apps' full-screen windows
_COLLECTION_CAN_JOIN_ALL_SPACES = 1 << 0
_COLLECTION_STATIONARY = 1 << 4
_COLLECTION_FULL_SCREEN_AUX = 1 << 8


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
        # NSPanel + NonactivatingPanel = doesn't steal focus when shown,
        # which means clicking it doesn't pull our app to the front and
        # the panel can stay visible above whichever app IS in front.
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskNonactivatingPanel

        self.window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, win_w, win_h),
            style,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_(title)
        self.window.center()

        # ----- "Stay above EVERYTHING" configuration -----
        # 1. NSScreenSaverWindowLevel (1000) — required to stay above
        #    DaVinci Resolve's Qt modal dialogs, which use a custom
        #    window-server level that bypasses AppKit's normal hierarchy.
        self.window.setLevel_(_NS_SCREEN_SAVER_WINDOW_LEVEL)
        # 2. Mark as a floating panel — keeps it above normal windows.
        try:
            self.window.setFloatingPanel_(True)
        except Exception:
            pass
        # 3. Don't steal focus when shown.
        try:
            self.window.setBecomesKeyOnlyIfNeeded_(True)
        except Exception:
            pass
        # 4. Stay visible above modal sheets/panels from other apps.
        try:
            self.window.setWorksWhenModal_(True)
        except Exception:
            pass
        # 5. Don't disappear when our app loses focus to Resolve.
        try:
            self.window.setHidesOnDeactivate_(False)
        except Exception:
            pass
        # 6. Visible on every Space + above other apps' full-screen windows.
        try:
            self.window.setCollectionBehavior_(
                _COLLECTION_CAN_JOIN_ALL_SPACES
                | _COLLECTION_STATIONARY
                | _COLLECTION_FULL_SCREEN_AUX
            )
        except Exception:
            pass

        # User can't close it from the title bar — only the script can.
        try:
            self.window.standardWindowButton_(0).setHidden_(True)  # close
            self.window.standardWindowButton_(1).setHidden_(True)  # minimize
            self.window.standardWindowButton_(2).setHidden_(True)  # zoom
        except Exception:
            pass

        content = self.window.contentView()
        self.window.setBackgroundColor_(BG_DARK)
        from AppKit import NSAppearance
        dark_appearance = NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua")
        if dark_appearance:
            self.window.setAppearance_(dark_appearance)

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
        self.status.setTextColor_(TEXT_WHITE)
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
            self.sub_status.setTextColor_(TEXT_DIM)
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
            help_label.setTextColor_(TEXT_DIM)
        except Exception:
            pass
        content.addSubview_(help_label)

        _RETAINED.append(self.window)

    # ---- Public API -----------------------------------------------------

    def show(self) -> None:
        # orderFrontRegardless_ shows the panel above ALL windows from all
        # apps (subject to the panel's window level) without making our app
        # active. This is what we want — the user is presumably in Resolve
        # and we want to show progress on top WITHOUT pulling them out of
        # Resolve and stealing keyboard focus.
        try:
            self.window.orderFrontRegardless()
        except Exception:
            try:
                self.window.makeKeyAndOrderFront_(None)
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
        """Hide and destroy the panel. Pumps the run loop several times
        afterward to make sure the WindowServer actually removes the
        window from the screen BEFORE the caller does anything else
        (e.g. shows a follow-up dialog). Without the pumps the panel
        can stay visually present even after orderOut_ if the next
        thing the caller does is a synchronous block like
        subprocess.run on osascript."""
        try:
            self.spinner.stopAnimation_(None)
        except Exception:
            pass
        try:
            self.window.orderOut_(None)
        except Exception:
            pass
        # Aggressively pump so orderOut_ actually takes visual effect.
        try:
            for _ in range(8):
                NSRunLoop.currentRunLoop().runMode_beforeDate_(
                    NSDefaultRunLoopMode,
                    NSDate.dateWithTimeIntervalSinceNow_(0.03),
                )
        except Exception:
            pass
        try:
            self.window.close()
        except Exception:
            pass
        # Final pump to make sure the close took effect too.
        try:
            for _ in range(4):
                NSRunLoop.currentRunLoop().runMode_beforeDate_(
                    NSDefaultRunLoopMode,
                    NSDate.dateWithTimeIntervalSinceNow_(0.03),
                )
        except Exception:
            pass
        # Leave the object in _RETAINED until the process exits — no harm.
