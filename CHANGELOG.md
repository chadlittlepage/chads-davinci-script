# Changelog

All notable changes to Chad's DaVinci Script are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.12] — 2026-04-07

### Added
- **Floating progress window during the build pipeline.** After the
  user clicks OK, a small `NSFloatingWindowLevel` window appears
  with a spinning indicator + a status label that updates at every
  phase of the build:
    - "Reviewing your file assignments…"
    - "Extracting metadata from media files…" (with sub-status
      showing the file count)
    - "Saving metadata reports…"
    - "Exporting EDL marker file…"
    - "Connecting to DaVinci Resolve…"
    - "Configuring Resolve project settings…"
    - "Building Resolve project…" (with sub-status "Creating bins,
      importing media, building timeline")
    - "Done!"

  The window has its title-bar buttons hidden so the user can't
  accidentally close it mid-build, and a footer line that says
  "Please don't click in DaVinci Resolve until this completes." It's
  positioned above all other windows including Resolve.

  Implementation: new `src/chads_davinci/progress_window.py` module
  with a `ProgressWindow` class. Each `set_status()` call pumps the
  Cocoa run loop briefly via
  `NSRunLoop.runMode_beforeDate_(NSDefaultRunLoopMode, ...)`
  so the window actually repaints during synchronous Python work.

- **`build_main` → `build_worker` subprocess now uses Popen + polling
  instead of `subprocess.run`.** The blocking `subprocess.run` call
  would freeze the main thread for the entire build (~30 s to several
  minutes), preventing the progress spinner from animating. The new
  implementation calls `Popen`, then polls `proc.poll()` in a loop
  while pumping the run loop every 50 ms via `progress.pump()`. The
  spinner stays alive and the status label stays responsive throughout.

## [0.2.11] — 2026-04-07

### Fixed (the v0.2.1 UTF-8 bug, second movement)

py2app bundles ship with no `LANG`/`LC_ALL` set, so the bundled
Python defaults to **ASCII** for `subprocess.run(..., text=True)`.
The moment any subprocess writes a non-ASCII byte (an em-dash in an
osascript error, a unicode quote in a mediainfo tag, anything in
`UTF-8`) Python crashes inside `_translate_newlines` with
`UnicodeDecodeError: 'ascii' codec can't decode byte 0xe2 in position 9`.

This is the same root cause as the v0.2.1 file-I/O fix, just on the
other side of the encoding wall (subprocess pipes instead of file
writes). v0.2.6's `sys.excepthook` caught the traceback in
`console.log` so we could find this in seconds instead of guessing.

Three-layer fix:

1. **`build_main.py` startup** sets `LANG=en_US.UTF-8`,
   `LC_ALL=en_US.UTF-8`, and `PYTHONIOENCODING=utf-8` on the process
   environment as the very first thing in `main()`. This makes
   the bundled interpreter's default subprocess decoding UTF-8 even
   though py2app inherited an empty environment. Single point of
   defense for all subprocess calls in the parent process.

2. **Every `subprocess.run(..., text=True)`** in the codebase now
   also explicitly passes `encoding="utf-8", errors="replace"` so
   it can never fall back to the platform default. Patched in:
   - `ui_automation._run_applescript` (the actual crash site)
   - `metadata._run_cmd` (mediainfo + ffprobe)
   - `diagnostics.log_tool_version`
   - `diagnostics.capture_app_screenshot` (both window and full-screen)
   - `diagnostics._bundled_tool_summary`
   - `build_main.subprocess.run` for build_worker

3. **`build_main` → `build_worker` subprocess** is now spawned with
   an explicit `env={**os.environ, "PYTHONIOENCODING": "utf-8",
   "LANG": "en_US.UTF-8"}` so the worker subprocess inherits a
   UTF-8 locale even if the parent's startup env-setting raced
   with anything else.

Defense in depth: any one of those three layers would be enough to
fix the bug. All three together mean no subprocess in the codebase
can ever hit the ASCII trap again.

## [0.2.10] — 2026-04-07

### Fixed (root cause)
- **AppleScript fallback for setting the playback frame rate left the
  Project Settings modal dialog open, which blocked every subsequent
  Resolve API call in the build_worker subprocess.** The exact failure
  chain on macOS 15.7.3:

  1. Parent calls `ctx.project.SetSetting("timelinePlaybackFrameRate", "23.976")`,
     which returns falsy on this Resolve version.
  2. Falls back to the UI-automation AppleScript.
  3. AppleScript opens the Project Settings dialog and tries to set
     the playback rate field to "23.976" — but the field is **already**
     "23.976", so Resolve sees no change and leaves the **Save button
     disabled**.
  4. AppleScript blindly clicks "Save" anyway → no-op, **dialog stays
     open**.
  5. build_worker subprocess starts → calls `MediaPool.ImportMedia` →
     **silently returns empty for every file** because Resolve has a
     modal dialog blocking API calls.
  6. Every import "fails", `create_quad_timeline` aborts with
     "Failed to create timeline", and no markers are generated.

  Two-layer fix:

  **Layer 1 — `build_main.py`**: read the current playback frame rate
  via `GetSetting()` BEFORE deciding whether to call the AppleScript.
  If the value already matches what we want, skip the AppleScript
  entirely. The dialog never opens; nothing to block. Then re-verify
  via `GetSetting()` after `SetSetting()` and only fall back to the
  AppleScript if Resolve's actual stored value still doesn't match.

  **Layer 2 — `ui_automation.py`**: even if the AppleScript does run,
  it now reads the enabled state of the Save button. If Save is
  enabled (Resolve detected a change), click it. If Save is disabled
  (no change to save), click Cancel instead. **Either way, the dialog
  ALWAYS closes** before the script returns. Belt-and-suspenders
  defensive `try`/`on error`/`Cancel` so the dialog can never be left
  open even if the button-state read itself fails.

### Fixed (defensive)
- **`MediaPool.ImportMedia` retries via lower-level Resolve APIs.**
  Even with the dialog issue fixed, `ImportMedia([path])` is known to
  silently fail on filenames containing `<digits>-<digits>` patterns
  (Resolve auto-detects them as image sequences). Add a
  `_import_one_file()` helper that tries three API paths in order:
  1. `MediaPool.ImportMedia([path])` — primary
  2. `MediaStorage.AddItemListToMediaPool(path)` — path-based, no
     sequence detection
  3. `MediaPool.ImportMedia([{"FilePath": path}])` — dict form, forces
     single-file mode

  Each fallback is logged so a future tester report tells us in
  `console.log` exactly which API path the file came in through.
  `import_media_files` also now logs file size and explicit
  file-not-found cases.

## [0.2.9] — 2026-04-07

### Code-path integrity hardening for file paths

The single most important change in this release: every step of the
drag-drop / Browse / paste / preset-load pipeline now stores the file
path string **byte-for-byte verbatim** with zero "helpful" mutation.
Plus length logging at every transit point so any future mutation is
provable from a single console.log.

#### Removed silent string-eating
- `_set_file()` previously stripped `{`, `}`, `"`, and `'` from the
  start AND end of every assigned path via
  `.strip().strip("{}").strip('"').strip("'")`. This was added to
  defend against pasted shell-quoted paths but would silently eat
  characters from any legitimate filename like `{notes}.mov` or
  `'commentary'.mov`. **Removed.** The only remaining transformation
  is a single leading/trailing whitespace strip, and that strip is
  logged whenever it actually changes anything.
- `pathFieldChanged_`, `okClicked_`, and `metadataOnlyClicked_` no
  longer pre-strip the field's `stringValue()` before passing to
  `_set_file`. `_set_file` is now the sole point of any string
  handling.

#### Provable roundtrip integrity
- `DropTextField.performDragOperation_` now stores the extracted path
  on the field via `setStringValue_`, immediately reads it back via
  `stringValue()`, and asserts they are equal. If NSTextField ever
  mutates a value silently (it shouldn't, but now we can prove it),
  the mismatch is logged in red to console.log with both the wrote
  and read values for diff.

#### Length logging at every transit point
- `_file_path_from_pasteboard`: logs `len=N` for every successful
  extraction.
- `performDragOperation_`: logs the roundtrip pass/fail and length.
- `pathFieldChanged_`: logs the byte length received from the field.
- `_set_file`: logs the raw length, the post-strip length (if
  anything was stripped), and the final stored path.

A future tester report can be diagnosed by reading the lengths in
console.log — if they're equal at every step, the path is
demonstrably intact. If any step shows a different length, we know
exactly which one is the culprit.

### Added (UX layer — independent of the integrity hardening above)
- **Tooltip on every drop field** — overrides `setStringValue_` so
  every assignment (drag, paste, Browse, preset load, settings
  restore, extras) automatically updates the tooltip with the full
  path. Hover the field for 1 second to see the COMPLETE path
  regardless of how long it is. There is no code path that can set
  a path without setting the tooltip too.
- **Truncate-at-head display** (from v0.2.8) — long paths now render
  as `…filename.mov` so the most informative part of the path (the
  filename) is always visible.
- **Wider picker window + wider path field** — picker is now 980 px
  wide (was 780) and the path field is 580 px wide (was 380). About
  80 characters of path now fit visually before truncation kicks in,
  vs the previous ~50.

## [0.2.8] — 2026-04-07

### Fixed
- **Path field appears truncated to "/Volumes/foo/" in the picker UI.**
  Pure visual bug — the v0.2.4 drag-and-drop fix already extracts the
  full POSIX path correctly (verified by the diagnostic logs in v0.2.5+),
  but NSTextField defaults to displaying only the LEADING characters
  that fit when text is set programmatically, so a long path stored in
  the field looked truncated to its volume root in the UI even though
  the full path was stored and would have been used by the build.

  Fix: every `DropTextField` now sets its cell line-break mode to
  `NSLineBreakByTruncatingHead`, which renders long paths as
  `…filename.mov` — showing the most informative part (the filename)
  instead of the volume root. The full path is still stored and
  retrievable via `stringValue()` exactly as before.

  This was the cause of multiple "drag and drop failed" reports today
  that were actually successful drops with confusing UI display.

## [0.2.7] — 2026-04-07

### Fixed
- **Metadata comparison table truncated to 80 columns in console.log.**
  The Rich `Console` in `metadata.py` was using its default width (80
  chars) when stdout was tee'd to a file (no TTY). With 7 metadata
  columns squeezed into 80 chars, every property value got cut off
  after ~10 characters, making the table visually useless in exported
  log files. Fix: construct the module-level Console with
  `width=240, force_terminal=False` so the table renders at full
  width regardless of where stdout is going.

## [0.2.6] — 2026-04-07

### Added
- **Session-start system probe.** Every launch writes a one-time block
  to console.log with macOS version, architecture, Python version,
  PyObjC version, locale, app bundle path, screen info, and bundled
  binary paths/sizes/architectures. Future tester reports can be
  diagnosed without asking the user "what version of macOS are you
  on" — it's right at the top of the log.
- **Resolve API probe.** When the app connects to DaVinci Resolve,
  it logs the Resolve product, version string, and database count.
- **Bundled tool version logging.** First time MediaInfo or ffprobe
  is invoked in a session, the tool's version line is logged to
  console.log so we know it's actually running and not quarantined.
- **Global unhandled-exception hook.** Any Python exception that
  isn't caught now writes a full traceback to console.log via the
  rich console. Previously these would only surface as the bare
  py2app fatal-error dialog with no context.
- **Screenshot capture on Export Console Log.** When the user picks
  Help → Export Console Log…, the app now also captures a PNG
  screenshot of its main window (via `screencapture -l <window-id>`)
  and saves it next to the .log file with a matching name. The
  screenshot is taken BEFORE the save panel opens so the panel
  doesn't appear in the captured image. The export-success dialog
  lists both files and asks the user to email both to support.

### Internal
- New `src/chads_davinci/diagnostics.py` module holding the system
  probe, exception hook, Resolve probe, tool version logger, and
  screenshot helper. Added to py2app includes list.

## [0.2.5] — 2026-04-07

### Added
- **Verbose drag-and-drop diagnostics in console.log.** Every drag enter
  and every drop now logs:
  1. The full list of pasteboard types Finder sent
  2. Whether the drop target accepted the drag
  3. The pasteboardItems count (when method 2 is reached)
  4. The raw `public.file-url` string per item
  5. Which extraction method (`readObjectsForClasses` /
     `pasteboardItems` / `NSFilenamesPboardType`) successfully produced
     a path, and what that path was
  6. The full pasteboard type list on total failure

  This means future tester reports about drag-drop issues can be
  diagnosed by reading `console.log` once instead of guessing — we'll
  see exactly what Finder sent and which extraction path took it.

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

[Unreleased]: https://github.com/chadlittlepage/chads-davinci-script/compare/v0.2.12...HEAD
[0.2.12]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.12
[0.2.11]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.11
[0.2.10]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.10
[0.2.9]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.9
[0.2.8]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.8
[0.2.7]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.7
[0.2.6]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.6
[0.2.5]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.5
[0.2.4]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.4
[0.2.3]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.3
[0.2.2]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.2
[0.2.1]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.1
[0.2.0]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.0
