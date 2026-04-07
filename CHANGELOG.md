# Changelog

All notable changes to Chad's DaVinci Script are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/chadlittlepage/chads-davinci-script/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.1
[0.2.0]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.0
