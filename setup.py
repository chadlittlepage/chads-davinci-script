"""py2app setup script for building a standalone macOS .app bundle.

Build with:
    pip3 install py2app
    python3 setup.py py2app

Output: dist/Chad's DaVinci Script.app

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from setuptools import setup

APP_NAME = "Chad's DaVinci Script"
APP_VERSION = "0.2.18"

# Bundle ID — used for code signing, notarization, and AppleScript permissions
BUNDLE_ID = "com.chadlittlepage.chadsdavinciscript"

# Entry point script — wraps build_main.main()
APP = ["app_entry.py"]

DATA_FILES = [
    ("assets", ["assets/about_background.jpg"]),
    ("bin", ["bin/mediainfo", "bin/ffprobe"]),
]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "assets/AppIcon.icns",
    "plist": {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleVersion": APP_VERSION,
        "CFBundleShortVersionString": APP_VERSION,
        "NSHumanReadableCopyright": "© 2026 Chad Littlepage",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
        # Required so the bundle has Accessibility access for AppleScript UI automation
        "NSAppleEventsUsageDescription": (
            "Chad's DaVinci Script controls DaVinci Resolve via menu commands "
            "to set the playback frame rate."
        ),
    },
    "packages": [
        "chads_davinci",
        "rich",
    ],
    "includes": [
        "chads_davinci.about_window",
        "chads_davinci.bin_editor",
        "chads_davinci.build_main",
        "chads_davinci.build_worker",
        "chads_davinci.console_log",
        "chads_davinci.diagnostics",
        "chads_davinci.file_picker",
        "chads_davinci.manual_window",
        "chads_davinci.menu_bar",
        "chads_davinci.metadata",
        "chads_davinci.models",
        "chads_davinci.paths",
        "chads_davinci.progress_window",
        "chads_davinci.resolve_connection",
        "chads_davinci.settings_io",
        "chads_davinci.ui_automation",
        # Quartz needed for typed CGColor creation (avoids PyObjC bridge warnings)
        "Quartz",
    ],
    "excludes": [
        "tkinter",
    ],
}

setup(
    name=APP_NAME,
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    install_requires=[],  # py2app rejects install_requires; pyproject.toml deps must be empty here
)
