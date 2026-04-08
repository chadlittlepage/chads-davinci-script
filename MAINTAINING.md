# Maintaining Chad's DaVinci Script

The single source of truth for "how do I do X to this project" — read or
search this file before going hunting through the codebase.

If you're new to the project (or coming back after a long break), read
the **TL;DR** below and the **Project layout** section, then jump to
whichever recipe you need.

---

## TL;DR

- **Source**: <https://github.com/chadlittlepage/chads-davinci-script> (private)
- **Public releases**: <https://github.com/chadlittlepage/chads-davinci-script-releases> (public, hosts the DMGs only)
- **Latest download URL** (share with anyone): <https://github.com/chadlittlepage/chads-davinci-script-releases/releases/latest>
- **Local source clone**: `~/Documents/APPs/Chads DaVinci Script`
- **Local Python build venv**: `.venv-build/` (in repo root, gitignored)
- **App support / settings dir**: `~/Library/Application Support/Chads DaVinci Script/`
- **In-app manual**: Help → Chad's DaVinci Script Help (or `src/chads_davinci/manual_window.py`)
- **Build a release**: bump version in 3 files → commit → `git tag -a vX.Y.Z -m "..."` → `git push origin main vX.Y.Z` → walk away (~5 min)

---

## Project layout

```
Chads DaVinci Script/
├── src/chads_davinci/         ← all the Python source
│   ├── __init__.py            ← __version__ lives here
│   ├── about_window.py        ← About dialog with carbon-nano BG
│   ├── bin_editor.py          ← bin tree editor (NSOutlineView)
│   ├── build_main.py          ← parent process entry point + orchestrator
│   ├── build_worker.py        ← subprocess for clean Resolve API state
│   ├── console_log.py         ← tee stdout/stderr to console.log + auto-rotation
│   ├── diagnostics.py         ← system probe + exception hook + screenshot capture
│   ├── file_picker.py         ← main Cocoa picker window (the big one — 1547 lines)
│   ├── manual_window.py       ← in-app help / manual
│   ├── menu_bar.py            ← native macOS menu bar
│   ├── metadata.py            ← MediaInfo + ffprobe + report writers
│   ├── models.py              ← TrackRole enum, BIN_STRUCTURE, transforms,
│   │                            SUPPORTED_VIDEO_EXTENSIONS, etc.
│   ├── paths.py               ← APP_SUPPORT_DIR + legacy migration
│   ├── progress_window.py     ← floating NSPanel build progress UI
│   ├── resolve_connection.py  ← all DaVinci Resolve scripting API calls
│   ├── settings_io.py         ← user settings + presets persistence
│   └── ui_automation.py       ← AppleScript fallback for read-only Resolve settings
│
├── assets/
│   ├── AppIcon.icns           ← macOS app icon (regenerate with iconutil)
│   ├── AppIcon.iconset/       ← per-size PNGs that go into the .icns
│   ├── icon_source.png        ← 1024x1024 source for the icon
│   ├── about_background.jpg   ← About window background
│   ├── dmg_background.png     ← DMG window background (source)
│   └── dmg_background.jpg     ← DMG window background (composited onto white)
│
├── bin/                       ← BUNDLED BINARIES (not in git)
│   ├── mediainfo              ← downloaded once; CI fetches fresh from build-deps-v1
│   ├── ffprobe                ← same
│   └── README.md              ← where to download them from
│
├── .github/
│   ├── workflows/
│   │   ├── ci.yml             ← lint + syntax check on every push
│   │   └── release.yml        ← full notarized build + double-publish on every v* tag
│   ├── dependabot.yml         ← monthly auto-PRs for pip + actions
│   └── RELEASE_SETUP.md       ← one-time secrets setup doc (already done)
│
├── app_entry.py               ← py2app entry point — wraps build_main.main()
├── setup.py                   ← py2app build config (APP_VERSION lives here)
├── pyproject.toml             ← package metadata (version lives here too)
├── entitlements.plist         ← hardened runtime + AppleScript automation
├── dmg_settings.py            ← dmgbuild config: window size, icon positions, BG
├── build_and_sign.sh          ← one-command local notarized build
│
├── README.md                  ← public-facing project overview + feature list
├── CHANGELOG.md               ← Keep-a-Changelog format release notes
├── LICENSE                    ← proprietary "All Rights Reserved"
└── MAINTAINING.md             ← this file
```

---

## How to do common things

### Cut a new release (the standard flow)

```bash
# 1. Bump the version in three places. Yes, three.
#    a) src/chads_davinci/__init__.py     →  __version__ = "0.2.X"
#    b) setup.py                          →  APP_VERSION = "0.2.X"
#    c) pyproject.toml                    →  version = "0.2.X"

# 2. Add a CHANGELOG entry under [Unreleased] then promote to [0.2.X] — YYYY-MM-DD

# 3. Commit
git add -A
git commit -m "Release v0.2.X — short description"
git push origin main

# 4. Tag and push the tag
git tag -a v0.2.X -m "v0.2.X — short description"
git push origin v0.2.X
```

The release workflow takes ~3.5 minutes:
1. Builds the .app via py2app on a fresh macOS-14 runner
2. Deep-signs every nested binary with hardened runtime + entitlements
3. Submits to Apple notarization, waits for approval, staples the ticket
4. Builds the DMG via dmgbuild (with the carbon-nano background and 105px icons)
5. Signs + notarizes + staples the DMG itself
6. Publishes to the **private source repo's** Releases with the DMG attached
7. Mirrors the same DMG to the **public repo's** Releases

Watch progress: <https://github.com/chadlittlepage/chads-davinci-script/actions>

When done, the public download URL automatically updates to the new version:
<https://github.com/chadlittlepage/chads-davinci-script-releases/releases/latest>

### Build locally without going through CI

```bash
source .venv-build/bin/activate
./build_and_sign.sh
```

Output: `dist/Chads DaVinci Script.dmg`. Same notarization pipeline as CI, just on your laptop. Useful when you want to test a build before tagging.

If `.venv-build/` doesn't exist (or you blew it away), recreate it:

```bash
python3 -m venv .venv-build
source .venv-build/bin/activate
pip install --upgrade pip 'setuptools<81'
pip install py2app dmgbuild Pillow rich pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-Quartz
```

### Run from source (no .app bundle, fastest iteration)

```bash
PYTHONPATH=src python3 -m chads_davinci.build_main
```

This skips py2app entirely. Edit Python files, re-run, see changes immediately. Use this for UI iteration; switch to the full build only when you want to test something that py2app affects (signing, bundled binaries, .icns, etc.).

### Update the in-app manual / help text

Edit `src/chads_davinci/manual_window.py` — the `MANUAL_TEXT` constant near the top. It's a triple-quoted string. Save, run, click Help → Chad's DaVinci Script Help to verify.

### Update the README that end-users see

Two READMEs to consider:
- **Source repo README** (`README.md`) — for developers building from source
- **Public mirror repo README** — for end-users downloading the DMG. To edit:
  ```bash
  cd /tmp && rm -rf cdv-public
  git clone https://github.com/chadlittlepage/chads-davinci-script-releases.git cdv-public
  cd cdv-public
  # edit README.md
  git commit -am "Update README"
  git push
  ```

### Replace the app icon

```bash
# 1. Drop a 1024x1024 PNG (with alpha) into the repo:
cp ~/Desktop/new-icon.png assets/icon_source.png

# 2. Regenerate the iconset and .icns
rm -rf assets/AppIcon.iconset && mkdir assets/AppIcon.iconset
for sz in 16 32 128 256 512; do
    sips -z $sz $sz assets/icon_source.png --out "assets/AppIcon.iconset/icon_${sz}x${sz}.png"
    sz2=$((sz * 2))
    sips -z $sz2 $sz2 assets/icon_source.png --out "assets/AppIcon.iconset/icon_${sz}x${sz}@2x.png"
done
iconutil -c icns assets/AppIcon.iconset -o assets/AppIcon.icns
```

Commit `assets/AppIcon.icns`, the iconset, and `icon_source.png`. The next build will pick it up automatically (referenced in `setup.py` via `iconfile`).

### Replace the DMG background or About-window background

DMG background (the carbon-nano image users see when they open the .dmg):
- Source PNG (with transparency): `assets/dmg_background.png`
- Composited JPG (what dmgbuild actually uses): `assets/dmg_background.jpg`
- Composite PNG → JPG over a white background:
  ```bash
  source .venv-build/bin/activate
  python3 - <<'PY'
  from PIL import Image
  src = Image.open("assets/dmg_background.png").convert("RGBA")
  white = Image.new("RGB", src.size, (255, 255, 255))
  white.paste(src, mask=src.split()[3])
  white.save("assets/dmg_background.jpg", quality=92)
  PY
  ```
- Tweak `dmg_settings.py` if you change dimensions (default is 1200x600)

About-window background: edit `assets/about_background.jpg` directly. Used by `src/chads_davinci/about_window.py`.

### Adjust the DMG layout (icon size, positions, window size)

Edit `dmg_settings.py`:
- `icon_size = 105` — pixel size of the icons in the DMG window
- `icon_locations` — `(x, y)` of each icon in the window
- `window_rect = ((200, 120), (600, 400))` — `((origin_x, origin_y), (width, height))`
- `text_size = 13` — label text size
- `background = "assets/dmg_background.jpg"`

Rebuild the DMG locally (no need to rebuild the .app if you just changed layout):
```bash
source .venv-build/bin/activate
dmgbuild -s dmg_settings.py "Chads DaVinci Script" "dist/Chads DaVinci Script.dmg"
```

### Add a new track role / bin / project setting

Most things are wired into a few places:
- `src/chads_davinci/models.py` — `TrackRole` enum, `SELECTABLE_TRACKS`,
  `REQUIRED_TRACKS`, `OPTIONAL_TRACKS`, `BIN_STRUCTURE`, `TRACK_BIN_MAP`,
  `get_quad_transforms()`
- `src/chads_davinci/file_picker.py` — picker UI; track rows are
  rendered in a loop over `SELECTABLE_TRACKS`, so adding a role usually
  just works
- `src/chads_davinci/resolve_connection.py` — `set_project_settings()`
  calls `project.SetSetting(...)`. Add new keys here.
- `src/chads_davinci/build_worker.py` — orchestrates the build inside
  the subprocess

### Add a new picker form field

Edit `src/chads_davinci/file_picker.py`:
1. Add the control creation in `pick_files()` (the long function near the bottom)
2. Add the field to `FilePickerController.__init__` (set to `None`)
3. Wire the value into `_capture_form_settings()` and `_apply_settings()`
4. Add the field to `PickerResult` near the top of the file
5. If it's a Resolve project setting, plumb it through `okClicked_` →
   `PickerResult` → `build_main.py` → `build_worker.py` →
   `resolve_connection.set_project_settings()`
6. Update `DEFAULT_SETTINGS` in `src/chads_davinci/settings_io.py`

The presets, persistent settings, and Reset Defaults flows all work
through `_capture_form_settings` / `_apply_settings`, so as long as
you wire your new field through those two functions, persistence and
preset save/load will Just Work.

### Update / add an entitlement

Edit `entitlements.plist`. Common keys:
- `com.apple.security.cs.allow-unsigned-executable-memory` — required for py2app
- `com.apple.security.cs.allow-dyld-environment-variables` — required for py2app
- `com.apple.security.cs.disable-library-validation` — required because
  Python.framework and our app have different Team IDs
- `com.apple.security.automation.apple-events` — required for AppleScript

After editing, rebuild from scratch (`./build_and_sign.sh`) — partial
re-signs aren't reliable.

### Rotate the bundled mediainfo / ffprobe binaries

```bash
# 1. Drop new versions into bin/
cp ~/Downloads/mediainfo bin/mediainfo
cp ~/Downloads/ffprobe   bin/ffprobe
chmod +x bin/mediainfo bin/ffprobe

# 2. Verify they run
./bin/mediainfo --version
./bin/ffprobe -version

# 3. Push to the build-deps-v1 release so CI picks them up
gh release upload build-deps-v1 bin/mediainfo bin/ffprobe --clobber
```

If you want a clean break (different ABI, etc.), create `build-deps-v2`:
```bash
gh release create build-deps-v2 bin/mediainfo bin/ffprobe \
  --title "Build dependencies v2" \
  --notes "..." \
  --prerelease
# then update the tag in .github/workflows/release.yml
```

### Roll back to a previous release

```bash
# Delete the tag locally and on GitHub
git tag -d v0.2.X
git push origin :refs/tags/v0.2.X

# Delete the GitHub Releases on both repos
gh release delete v0.2.X --repo chadlittlepage/chads-davinci-script -y
gh release delete v0.2.X --repo chadlittlepage/chads-davinci-script-releases -y

# Optional: revert the commit
git revert <hash>
```

Users who already downloaded v0.2.X still have it; the rollback only
prevents new downloads of that version.

### Reset the local "first launch" welcome dialog

If you want to see the first-launch welcome again (to test it, or to
reset state):

```bash
rm "$HOME/Library/Application Support/Chads DaVinci Script/.first_launch_seen"
```

### Wipe all user data and start fresh

```bash
rm -rf "$HOME/Library/Application Support/Chads DaVinci Script"
```

(There's also a "Reset Defaults" button in the picker that does the
equivalent without nuking the logs directory.)

### Manually wipe just the console logs

```bash
rm "$HOME/Library/Application Support/Chads DaVinci Script/logs/"*.log*
```

The next session will create a fresh `console.log` automatically.

### Tweak log rotation thresholds

Edit the constants at the top of `src/chads_davinci/console_log.py`:

```python
LOG_MAX_AGE_DAYS = 30          # archive after this many days
LOG_MAX_SIZE_BYTES = 10 * 1024 * 1024     # rotate after this many bytes
LOG_TRUNCATE_TO_BYTES = 5 * 1024 * 1024   # keep this many bytes on size rotation
```

### Read the latest console log without opening the app

```bash
tail -200 "$HOME/Library/Application Support/Chads DaVinci Script/logs/console.log"
```

Look for the most recent `=== Session started ===` block. The
system probe is right under it, then any errors / dialogs / build
output for that session.

---

## Secrets and credentials reference

All the credentials live in three places:

### Your local Mac (Keychain Access)

- **Developer ID Application** certificate — created via Xcode → Settings →
  Accounts → Manage Certificates → +. Stays in your login keychain. Used
  by `build_and_sign.sh` and the CI workflow's import step.
- **notarytool keychain profile** named `chads-davinci-notary` — created
  with `xcrun notarytool store-credentials chads-davinci-notary --apple-id ... --team-id ... --password ...`
  Stored as a generic keychain item. Used by `build_and_sign.sh`.

### GitHub repo Secrets (private source repo)

Set at <https://github.com/chadlittlepage/chads-davinci-script/settings/secrets/actions>:

| Secret | What it is |
|---|---|
| `DEVELOPER_ID_CERT_P12_BASE64` | Your Developer ID cert exported as .p12, base64 encoded |
| `DEVELOPER_ID_CERT_PASSWORD` | The password you set on the .p12 |
| `KEYCHAIN_PASSWORD` | Random string — temp keychain password on the runner |
| `APPLE_ID` | `chad.littlepage@me.com` |
| `APPLE_TEAM_ID` | `72J767FV46` |
| `APPLE_APP_SPECIFIC_PASSWORD` | App-specific password from appleid.apple.com (the `xxxx-xxxx-xxxx-xxxx` one) |
| `RELEASES_REPO_TOKEN` | Personal access token used to push DMG to the public mirror repo (currently your gh CLI token) |

To rotate any of them, regenerate the secret on Apple's side (or
re-export the .p12), then `gh secret set <NAME>` and paste the new value.

### Apple's side

- **Apple Developer Program** ($99/year) — required for the Developer ID cert
- **Team ID `72J767FV46`** — your paid Developer Program team
- **App-specific password** — at <https://appleid.apple.com> →
  Sign-In and Security → App-Specific Passwords. Can be revoked
  individually without affecting your Apple ID password.

---

## Architecture notes

### Why there's a parent + subprocess (build_main + build_worker)

The Resolve scripting API and AppleScript UI automation **conflict**.
If we run AppleScript to set the playback frame rate (which the
scripting API treats as read-only) and then keep using the same
Resolve API connection, the API connection enters a wedged state and
subsequent calls fail or return stale data.

The fix is to AppleScript-poke Resolve in the parent process, then
spawn `build_worker.py` as a fresh subprocess that gets a clean Resolve
API connection. The parent waits for the subprocess to finish and
shows the success/failure dialog.

### Why the package layout is `src/chads_davinci/`

It's a "src layout" — keeps the package separated from the project
root so editable installs and tests don't accidentally pick up the
wrong files. py2app needs `PYTHONPATH=src` set during build because of
this; `build_and_sign.sh` does that automatically.

### Why dmgbuild and not create-dmg

create-dmg uses an internal AppleScript template to lay out the DMG
window, and it does NOT expose a way to control text color or
background image positioning at the level we need. dmgbuild writes
the `.DS_Store` directly via Python with full control over every
icon-view property.

(Note: even with dmgbuild, **icon-label text color** in DMG icon view
is not controllable on modern macOS — Apple removed that property.
That's why the DMG background image is light gray rather than dark,
so the auto-rendered black labels remain readable.)

### Why two repos (private source + public mirror)

The source repo is private to keep the code closed. Anyone with read
access to the source repo can also download the DMG via the source
repo's Releases — but you can't share that download URL with random
testers because it requires GitHub authentication.

The public mirror repo (`chads-davinci-script-releases`) holds NOTHING
but a README and the released DMGs. The release workflow publishes to
both. The public mirror's `/releases/latest/Chads.DaVinci.Script.dmg`
URL is anonymously downloadable and is the link you share with anyone.

### Why bundled mediainfo + ffprobe instead of `brew install`

End users don't have Homebrew, ffmpeg, or mediainfo installed. The
app bundles them inside `Contents/Resources/bin/` so it works
out-of-the-box on a fresh Mac. They're statically linked and signed
with the rest of the bundle.

### How the diagnostic stack works (added v0.2.6)

Three layers, all in `src/chads_davinci/diagnostics.py`:

1. **`write_session_probe()`** runs once at the very start of
   `build_main.main()` and writes a one-shot block to `console.log`:
   macOS version, architecture, Python version, PyObjC version,
   app version, locale, screen info, and the path/size/architecture
   of every bundled binary. This is the first thing in every
   exported log — support can see the user's environment in 5 seconds.

2. **`install_global_exception_hook()`** sets `sys.excepthook` AND
   `threading.excepthook` so any unhandled Python exception (main
   thread or background thread) writes a full traceback to
   `console.log` via the rich console. PyObjC's `NSException` is
   wrapped as an `objc_error` Python exception, so it goes through
   the same hook. Without this, py2app's bare "fatal error" dialog
   would lose the traceback entirely.

3. **`log_resolve_connection(ctx)`** runs immediately after
   `connect()` succeeds in the parent process. Logs Resolve product,
   version string, and database count.

`metadata.py` also calls `log_tool_version()` the first time
mediainfo and ffprobe are invoked, so the version line of each
bundled binary lands in the log on first use.

### How the floating progress panel beats Resolve's z-order (v0.2.13+)

DaVinci Resolve is a Qt application. Qt's modal dialogs use a custom
window-server level that bypasses AppKit's normal hierarchy entirely.
After many false starts (`NSFloatingWindowLevel` (3), then
`NSPopUpMenuWindowLevel` (101), neither of which beat Resolve's
modals), the working solution is in `src/chads_davinci/progress_window.py`:

- **`NSPanel`** instead of `NSWindow` (lighter weight, supports more
  styles)
- **`NSWindowStyleMaskNonactivatingPanel`** so clicks don't pull our
  app to the foreground
- **`setLevel_(NSScreenSaverWindowLevel)`** = 1000 (the highest
  user-accessible window level on macOS short of system shielding)
- **`setFloatingPanel_(True)`**
- **`setBecomesKeyOnlyIfNeeded_(True)`** — never steals keyboard focus
- **`setWorksWhenModal_(True)`** — the key flag, stays visible above
  modal sheets/dialogs from other apps
- **`setHidesOnDeactivate_(False)`** — doesn't disappear when our app
  loses focus to Resolve
- **`collectionBehavior` = `canJoinAllSpaces | stationary | fullScreenAuxiliary`**
- **`orderFrontRegardless()`** instead of `makeKeyAndOrderFront_`

The panel runs the Cocoa run loop briefly on every `set_status()`
call (`NSRunLoop.runMode_beforeDate_(NSDefaultRunLoopMode, 0.02)`)
so it actually repaints during synchronous Python work. The
`build_main` → `build_worker` subprocess wait is a polling loop
that calls `progress.pump()` every 50 ms instead of a blocking
`subprocess.run`, so the spinner stays alive throughout.

### How alerts are shown (v0.2.15+)

`build_main._show_alert()` does NOT use `NSAlert`. NSAlert +
`NSRunningApplication.activateWithOptions_` doesn't reliably win
the z-order fight against Resolve on modern macOS — the system
refuses to promote our process to foreground because we're
"background" by the time the build subprocess returns.

Instead, `_show_alert()` uses `osascript -e 'display dialog "..."'`.
AppleScript's `display dialog` is shown by `osascript` itself via
StandardAdditions (NOT via System Events), so:

- It does NOT need Accessibility / TCC permission
- It IS reliably brought to the front by macOS regardless of which
  app is currently active
- It respects system appearance and uses native icons

The same goes for `menu_bar._show_dialog()`. Both fall back to
`NSAlert` only if `osascript` itself fails for some reason.

### How console.log auto-rotation works (v0.2.18)

`src/chads_davinci/console_log.py` has `_rotate_log_if_needed()`
which is called by `setup_logging()` at every session start, before
the log is opened for append:

- **Age cap** (30 days): if `console.log.mtime` is older than
  `LOG_MAX_AGE_DAYS = 30`, the file is renamed to
  `console.log.old` (overwriting any previous backup) and a fresh
  `console.log` is started.
- **Size cap** (10 MB): if `console.log.size` exceeds
  `LOG_MAX_SIZE_BYTES = 10_485_760`, the file is tail-truncated to
  the last `LOG_TRUNCATE_TO_BYTES = 5_242_880` bytes (5 MB) with a
  `=== log truncated (rolling 5 MB cap) ===` marker prepended.
- **All failures are silent.** Log rotation must NEVER block app
  startup. If the rename or truncate fails, the function falls
  through and `setup_logging()` proceeds with whatever is on disk.

To tweak the thresholds, edit the constants at the top of
`console_log.py`. To wipe the log manually:

```bash
rm "$HOME/Library/Application Support/Chads DaVinci Script/logs/"*.log*
```

### How `Help → Export Console Log…` works (v0.2.6+)

`src/chads_davinci/menu_bar.py` `exportConsole_()`:

1. Captures a screenshot of the picker window via
   `screencapture -l <windowID>` (uses `NSApp.mainWindow().windowNumber()`).
   Saved to a tmp file.
2. Shows an `NSSavePanel` so the user picks where to save the .log.
3. Copies `~/Library/Application Support/Chads DaVinci Script/logs/console.log`
   to the chosen path.
4. Moves the screenshot from the tmp file to a sibling `.png` next
   to the chosen .log.
5. Shows a confirmation dialog listing both saved file paths and
   asking the user to email both to support.

If the user cancels the save panel, the tmp screenshot is cleaned up.

### How sandbox-friendly storage works (v0.2.0)

All persistent state goes in
`~/Library/Application Support/Chads DaVinci Script/`:

- `user_settings.json` — picker form defaults
- `bin_structure.json` — saved bin tree
- `presets.json` — named presets
- `.first_launch_seen` — marker; delete to see welcome dialog again
- `reports/` — default location for metadata reports
- `logs/console.log` — current session log
- `logs/console.log.old` — previous archive (one backup)

`src/chads_davinci/paths.py` provides `APP_SUPPORT_DIR` and a
one-shot migration: if the legacy `~/.chads-davinci/` directory
exists from a pre-v0.2.0 install, its contents are copied to the
new location at first import (silent best-effort, never fails).

This location is the only home-directory path an App Sandbox /
Hardened Runtime app can write to without explicit entitlements.

### How three-way ImportMedia fallback works (v0.2.10)

Resolve's `MediaPool.ImportMedia([path])` has a quirk: it sometimes
auto-detects filenames matching `<prefix>_<digits>-<digits>.<ext>`
as the first frame of an image sequence and refuses to import the
file as a standalone clip. We don't know exactly when this triggers
and when it doesn't.

`src/chads_davinci/resolve_connection.py` `_import_one_file()` tries
three Resolve API paths in sequence:

1. `media_pool.ImportMedia([file_str])` — primary (handles real
   image sequences correctly)
2. `media_storage.AddItemListToMediaPool(file_str)` — lower-level,
   bypasses sequence detection
3. `media_pool.ImportMedia([{"FilePath": file_str}])` — clip-info
   dict form, forces single-file mode

Each fallback is logged with which method actually succeeded so
future tester reports show exactly which API path the file came
in through.

---

## Troubleshooting recipes

### "Launch error / fatal error" dialog from py2app on startup

Read the console log:
```bash
tail -200 "$HOME/Library/Application Support/Chads DaVinci Script/logs/console.log"
```

Common causes seen so far:
- **`UnicodeEncodeError`** in a report writer — fixed in v0.2.1, all
  file I/O now uses `encoding="utf-8"`. If a new one appears, search
  for any new `write_text(` or `read_text(` and add the encoding kwarg.
- **`code signature ... different Team IDs`** — the bundle was signed
  without `disable-library-validation`. Re-sign with the entitlements
  file present. CI handles this automatically; for local builds make
  sure `entitlements.plist` is in the repo root.
- **`No module named 'chads_davinci'`** — py2app was run without
  `PYTHONPATH=src`. Use `build_and_sign.sh` instead of running
  `python setup.py py2app` directly.

### Picker freezes / unresponsive on first drag-and-drop

Fixed in v0.2.3 by registering both `NSFilenamesPboardType` AND
`public.file-url`. If a future macOS version breaks it again, the
fix is in `src/chads_davinci/file_picker.py` — search for
`registerForDraggedTypes_` and `_file_path_from_pasteboard`.

### "AppleScript error: ... not allowed assistive access" in console

Suppressed in v0.2.2 — only logs if it's an unexpected AppleScript
failure. The build itself doesn't need this path; the timeline frame
rate is set via the Resolve API and the playback monitor inherits it.

If you actually want the AppleScript path to work (for setting the
playback monitor frame rate when the API treats it as read-only),
the user needs to grant Accessibility permission in System Settings →
Privacy & Security → Accessibility → toggle Chad's DaVinci Script.

### Notarization fails

```bash
# Get the submission log from Apple
xcrun notarytool log <submission-id> --keychain-profile chads-davinci-notary
```

Common causes:
- A nested Mach-O wasn't signed (codesign --deep + the find loop in
  `build_and_sign.sh` should cover all of them; check the loop's
  predicate)
- An entitlement is wrong or the cert's not Developer ID Application
- The Apple Developer Program License Agreement has been updated and
  needs re-acceptance at developer.apple.com

### CI release workflow fails

Watch the run: <https://github.com/chadlittlepage/chads-davinci-script/actions>

Each step has its own log. The most common breakages:
- **Install build dependencies** — pip install something that broke. The
  pin is `setuptools<81` because py2app 0.28 still references the
  legacy distutils paths setuptools 81 removed. Bump it deliberately
  if py2app gets a fix.
- **Download bundled binaries** — the `build-deps-v1` release was
  deleted. Re-create it (see "Rotate the bundled binaries" above).
- **Import Developer ID Application certificate** — the .p12 base64
  secret is wrong, the password is wrong, or the cert expired (they're
  valid for 5 years). Re-export and re-set the secret.
- **Build, sign, notarize, and package DMG** — read the build_and_sign.sh
  output. Apple notarization rejection logs are accessible via
  `xcrun notarytool log <id> --keychain-profile chads-davinci-notary`.

---

## File-locator quick reference

| Where is...? | File / location |
|---|---|
| The version number | `src/chads_davinci/__init__.py`, `setup.py`, `pyproject.toml` (3 places — keep them in sync) |
| The app icon | `assets/AppIcon.icns` (regenerated from `assets/icon_source.png`) |
| The DMG background | `assets/dmg_background.jpg` (composited from `assets/dmg_background.png`) |
| The About-window background | `assets/about_background.jpg` |
| The in-app manual text | `src/chads_davinci/manual_window.py` (`MANUAL_TEXT` constant) |
| The DMG window layout | `dmg_settings.py` |
| The default picker form values | `DEFAULT_SETTINGS` in `src/chads_davinci/settings_io.py` |
| The bin tree default | `BIN_STRUCTURE` in `src/chads_davinci/models.py` |
| The track-to-bin map | `TRACK_BIN_MAP` in `src/chads_davinci/models.py` |
| The quad transform math | `get_quad_transforms()` in `src/chads_davinci/models.py` |
| The list of fixed track rows | `SELECTABLE_TRACKS` in `src/chads_davinci/models.py` |
| The list of frame rates / source resolutions / report formats / marker options | Top of `src/chads_davinci/file_picker.py` |
| User settings on disk | `~/Library/Application Support/Chads DaVinci Script/user_settings.json` |
| Bin structure on disk | `~/Library/Application Support/Chads DaVinci Script/bin_structure.json` |
| Saved presets on disk | `~/Library/Application Support/Chads DaVinci Script/presets.json` |
| First-launch marker | `~/Library/Application Support/Chads DaVinci Script/.first_launch_seen` |
| Console log | `~/Library/Application Support/Chads DaVinci Script/logs/console.log` |
| Default metadata reports dir | `~/Library/Application Support/Chads DaVinci Script/reports/` |

---

## Author

Chad Littlepage · <chad.littlepage@gmail.com>
