"""Native macOS menu bar with About / Help / Quit items.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import objc
from AppKit import (
    NSApp,
    NSMenu,
    NSMenuItem,
    NSObject,
)

# Module-level retention for menu and target objects
_RETAINED = []


class MenuTarget(NSObject):
    """Receives menu actions and dispatches to handlers."""

    def init(self):
        self = objc.super(MenuTarget, self).init()
        return self

    def showAbout_(self, sender):
        from chads_davinci.about_window import show_about_window
        show_about_window()

    def showHelp_(self, sender):
        from chads_davinci.manual_window import show_manual_window
        show_manual_window()

    def exportSettings_(self, sender):
        """Show save panel and export settings to JSON."""
        from AppKit import NSSavePanel
        from chads_davinci.settings_io import export_to_file

        panel = NSSavePanel.savePanel()
        panel.setNameFieldStringValue_("ChadsDaVinciScript_settings.json")
        panel.setMessage_("Export all settings to a JSON file")
        panel.setAllowedFileTypes_(["json"])

        if panel.runModal():
            url = panel.URL()
            if url is not None:
                target = str(url.path())
                try:
                    saved = export_to_file(target)
                    _show_dialog("Settings Exported", f"Saved to: {saved}")
                except Exception as e:
                    _show_dialog("Export Failed", str(e))

    def exportConsole_(self, sender):
        """Capture a screenshot, then show a save panel that saves BOTH
        the console log AND the screenshot side-by-side. The screenshot
        is taken BEFORE the save panel opens so the panel itself isn't
        in the captured image."""
        from datetime import datetime
        from pathlib import Path

        from AppKit import NSSavePanel
        from chads_davinci.console_log import get_log_path
        from chads_davinci.diagnostics import capture_app_screenshot

        log_path = get_log_path()
        if not log_path.exists():
            _show_dialog("No Log Available", "No console log file found yet.")
            return

        # Capture the screenshot to a temporary location BEFORE the save
        # panel opens (so the panel itself doesn't end up in the image).
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        import tempfile
        tmp_screenshot = Path(tempfile.gettempdir()) / f"cdv_screenshot_{timestamp}.png"
        screenshot_taken = capture_app_screenshot(tmp_screenshot)

        panel = NSSavePanel.savePanel()
        panel.setNameFieldStringValue_(f"ChadsDaVinciScript_console_{timestamp}.log")
        panel.setMessage_(
            "Save the console log file. A screenshot of the app will be "
            "saved next to it. Send both to support if there's a crash."
        )
        panel.setAllowedFileTypes_(["log", "txt"])

        if panel.runModal():
            url = panel.URL()
            if url is not None:
                target = Path(url.path())
                try:
                    import shutil
                    shutil.copy2(str(log_path), str(target))
                    saved_files = [str(target)]
                    # Move screenshot next to the log with a matching name
                    if screenshot_taken and screenshot_taken.exists():
                        screenshot_dest = target.with_suffix(".png")
                        shutil.move(str(screenshot_taken), str(screenshot_dest))
                        saved_files.append(str(screenshot_dest))
                    _show_dialog(
                        "Diagnostics Exported",
                        "Saved:\n" + "\n".join(saved_files)
                        + "\n\nEmail BOTH files to chad.littlepage@gmail.com",
                    )
                except Exception as e:
                    _show_dialog("Export Failed", str(e))
        # If the user cancelled, clean up the temp screenshot
        if screenshot_taken and screenshot_taken.exists():
            try:
                screenshot_taken.unlink()
            except Exception:
                pass

    def importSettings_(self, sender):
        """Show open panel and import settings from JSON."""
        from AppKit import NSOpenPanel
        from chads_davinci.settings_io import import_from_file

        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(False)
        panel.setMessage_("Choose a settings JSON file to import")
        panel.setAllowedFileTypes_(["json"])

        if panel.runModal():
            urls = panel.URLs()
            if urls and len(urls) > 0:
                source = str(urls[0].path())
                ok, msg = import_from_file(source)
                title = "Settings Imported" if ok else "Import Failed"
                if ok:
                    msg += "\nReopen the picker for changes to take effect."
                _show_dialog(title, msg)


def _show_dialog(title: str, message: str) -> None:
    """Show a simple macOS dialog."""
    import subprocess
    msg = message.replace('"', '\\"').replace('\n', '\\n')
    safe_title = title.replace('"', '\\"')
    subprocess.run([
        "osascript", "-e",
        f'display dialog "{msg}" with title "{safe_title}" buttons {{"OK"}}',
    ], capture_output=True)


def setup_menu_bar(app_name: str = "Chad's DaVinci Script") -> None:
    """Install the macOS menu bar with App / Help menus."""
    target = MenuTarget.alloc().init()
    _RETAINED.append(target)

    main_menu = NSMenu.alloc().init()

    # ---- App menu (first menu, named after the app) ----
    app_menu_item = NSMenuItem.alloc().init()
    main_menu.addItem_(app_menu_item)

    app_menu = NSMenu.alloc().init()
    app_menu_item.setSubmenu_(app_menu)

    # About
    about_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        f"About {app_name}", "showAbout:", ""
    )
    about_item.setTarget_(target)
    app_menu.addItem_(about_item)

    app_menu.addItem_(NSMenuItem.separatorItem())

    # Hide
    hide_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        f"Hide {app_name}", "hide:", "h"
    )
    app_menu.addItem_(hide_item)

    # Hide Others
    hide_others = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Hide Others", "hideOtherApplications:", "h"
    )
    hide_others.setKeyEquivalentModifierMask_(1 << 19 | 1 << 20)  # cmd+option
    app_menu.addItem_(hide_others)

    # Show All
    show_all = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Show All", "unhideAllApplications:", ""
    )
    app_menu.addItem_(show_all)

    app_menu.addItem_(NSMenuItem.separatorItem())

    # Quit
    quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        f"Quit {app_name}", "terminate:", "q"
    )
    app_menu.addItem_(quit_item)

    # ---- File menu ----
    file_menu_item = NSMenuItem.alloc().init()
    main_menu.addItem_(file_menu_item)

    file_menu = NSMenu.alloc().initWithTitle_("File")
    file_menu_item.setSubmenu_(file_menu)

    export_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Export Settings…", "exportSettings:", "e"
    )
    export_item.setKeyEquivalentModifierMask_((1 << 17) | (1 << 20))  # shift+cmd
    export_item.setTarget_(target)
    file_menu.addItem_(export_item)

    import_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Import Settings…", "importSettings:", "i"
    )
    import_item.setKeyEquivalentModifierMask_((1 << 17) | (1 << 20))  # shift+cmd
    import_item.setTarget_(target)
    file_menu.addItem_(import_item)

    # ---- Edit menu (provides cut/copy/paste for text fields) ----
    edit_menu_item = NSMenuItem.alloc().init()
    main_menu.addItem_(edit_menu_item)

    edit_menu = NSMenu.alloc().initWithTitle_("Edit")
    edit_menu_item.setSubmenu_(edit_menu)

    for title, sel, key in [
        ("Undo", "undo:", "z"),
        ("Redo", "redo:", "Z"),
    ]:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, sel, key)
        edit_menu.addItem_(item)

    edit_menu.addItem_(NSMenuItem.separatorItem())

    for title, sel, key in [
        ("Cut", "cut:", "x"),
        ("Copy", "copy:", "c"),
        ("Paste", "paste:", "v"),
        ("Select All", "selectAll:", "a"),
    ]:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, sel, key)
        edit_menu.addItem_(item)

    # ---- Help menu ----
    help_menu_item = NSMenuItem.alloc().init()
    main_menu.addItem_(help_menu_item)

    help_menu = NSMenu.alloc().initWithTitle_("Help")
    help_menu_item.setSubmenu_(help_menu)

    help_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        f"{app_name} Help", "showHelp:", "?"
    )
    help_item.setTarget_(target)
    help_menu.addItem_(help_item)

    help_menu.addItem_(NSMenuItem.separatorItem())

    console_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Export Console Log…", "exportConsole:", ""
    )
    console_item.setTarget_(target)
    help_menu.addItem_(console_item)

    NSApp.setMainMenu_(main_menu)
    _RETAINED.append(main_menu)
