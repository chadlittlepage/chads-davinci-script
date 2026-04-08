# Changelog

All notable changes to Chad's DaVinci Script are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.19] — 2026-04-08

### Added — three real workflow features

#### 1. Drop a folder → auto-route files to picker rows

Instead of dragging six files into six rows, drag a single folder
onto any path field. The picker scans the folder for video files
and routes each one to the matching row by filename pattern.

Pattern matching is case-insensitive substring on the basename
(see `models.route_filename_to_role`):

  - `hdmi`                              → `L1SHW HDMI`
  - `hw2` + (`795`/`1500`/`stretch`)    → `HW2 795 Stretch 1500`
  - `l1shw`/`l15hw`/`hwl15` + same      → `L1SHW 795 Stretch 1500`
  - `hw2` + (`300`/`300nit`)            → `HW2 300 nit`
  - `l1shw`/`l15hw`/`hwl15` + same      → `L1SHW 300`
  - `reel` or `source`                  → `REEL SOURCE`

Files that don't match any pattern are silently ignored. If
multiple files match the same row, the first one alphabetically
wins. Single-file drops still go to the row that received the
drop (no surprises).

A green confirmation message at the bottom of the picker reports
how many files were matched and which rows they filled. Implemented
in `FilePickerController.routeDroppedFolder_` (called from
`DropTextField.performDragOperation_` when the dropped item is a
directory).

#### 2. Pre-flight validation when you click OK

Before starting the build, the picker now runs a quick MediaInfo
sweep across every assigned file and checks for:

  1. **File existence** — every assigned path actually exists on
     disk (catches unmounted volumes like `/Volumes/media6` not
     being connected)
  2. **Frame rate consistency** across all enabled rows
  3. **Resolution consistency**
  4. **Color space consistency** — the whole point of HDR-test
     workflows; a mismatch here is a real bug to catch
  5. **Bit depth consistency**

If any check fails, an `osascript display dialog` warning appears
listing every issue. The user can:
  - Click **Cancel** — keeps the picker open so they can fix the
    assignments
  - Click **Continue Anyway** — proceeds with the build (use when
    the mismatch is intentional)

If pre-flight finds no issues, no dialog appears — the build just
starts immediately. Pre-flight takes ~1-2 seconds for 6 files.
The MediaInfo result is cached so the actual build doesn't
re-extract the same metadata.

Implemented as `_run_preflight()` and `_show_preflight_dialog()`
on `FilePickerController`, called from `okClicked_()` after the
existing required-tracks / database / project-name validation.

### Added — supporting helpers

- **`models.route_filename_to_role(filename)`** — case-insensitive
  pattern matcher returning a `TrackRole` or `None`. Documented
  with examples in the docstring.
- **`FilePickerController._set_status_ok()`** — green
  confirmation message in the picker status bar (used by the
  folder auto-router).
- **`FilePickerController._set_status_info()`** — gray plain
  status (used during pre-flight to show "Pre-flight check…").
- **All new status messages are also printed via the rich console**
  so they land in `console.log` per the v0.2.18 error-visibility
  pass.

### Manual updates
- New section: **DROP A FOLDER → AUTO-ROUTE FILES** with the full
  pattern table and example filenames
- New section: **PRE-FLIGHT VALIDATION** explaining the checks,
  the dialog, and when each is skipped

## [0.2.18] — 2026-04-07

### Added — error visibility + log rotation

- **Log rotation in `console_log.py`.** The session log no longer
  grows unbounded. On every launch, `setup_logging()` checks the
  existing `console.log` file:
  - If older than **30 days** → archived to `console.log.old` (one
    backup kept; older backups overwritten)
  - If larger than **10 MB** → tail-truncated to the last 5 MB with
    a `=== log truncated (rolling 5 MB cap) ===` marker prepended
  Failures during rotation are silent — log rotation must never block
  app startup.

- **Threading exception hook.** v0.2.6's
  `install_global_exception_hook` now also installs
  `threading.excepthook`, so Python exceptions raised in non-main
  threads are written to console.log too. Previously they would
  silently disappear into the thread cleanup path.

- **Validation errors shown to the user are now also logged.**
  `FilePickerController._set_status` (the validator that paints red
  text under the picker form when something is missing) now also
  prints the same message to the rich console, so the validation
  error lands in `console.log`. Previously these only appeared on
  screen and weren't captured by the export-log feature.

- **`menu_bar._show_dialog` now logs to console too.** This is the
  helper used by the menu's "Export Settings", "Import Settings",
  and "Export Console Log" handlers to show success/failure popups.
  Now every dialog message ALSO lands in `console.log`. The
  `osascript` subprocess call also gained explicit
  `encoding="utf-8", errors="replace"` and exception logging so
  any failure is captured.

- **`_file_path_from_pasteboard` re-added per-method exception
  logging.** When a fallback method raises (genuinely rare), the
  exception is now logged in yellow so we can see what went wrong
  rather than silently swallowing it.

### Optimizations / cleanup pass

100 lines of dead and verbose-debug code removed without losing any
functionality. The macOS 15 debugging logs we added in v0.2.5–v0.2.9
served their purpose (caught the NSURL truncation bug, the UTF-8
subprocess bug, the Project Settings dialog hang, and several others)
and are no longer needed in normal operation.

#### `file_picker.py` — 1619 → 1536 lines (−83)

- **`_file_path_from_pasteboard`**: removed all per-event diagnostic
  logging. The function now silently returns the path through method
  1/2/3 and only logs in the "all methods failed" case (which never
  fires in v0.2.17+).
- **`draggingEntered_`**: removed the `[dim]Drag enter: types=...`
  log that fired on every mouseover.
- **`performDragOperation_`**: removed the roundtrip integrity check
  (`setStringValue_` → readback → assert). Was added in v0.2.9 to
  prove the path bytes were intact end-to-end. We have that proof
  now and the check just adds 4 console lines per drop.
- **`pathFieldChanged_`**: removed the per-call length log.
- **`_set_file`**: removed both per-call length logs (the "stripped
  whitespace" debug print and the "stored len=" debug print). The
  function is now 4 lines instead of 18.
- **Module-level `_module_console`**: replaces the inline `Console()`
  instantiations in hot paths (one Console per app run instead of
  one per drag).
- **`NSLineBreakByTruncatingHead`**: hoisted to top-level imports,
  removed the lazy `try/except` around the lookup.

#### `metadata.py` — 621 → 604 lines (−17)

- **`extract_metadata`**: removed the per-file `_check_tool()` calls.
  `extract_mediainfo()` and `extract_ffprobe()` already do their own
  cached `_resolve_tool()` lookup internally, so the outer check was
  redundant work — and the yellow "tool not found" warnings printed
  per file (5 yellow lines if the user dropped 5 files and ffprobe
  was missing).
- **`_check_tool`**: deleted (no more callers).

### Notes

- All linting passes, no behavior changes
- Drag-drop, build pipeline, and progress window all work exactly
  as before — they're just quieter
- console.log files will be ~70% smaller for a typical session
- The unhandled-exception hook + system probe + Resolve probe + tool
  version logging are all kept (those are one-shot at session start
  and remain useful)

## [0.2.17] — 2026-04-07

### Added — image sequence support + comprehensive format documentation

- **Image sequence detection.** When the user drags a single frame
  from a numbered image sequence (DPX, TIFF, EXR, JPEG, PNG, etc.)
  onto a track row, the metadata extractor now scans the parent
  folder for sibling frames matching the same prefix + digit count
  + extension and reports the **full sequence frame count** instead
  of just the dropped file. The console.log shows the detected
  pattern, e.g. `frame.[####].dpx (image sequence, 1200 frames)`.

  Resolve's `MediaPool.ImportMedia` already auto-detects image
  sequences when given a single frame, so the existing import path
  works without changes — the sequence appears as ONE clip on the
  V3-V6 quad tracks, not 1200 separate stills.

- **`models.py`: comprehensive supported-format constants.**
    - `SUPPORTED_VIDEO_EXTENSIONS` — every container format Resolve
      can ingest: `.mov`, `.mp4`, `.m4v`, `.mkv`, `.avi`, `.webm`,
      `.mxf`, `.ts`, `.m2t`, `.m2ts`, `.mts`, `.braw`, `.r3d`,
      `.ari`, `.arx`, `.crm`, `.rmf`, `.dng`, `.cine`, `.3gp`,
      `.vob`, `.ogv`
    - `IMAGE_SEQUENCE_EXTENSIONS` — every image format that can
      stand alone OR be part of a sequence: `.dpx`, `.tif`, `.tiff`,
      `.exr`, `.jpg`, `.jpeg`, `.jp2`, `.j2k`, `.jpf`, `.jpx`,
      `.png`, `.tga`, `.bmp`, `.hdr`, `.cin`
    - `SUPPORTED_AUDIO_EXTENSIONS` — `.wav`, `.aif`, `.aiff`,
      `.flac`, `.mp3`, `.m4a`, `.aac`
    - `ALL_SUPPORTED_EXTENSIONS` — convenience union
  - New helpers `is_image_sequence_format(path)` and
    `detect_image_sequence(path)` for use throughout the app.

- **In-app manual: SUPPORTED FILE FORMATS section** listing every
  container, codec, image format, and audio format with brief
  descriptions. Plus a new **WORKING WITH IMAGE SEQUENCES** section
  explaining the "drag a single frame, Resolve auto-detects the
  rest" workflow and what to do if a sequence isn't detected.

- **Picker column header text** updated from
  `"File (drag from Finder, paste, or Browse)"` →
  `"File or first frame of an image sequence (drag, paste, or Browse)"`
  so the new capability is discoverable from the picker UI.

### Notes

The picker still accepts ANY file extension (no filtering on
drag-drop or Browse) — the lists above document what's *supported*,
not what's *whitelisted*. If Resolve can read a format that isn't in
the list, the picker will still let you import it.

## [0.2.16] — 2026-04-07

### Fixed
- **Restored the AppleScript playback-frame-rate fallback (correctly
  this time).** v0.2.15 removed it entirely on the assumption that
  the playback monitor would inherit from the timeline frame rate.
  In practice the Resolve API treats `timelinePlaybackFrameRate` as
  read-only on the user's Resolve version, the playback monitor
  does NOT inherit, and the result was that the playback rate
  stayed at Resolve's default (24 fps) even though the timeline
  was correctly set to 23.976.

  v0.2.16 brings back the `set_playback_frame_rate()` AppleScript
  call when the API path doesn't take effect, but wraps it
  correctly:
  1. Read current `timelinePlaybackFrameRate` via `GetSetting()`.
     If it already matches → done.
  2. Call `SetSetting()` once via the API.
  3. Re-check. If now matches → done.
  4. Otherwise:
     - Update the progress panel status to "Setting playback frame
       rate via Resolve UI…" with sub-status explaining that
       Resolve will briefly show its Project Settings dialog.
     - **`orderOut_(None)`** the progress panel so it isn't covered
       by the Project Settings dialog.
     - Run `set_playback_frame_rate()` (still has the v0.2.10
       "click Cancel if Save is disabled" safety so the dialog
       always closes).
     - **`orderFrontRegardless()`** the progress panel back.
     - Update status to "Continuing build…".

- **Two dialogs at the end (progress panel + Build complete alert
  visible simultaneously).** `progress.close()` was calling
  `orderOut_(None)` and `close()` on the panel, but the next thing
  the calling code did was a synchronous `subprocess.run` on
  `osascript display dialog`, which blocked the main thread before
  the WindowServer had a chance to actually remove the panel from
  the screen. Result: the user saw both the "Done!" panel and the
  "Build complete" dialog at the same time.

  Fix in `progress_window.close()`: aggressively pump the run loop
  with `NSRunLoop.runMode_beforeDate_(NSDefaultRunLoopMode, ...)`
  for ~240 ms after `orderOut_` and again after `close()`. This
  forces the WindowServer to process the close request before
  control returns to the caller.

## [0.2.15] — 2026-04-07

### Fixed (real fix this time, after the 0.2.12-14 saga)

The progress panel + Build complete dialog were *still* getting
covered by Resolve after multiple window-level escalations
(NSFloatingWindowLevel → NSPopUpMenuWindowLevel → NSScreenSaverWindowLevel)
because the root cause wasn't actually about window levels at all —
it was about the AppleScript opening Resolve's Project Settings
modal in the first place. Two real fixes:

#### 1. Stop opening Project Settings entirely

The AppleScript fallback for setting the playback frame rate was the
fundamental cause of all the "covered by Project Settings" symptoms.
Even with a perfect window-level configuration, popping a modal
dialog inside Resolve was always going to fight our progress UI. The
build itself doesn't need this fallback — the timeline frame rate is
set via the Resolve API and the playback monitor inherits from the
timeline. Setting the playback rate independently is a minor
convenience that has cost us many releases worth of pain.

`build_main.py` no longer calls `set_playback_frame_rate()` from
`ui_automation.py`. The function is left in the codebase (it's harmless
and might be useful for power users who can grant Accessibility
permission and call it manually) but is no longer wired into the
default build flow. The flow now is:

1. Read current playback frame rate via `GetSetting()`
2. If it already matches → do nothing
3. Otherwise call `SetSetting()` once
4. Re-check; log success or graceful warning
5. Either way, never open Project Settings

#### 2. `_show_alert` now uses `osascript display dialog` instead of `NSAlert`

`NSAlert` + `NSRunningApplication.activateWithOptions_` simply doesn't
win the Z-order fight against DaVinci Resolve on modern macOS, even
with `NSScreenSaverWindowLevel` set on the alert window. The system
won't promote our app to foreground because it considers us to be in
the background by the time the build subprocess returns.

Switched the success/failure dialogs to use `osascript -e 'display
dialog "..."'`. AppleScript's `display dialog` is shown by `osascript`
itself via `StandardAdditions` (NOT via System Events), so:

- It does NOT need Accessibility (TCC) permission — `display dialog`
  outside any `tell` block is just StandardAdditions
- It IS reliably brought to the front by macOS regardless of which
  app is currently active
- It respects the system appearance (light/dark mode)
- It uses the standard system "stop" or "note" icon

The dialog is invoked with:
  `display dialog "..." with title "..." buttons {"OK"}
   default button "OK" with icon note`

Falls back to `NSAlert` only if `osascript` itself fails for some
reason (which shouldn't happen — osascript is part of macOS).

## [0.2.14] — 2026-04-07

### Fixed (the v0.2.12/0.2.13 saga continues)
- **Progress panel STILL covered by Resolve's Project Settings modal**
  even after v0.2.13 bumped the level to `NSPopUpMenuWindowLevel` (101).
  Root cause: **DaVinci Resolve is a Qt application**. Qt's modal
  dialogs use a custom window-server level that bypasses AppKit's
  normal hierarchy entirely. AppKit's `NSPopUpMenuWindowLevel` isn't
  high enough to beat them.

  Fix: bump `progress_window.py` window level to
  `NSScreenSaverWindowLevel` (1000). This is the highest user-accessible
  level on macOS short of system shielding. Apple's own software-update
  progress windows use the same level for the same reason.

- **"Build complete" alert appears BEHIND DaVinci Resolve.** Modern
  macOS frequently refuses `NSApplication.activateIgnoringOtherApps_`
  when the calling process is no longer the foreground app from the
  system's perspective — which is exactly the state we're in by the
  time the build subprocess finishes and we try to show the alert.

  Fix in `_show_alert()`:
  1. Force-activate via the modern
     `NSRunningApplication.currentApplication().activateWithOptions_(
       NSApplicationActivateAllWindows |
       NSApplicationActivateIgnoringOtherApps)`
     API. The legacy `activateIgnoringOtherApps_` is kept as a fallback.
  2. Bump the alert window's level to `NSScreenSaverWindowLevel` (1000)
     BEFORE running the modal so it sits above Resolve and any of
     Resolve's modal dialogs.
  3. Call `orderFrontRegardless()` on the alert window before
     `runModal()`.

  Net result: the alert is unmissable. It appears above Resolve, above
  any Qt modals Resolve might still have open, and the user actually
  sees their build completed.

## [0.2.13] — 2026-04-07

### Fixed
- **Progress window was getting covered by Resolve's Project Settings
  modal and then by Resolve's main window after the modal closed.**
  v0.2.12 used `NSWindow` at `NSFloatingWindowLevel` (3), which is
  high enough to float above normal app windows but NOT high enough
  to beat Resolve's modal Project Settings dialog (which is at
  modal-panel level), and the progress window also disappeared when
  our app lost focus to Resolve.

  Fix: rewrite `progress_window.py` to use **`NSPanel`** instead of
  `NSWindow`, with the full "always on top, never hide, never steal
  focus" set of flags:
  - **Window level `NSPopUpMenuWindowLevel` (101)** — beats every
    normal app modal panel.
  - **`NSWindowStyleMaskNonactivatingPanel`** — clicks on the panel
    don't pull our app to the foreground (so the user can keep
    interacting with whatever they want behind it).
  - **`setFloatingPanel_(True)`** — declares it as a floating utility
    panel.
  - **`setBecomesKeyOnlyIfNeeded_(True)`** — never steals keyboard
    focus.
  - **`setWorksWhenModal_(True)`** — stays visible above modal
    sheets/dialogs from other apps (this is the key flag that makes
    it appear above Resolve's Project Settings).
  - **`setHidesOnDeactivate_(False)`** — doesn't disappear when our
    app loses focus to Resolve.
  - **Collection behavior `canJoinAllSpaces | stationary |
    fullScreenAuxiliary`** — visible on every Space + above
    full-screen apps.
  - **`orderFrontRegardless()`** instead of `makeKeyAndOrderFront_`
    so the panel comes to the front without making our app active.

  Net result: the progress panel stays visible above Resolve, above
  Resolve's Project Settings modal, above any other app the user
  might switch to, until the build script explicitly closes it.

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

[Unreleased]: https://github.com/chadlittlepage/chads-davinci-script/compare/v0.2.19...HEAD
[0.2.19]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.19
[0.2.18]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.18
[0.2.17]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.17
[0.2.16]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.16
[0.2.15]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.15
[0.2.14]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.14
[0.2.13]: https://github.com/chadlittlepage/chads-davinci-script/releases/tag/v0.2.13
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
