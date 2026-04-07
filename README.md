# Chad's DaVinci Script

A native macOS app that automates DaVinci Resolve project setup for
quad-view HDR metadata testing — file picking, bin structure, project
settings, color management, video monitoring, metadata extraction
(MediaInfo + ffprobe), reports (Text/CSV/JSON/HTML), and Resolve markers,
all from a single Cocoa form.

Built with PyObjC + py2app. Distributed as a signed, notarized DMG.

## Features

- Native Cocoa file picker with drag-and-drop, presets, and persistent
  settings (`~/Library/Application Support/Chads DaVinci Script/`)
- Resolve project automation: database/folder/project, bin tree, media
  import, 7-track quad timeline with auto-applied transforms
- User-defined extra video tracks added at the top of the timeline stack
- Metadata extraction via bundled MediaInfo + ffprobe
- Multi-format reports + Resolve EDL marker export
- Metadata-only export mode (no Resolve build)
- Editable bin structure with persistent storage and revert-to-default
- Named presets (save / recall / delete)
- Comprehensive in-app manual (Help → Chad's DaVinci Script Help)

See the in-app manual for the complete user-facing reference.

## Install (end users)

Download the latest signed/notarized `Chads DaVinci Script.dmg` from the
project's GitHub Releases page, drag the app to `/Applications`, and
launch. The first time you set the playback frame rate, macOS will ask
to allow the app to control DaVinci Resolve — click OK once.

## Build from source (developers)

### Prerequisites

- macOS 11+
- Python 3.11+
- DaVinci Resolve 20.x installed
- (For releases) An Apple Developer ID Application certificate in your
  login keychain and a notarytool keychain profile — see the comments
  at the top of `build_and_sign.sh`.

### Bundled binaries (one-time)

`mediainfo` and `ffprobe` are NOT checked into the repo. Drop static
arm64 builds into `bin/`:

```
bin/mediainfo
bin/ffprobe
```

See `bin/README.md` for download links and the exact command to
verify them.

### Run from source

```bash
PYTHONPATH=src python3 -m chads_davinci.build_main
```

### Build a signed, notarized DMG

```bash
./build_and_sign.sh
```

Output: `dist/Chads DaVinci Script.dmg`. The script handles
deep-signing, hardened-runtime entitlements, notarization submission,
ticket stapling, DMG creation, and DMG signing/notarization in one go.

## Project layout

```
.
├── app_entry.py            # py2app entry — wraps build_main.main()
├── setup.py                # py2app build config
├── pyproject.toml          # package metadata (no install_requires; py2app rejects)
├── entitlements.plist      # hardened runtime + automation entitlements
├── build_and_sign.sh       # one-shot release pipeline
├── assets/                 # icon, background image
├── bin/                    # bundled mediainfo + ffprobe (not in repo)
└── src/chads_davinci/
    ├── __init__.py
    ├── about_window.py
    ├── bin_editor.py       # native NSOutlineView bin editor
    ├── build_main.py       # parent process entry point
    ├── build_worker.py     # subprocess for clean Resolve API state
    ├── console_log.py      # tee stdout/stderr to ~/Library/Application Support/.../logs
    ├── file_picker.py      # main Cocoa picker window
    ├── manual_window.py    # in-app manual
    ├── menu_bar.py         # native menu bar
    ├── metadata.py         # MediaInfo + ffprobe wrappers + report writers
    ├── models.py           # TrackRole, BIN_STRUCTURE, transforms
    ├── paths.py            # sandbox-friendly app support paths
    ├── resolve_connection.py  # all DaVinci Resolve API calls
    ├── settings_io.py      # user settings + presets persistence
    └── ui_automation.py    # AppleScript playback frame rate fallback
```

## License

Proprietary — see [LICENSE](LICENSE). All rights reserved.

## Author

Chad Littlepage
<chad.littlepage@gmail.com>
