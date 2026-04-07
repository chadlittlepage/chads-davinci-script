# Changelog

All notable changes to Chad's DaVinci Script are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.4] — 2026-04-07

### Fixed
- **Drag-and-drop returns truncated path on macOS 15.** A tester reported
  that dropping a video file onto a picker row populated only the volume
  mount root (e.g. `/Volumes/media6/`) instead of the full file path.
  Root cause: the v0.2.3 fix used `NSURL.URLWithString:` to parse the
  `public.file-url` pasteboard type, but on macOS 15 Finder packs the
  URL data in a way that `URLWithString:` parses incorrectly — it
  returns the volume root URL instead of the file URL.

  Fix: switch to the canonical `NSPasteboard.readObjectsForClasses:options:`
  API with `[NSURL]`, which returns parsed NSURL objects directly and
  avoids string-based URL parsing entirely. Falls back to per-item
  iteration via `pasteboardItems` and finally to legacy
  `NSFilenamesPboardType` if both modern paths fail.

### Added
- Diagnostic logging in `_file_path_from_pasteboard`. If all three
  extraction methods fail, the picker now logs the available pasteboard
  types so a future tester's console.log will tell us exactly what
  Finder sent.

## [0.2.3] — 2026-04-07

### Fixed
- **macOS 15 (Sequoia) drag-and-drop freeze.** Apple has been
  deprecating `NSFilenamesPboardType` and on macOS 15 Finder no
  longer reliably populates it for file drags — it sends only the
  modern `public.file-url` UTI. Our drop handler was registered for
  the legacy type only, so the dragging session never resolved and
  the picker froze (UI completely unresponsive) the first time a
  user tried to drag from Finder. Fix: register for BOTH the legacy
  `NSFilenamesPboardType` AND `public.file-url`, and extract the
  file path from whichever the system actually populates.

### Added
- **First-launch welcome dialog.** A native NSAlert appears the very
  first time the app runs (gated on a marker file in
  `~/Library/Application Support/Chads DaVinci Script/.first_launch_seen`)
  warning the user about:
    1. The macOS Apple Events permission prompt that will appear
       on the first build (and how to respond to it)
    2. The need to launch DaVinci Resolve before clicking OK
    3. How drag-and-drop works (drag onto a path field; outline
       turns blue when ready)
    4. How auto-saved settings + Reset Defaults work
  Dismissed once per machine; never shown again on subsequent runs.
- Success / failure NSAlerts now explicitly call
  `activateIgnoringOtherApps_` so they come to the foreground
  instead of hiding behind Resolve or Terminal.

## [0.2.2] — 2026-04-07

### Added
- **Build complete / Metadata Export complete dialogs.** After the build
  subprocess returns, the parent Cocoa app now shows a native NSAlert
  with the project name, folder, and timeline name (or, in metadata-only
  mode, the export folder path) before exiting. Previously the app would
  silently exit after the picker closed, which felt to the user like
  the app "just quit" mid-task.
- **Build failed dialog.** Same idea on the error path: a critical-style
  NSAlert pointing the user at Help → Export Console Log… for details.

### Fixed
- **Quiet the AppleScript "not allowed assistive access" warning.** The
  UI-automation fallback for setting the *playback* monitor frame rate
  needs the macOS Accessibility permission, which is independent of the
  Apple Events entitlement. When that permission isn't granted (the most
  common case), the build still works fine because the timeline frame
  rate has already been set via the Resolve API and the playback
  monitor inherits it. The error log is now suppressed in this specific
  case so the console isn't spammed on a successful build.

## [0.2.1] — 2026-04-07

### Fixed
- **Crash on first real run**: text/CSV/JSON/HTML report writers were
  using `Path.write_text()` without `encoding="utf-8"`, which crashed on
  the very first em-dash (`—`) in a metadata table. Now every file I/O
  in the codebase explicitly uses UTF-8.
- Defensive UTF-8 + `ensure_ascii=False` on all settings/preset/bin
  JSON reads and writes, so unicode characters in track names, preset
  names, and bin labels round-trip safely.

## [0.2.0] — 2026-04-07

First public-facing notarized release.

### Added
- Native PyObjC + Cocoa file picker with drag-and-drop, persistent
  settings, and named presets (save / recall / delete).
- Dynamic "+ Add Video Track" rows. Extras insert above the fixed
  REEL SOURCE row in the picker and as the topmost video tracks in
  the resulting Resolve timeline.
- Editable bin tree with persistent storage and "Reset Defaults".
- Bin Editor side window with NSOutlineView.
- Metadata extraction via bundled MediaInfo + ffprobe.
- Multi-format reports: Text, CSV, JSON, HTML, "All formats".
- Resolve markers: "Add to Timeline", "Export as EDL file", or both.
- Metadata-only export mode (skip the full Resolve build, write
  reports + EDL into a folder you choose).
- Source resolution presets (HD → 4K timeline; UHD → 8K timeline) with
  automatic 2× quad-view layout.
- Timeline + Output Color Space dropdowns (25 Resolve color spaces).
- 12-bit / 10-bit / 8-bit SDI bit depth fallback chain.
- Comprehensive in-app manual (Help → Chad's DaVinci Script Help)
  covering every feature and option.
- Native macOS menu bar with File → Export/Import Settings, Help →
  Manual + Export Console Log.
- Sandbox-friendly storage in
  `~/Library/Application Support/Chads DaVinci Script/` with one-shot
  migration from the legacy `~/.chads-davinci/` location.

### Build / distribution
- py2app .app bundle, deep-signed with hardened runtime + Apple
  Developer ID.
- Notarized by Apple's notarytool service and stapled.
- DMG built with `dmgbuild` for full control over icon size, layout,
  and background image.
- Bundled `mediainfo` (universal) and `ffprobe` (arm64) hosted as a
  separate `build-deps-v1` GitHub Release for CI consumption.
- One-command local build via `./build_and_sign.sh`.
- One-tag CI release via `git tag v* && git push origin v*`. The
  `release.yml` workflow imports the cert from secrets, runs the full
  notarization pipeline on a macOS-14 runner, and publishes the DMG
  to GitHub Releases automatically (~4 minutes end-to-end).

### Fixed
- Silenced PyObjC bridge warning on `NSColor.CGColor()` calls by
  switching to typed `Quartz.CGColorCreateGenericRGB`.
- Removed dead `ripple_offset` and unused `project = ctx.project`
  variables in `resolve_connection.py`.
- Removed all "Dolby" branding remnants from default project name,
  default timeline name, and module/path names.
- `add_extra_tracks` now captures track count before AND after
  `AddTrack` so the new track index is unambiguous.
- Loop variables no longer shadow the imported `field` from
  `dataclasses` in `file_picker.py`.

[Unreleased]: https://github.com/chadlittlepage/chads-davinci-script/compare/v0.2.4...HEAD
[0.2.4]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.4
[0.2.3]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.3
[0.2.2]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.2
[0.2.1]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.1
[0.2.0]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.0
