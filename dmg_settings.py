"""dmgbuild settings for Chad's DaVinci Script.

Builds a styled DMG with a dark background and WHITE icon-label text
(label colour is written into the .DS_Store directly — AppleScript's
'text color' property was removed in modern Finder).

Build with:
    dmgbuild -s dmg_settings.py "Chad's DaVinci Script" "dist/Chads DaVinci Script.dmg"

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

import os.path

# ---- App being packaged ----------------------------------------------------
APP_BUNDLE = "dist/Chad's DaVinci Script.app"
APP_NAME = os.path.basename(APP_BUNDLE)

# ---- Volume / DMG ----------------------------------------------------------
volume_name = "Chads DaVinci Script"   # window title (no apostrophe avoids shell pain)
format = "UDZO"
filesystem = "HFS+"
size = None  # auto

# ---- Window appearance -----------------------------------------------------
window_rect = ((200, 120), (600, 400))
icon_size = 105
text_size = 13

# ---- Background image ------------------------------------------------------
background = "assets/dmg_background.jpg"  # 15% lighter so labels are readable

# ---- Files placed in the volume --------------------------------------------
files = [APP_BUNDLE]
symlinks = {"Applications": "/Applications"}

# Icon positions in the window (x, y from top-left of window content)
icon_locations = {
    APP_NAME: (150, 200),
    "Applications": (450, 200),
}

# ---- Default Finder view ---------------------------------------------------
default_view = "icon-view"
show_icon_preview = False
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False

# ---- WHITE label text ------------------------------------------------------
# dmgbuild writes this into the .DS_Store directly — actually works.
# RGB tuple (red, green, blue) in 0..1 range.
text_color = (1.0, 1.0, 1.0)

# Hide files we don't want shown in the volume window
hide_extension = [APP_NAME]
