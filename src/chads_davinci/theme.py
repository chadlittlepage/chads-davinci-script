"""Shared color theme — matches VideohubController's dark palette.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from AppKit import NSColor
from Quartz import CGColorCreateGenericRGB

# ---- RGB tuples (for CGColor / layer backgrounds) ----
BG_DARK_RGB = (0.12, 0.12, 0.12)
BG_PANEL_RGB = (0.17, 0.17, 0.17)
HEADER_BG_RGB = (0.06, 0.06, 0.06)
INACTIVE_RGB = (0.22, 0.22, 0.22)
FIELD_BG_RGB = (0.14, 0.14, 0.14)

# ---- NSColor objects (for text, controls, backgrounds) ----
BG_DARK = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.12, 0.12, 0.12, 1.0)
BG_PANEL = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.17, 0.17, 0.17, 1.0)
FIELD_BG = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.14, 0.14, 0.14, 1.0)
TEXT_WHITE = NSColor.whiteColor()
TEXT_DIM = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.60, 0.60, 0.58, 1.0)
GREEN = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.0, 0.78, 0.33, 1.0)
RED = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.91, 0.27, 0.38, 1.0)

# ---- CGColor objects (for layer-backed views) ----
BG_DARK_CG = CGColorCreateGenericRGB(*BG_DARK_RGB, 1.0)
BG_PANEL_CG = CGColorCreateGenericRGB(*BG_PANEL_RGB, 1.0)
HEADER_BG_CG = CGColorCreateGenericRGB(*HEADER_BG_RGB, 1.0)
FIELD_BG_CG = CGColorCreateGenericRGB(*FIELD_BG_RGB, 1.0)
SEPARATOR_CG = CGColorCreateGenericRGB(0.30, 0.30, 0.28, 1.0)


def apply_dark_appearance(window) -> None:
    """Apply the dark appearance to an NSWindow / NSPanel / alert window.

    Used by NSAlert and any standalone dialog so they match the app theme.
    Safe to call on anything that has a setAppearance_ method; failures
    are silently ignored."""
    try:
        from AppKit import NSAppearance
        dark = NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua")
        if dark is not None and window is not None:
            window.setAppearance_(dark)
    except Exception:
        pass
