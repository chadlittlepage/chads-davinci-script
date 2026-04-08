"""Comprehensive in-app manual window.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import objc
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSFont,
    NSMakeRect,
    NSMakeSize,
    NSObject,
    NSScrollView,
    NSTextView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)

# Module-level retention to prevent GC
_RETAINED = []


MANUAL_TEXT = """\
Chad's DaVinci Script — User Manual
====================================

OVERVIEW
This tool automates the setup of a DaVinci Resolve project for quad-view
HDR metadata testing. In one click it will:

  • Create or replace a Resolve project in the database/folder you choose
  • Build a custom bin/sub-bin structure in the media pool
  • Import each assigned media file into the correct bin
  • Build a 7-track quad-view timeline with pre-applied transforms
  • Add user-defined extra video tracks above the quad
  • Configure timeline resolution, frame rate, color management, video
    monitoring, image scaling, and SDI output options
  • Extract per-clip metadata using MediaInfo and ffprobe
  • Save metadata reports in Text / CSV / JSON / HTML
  • Optionally drop Resolve markers on the timeline OR export an EDL file

You can also run a metadata-only mode that skips the Resolve build entirely.


GETTING STARTED
1. Launch DaVinci Resolve.
2. Open Chad's DaVinci Script.
3. (Optional) Pick a saved Preset from the top-right dropdown to recall a
   prior configuration.
4. Assign your video files to the 6 track rows (drag from Finder, paste a
   path, or click Browse).
5. (Optional) Click "+ Add Video Track" to add additional tracks above
   REEL SOURCE.
6. Click "Connect to Resolve" to fetch the database list.
7. Choose your database, folder, project name, color spaces, frame rate,
   metadata tools, report format, and marker option.
8. Click OK to build the full project, or Metadata Export to extract
   metadata only.

All form values you set are saved automatically and restored the next time
you launch the app.


FILE ASSIGNMENT — FIXED ROWS
The picker has 6 fixed track rows for the quad-view layout:

  REEL SOURCE             (optional) — original reference video (V2 off)
  HW2 300 nit             (required) — Quadrant 1, top-left
  L1SHW 300               (required) — Quadrant 2, top-right
  HW2 795 Stretch 1500    (required) — Quadrant 3, bottom-left
  L1SHW 795 Stretch 1500  (required) — Quadrant 4, bottom-right
  L1SHW HDMI              (optional) — HDMI feed (V7 off)

V1 (QUAD Template) is auto-generated as 4 Solid Color compound clips named
Quad 1-4, colored Orange, with the matching transform values pre-applied as
a copy-paste reference.

For each row you can:
  • Drag a video file from Finder directly onto the path field. The drop
    target highlights with a blue outline while you hover.
  • Click Browse... to open a file picker
  • Paste a path with Cmd+V
  • Click the ✕ button on the right to clear that row
  • Edit the Track Name field to customize the name shown in the timeline


+ ADD VIDEO TRACK — EXTRA TRACKS
Click "+ Add Video Track" (left side, below the file rows) to add an extra
video track row. The picker grows downward automatically — no scrolling.

Extra rows always insert at the TOP of the extras section, immediately
below the column headers and ABOVE REEL SOURCE. The newest extra is at the
top of the stack; older extras shift down.

Each extra row has:
  • Editable track name (defaults to "Extra N")
  • Drop / paste / Browse path field (same drag highlight as fixed rows)
  • Delete button — removes that row and shrinks the window

Extras are imported into a Master / Extras bin in Resolve. Each extra
becomes a NEW video track at the TOP of the timeline stack (highest video
track number = visually topmost in Resolve), in the same order shown in
the picker. No quad transform is applied to extras — they play full-frame.

Extras are saved with your settings and presets, and persist across launches.


PRESETS (top-right corner)
The Preset row at the top right lets you save and recall full picker
configurations.

  • Preset dropdown — select a saved preset to instantly load it
  • Save  — opens a name prompt and saves the CURRENT form state as a
            preset (or overwrites an existing preset of the same name)
  • Delete — deletes the currently selected preset (with confirmation)

A preset captures:
  • All track names (fixed + extras)
  • Folder, Project Name, Source Resolution, Frame Rate, Start Timecode
  • Timeline / Output Color Space
  • MediaInfo / ffprobe toggles
  • Metadata Report format
  • Resolve Markers option
  • All extra video tracks (name + path)

Presets are stored in
~/Library/Application Support/Chads DaVinci Script/presets.json


RESET DEFAULTS
The "Reset Defaults" button (just below Resolve Markers) wipes ALL saved
user settings + bin structure, removes any extra tracks, and re-populates
the form with the factory defaults. Use this if your saved state ever gets
into a strange shape.


RESOLVE PROJECT SETTINGS

Resolve:        Click "Connect to Resolve" to fetch databases. Status shows
                green when connected, orange if no project is currently
                open in Resolve (the script falls back to "Local Database"
                in that case, which works for most use cases).

Database Type:  Local / Network / Cloud — filters the Database dropdown.

Database:       The Resolve database to use. Auto-populated when connected.

Folder:         The Project Manager folder where the project will be
                created. Created automatically if it doesn't exist.

Project Name:   Name of the new project. If a project of the same name
                already exists, it is automatically closed and replaced.

Bin Structure:  Click "Edit Bins..." to open the Bin Editor side window
                (see BIN EDITOR section below).

Source Resolution:
                Choose the resolution of your source files:
                  • 1920x1080 HD → builds a 4K timeline (3840x2160)
                  • 3840x2160 UHD → builds an 8K timeline (7680x4320)
                Timeline is always 2× the source so all 4 quads fit at 1:1.

Frame Rate:     23.976 / 24 / 25 / 29.97 / 30 / 48 / 50 / 59.94 / 60. Sets
                the timeline frame rate. The playback frame rate and video
                monitoring format are automatically matched.

Start Timecode: Initial timecode for the timeline. Default 00:00:00:00.

Timeline Color Space / Output Color Space:
                Default is Rec.2100 ST2084 (HDR PQ). Change to any of the
                Resolve color spaces including Rec.709 variants, Rec.2020,
                P3, ACES (cc / cct / cg), and camera native (ARRI LogC3/4,
                Sony S-Gamut3, Canon Cinema Gamut, RED Wide Gamut,
                Panasonic V-Gamut, BMD Film Gen 5).


BIN EDITOR
Click "Edit Bins..." in the picker to open a side window where you can:

  • View the entire bin / sub-bin tree (default: HW5, LWL15, HWL15,
    SOURCE, HW2 with sub-bins)
  • Add Top Bin — create a new top-level bin
  • Add Sub-Bin — create a sub-bin under the selected bin
  • Rename — edit the name of the selected bin inline
  • Delete — remove the selected bin
  • Save — persist your changes as the new default
  • Cancel — discard changes
  • Revert to Default — restore the original bin structure

Saved bins are stored in
~/Library/Application Support/Chads DaVinci Script/bin_structure.json
and loaded automatically next time you open the editor.

If you rename a bin (e.g. HW2 → FOO), the script automatically updates
the track→bin mapping so files still go to the renamed bin.


SUPPORTED FILE FORMATS
The picker accepts ANY file Resolve can read — there is no extension
filter on drag-drop or the Browse panel.

Container formats (single video file):
  • QuickTime / MPEG-4 — .mov, .mp4, .m4v, .mkv, .avi, .webm
  • Broadcast / pro     — .mxf, .ts, .m2t, .m2ts, .mts
  • Camera RAW / vendor:
      .braw          Blackmagic RAW
      .r3d           RED REDCODE RAW
      .ari, .arx     ARRIRAW
      .crm, .rmf     Canon Cinema RAW Light
      .dng           CinemaDNG
      .cine          Phantom Cine

Codecs (carried inside the containers above):
  • Apple ProRes (422, 422 HQ, 422 LT, 422 Proxy, 4444, 4444 XQ)
  • Avid DNxHD, DNxHR
  • H.264, H.265 / HEVC
  • XAVC, XAVC-I, XAVC-S
  • AVC-Intra, AVCHD
  • MPEG-2 (XDCAM HD/EX), MPEG-4
  • DV, DVCPRO, HDV
  • Cineform (GoPro)
  • Sony X-OCN

Image sequences (each frame is a single file; Resolve treats the
sequence as ONE clip on the timeline):
  • .dpx        Digital Picture Exchange (SMPTE 268M)
  • .tif, .tiff TIFF
  • .exr        OpenEXR
  • .jpg, .jpeg JPEG
  • .jp2, .j2k  JPEG 2000
  • .png        PNG
  • .tga        Targa
  • .bmp        Bitmap
  • .hdr        Radiance HDR
  • .cin        Cineon

Audio (rarely used in this picker but supported by Resolve):
  • .wav, .aif, .aiff, .flac, .mp3, .m4a, .aac


WORKING WITH IMAGE SEQUENCES
For DPX, TIFF, EXR, JPEG, etc. sequences:

1. Drag a SINGLE FRAME from the sequence onto a track row (e.g.
   "frame.0001.dpx"). Resolve auto-detects the rest of the sequence
   in the same folder and imports the entire run as ONE clip.

2. The metadata extraction automatically detects the sequence and
   reports the total frame count + duration of the WHOLE sequence,
   not just the dropped file.

3. The console.log shows the detected pattern, e.g.
   "Extracting metadata: frame.[####].dpx (image sequence, 1200 frames)"

4. The sequence appears as one entry in the bin and as one clip on
   the V3-V6 quad tracks, with the same transform math applied.

If your sequence isn't being auto-detected, make sure:
  • The frame numbers are zero-padded consistently (frame.0001 not
    frame.1)
  • All frames are in the SAME folder
  • The naming pattern is consistent (same prefix, same digit count,
    same extension)


METADATA EXTRACTION
The script bundles MediaInfo and ffprobe inside the .app — no install,
no PATH config required.

Metadata Tools:  Toggle MediaInfo and ffprobe checkboxes independently.
                 Both run by default for the most complete metadata.

The metadata extracted includes:
  • Codec, resolution, frame rate, bit depth, color space
  • Color primaries, transfer characteristics, matrix coefficients
  • HDR10: MaxCLL, MaxFALL, mastering display metadata
  • Dolby Vision: profile, level, RPU presence, BL signal compatibility ID,
    EL type

Metadata Report (Metadata Report dropdown):
  • None — no report file
  • Text (.txt) — human-readable
  • CSV (.csv) — spreadsheet-friendly
  • JSON (.json) — machine-readable
  • HTML (.html) — styled report
  • All formats — saves all four

Reports are saved to the export directory you choose (Metadata Export
mode) or to ~/Library/Application Support/Chads DaVinci Script/reports/
in normal Build mode.

Resolve Markers (Resolve Markers dropdown):
  • None — no markers
  • Add to Timeline — places metadata markers directly on the Resolve
    timeline at evenly spaced positions, color-cycled by track
  • Export as EDL file — writes a .edl marker file you can import into
    Resolve via File > Import > Timeline > Markers from EDL
  • Both — does both


METADATA EXPORT MODE
Click the Metadata Export button instead of OK to skip the Resolve build
entirely and just extract metadata. Useful for:

  • Quickly inspecting one or more files
  • Generating reports without touching Resolve
  • Exporting EDL markers for later use
  • Working when Resolve is not running

A folder picker appears so you can choose where to save the files. The
required-track validation is skipped — Metadata Export works with any
number of assigned files (1 or more), including extras.

When the export finishes, Finder opens to your chosen output folder.


MENU BAR

App menu (Chad's DaVinci Script):
  About — opens the About window
  Hide / Hide Others / Show All — standard macOS commands
  Quit — closes the app

File menu:
  Export Settings… (⇧⌘E) — saves user preferences + bin structure to a
                            JSON file you can transfer to another machine
  Import Settings… (⇧⌘I) — loads a previously exported settings file

Edit menu:
  Standard Cut / Copy / Paste / Select All shortcuts

Help menu:
  Chad's DaVinci Script Help — opens this manual
  Export Console Log… — saves the session log file. If something crashes
                        or behaves unexpectedly, use this to save the log
                        and email it to chad.littlepage@gmail.com


PROJECT SETTINGS APPLIED AUTOMATICALLY
The script configures the following Resolve project settings on Build:

Master Settings:
  Timeline resolution: 3840x2160 (4K) or 7680x4320 (8K) based on Source
  Timeline frame rate / Playback frame rate: matched to your selection
  Pixel aspect ratio: Square

Video Monitoring:
  Video Resolution: matches timeline
  Format: matches timeline + frame rate
  Use 4:4:4 SDI: enabled
  SDI Configuration: Quad link
  Data levels: Full
  Video bit depth: 12 if SDI hardware supports it, otherwise 10 / 8 fallback

Color Management:
  Color science: DaVinci YRGB
  Timeline color space: as you select (default Rec.2100 ST2084)
  Output color space: as you select (default Rec.2100 ST2084)

Image Scaling:
  Resize filter: Sharper
  Mismatched resolution files (Input + Output): Center crop with no resizing
  Match timeline settings (Output): enabled


TIMELINE STRUCTURE BUILT
With no extras added, the timeline has 7 video tracks:

Track  Name                        Quadrant     Default
V8+    (your extras, top-down)     full-frame   Enabled
V7     L1SHW HDMI                  (full)       Disabled
V6     L1SHW 795 Stretch 1500      Q4 BR        Enabled
V5     HW2 795 Stretch 1500        Q3 BL        Enabled
V4     L1SHW 300                   Q2 TR        Enabled
V3     HW2 300 nit                 Q1 TL        Enabled
V2     REEL SOURCE                 (full)       Disabled
V1     QUAD Template (auto)        Reference    Disabled

Each extra video track you add via "+ Add Video Track" becomes V8, V9, V10
… in the order shown in the picker (topmost picker row → highest track
number). Extras are placed in a Master / Extras bin in the media pool.


PERSISTENT SETTINGS
Every time you click OK or Metadata Export, the current form state is
saved to disk. The next launch restores:

  • All track names (fixed + extras)
  • Folder, Project Name, Source Resolution, Frame Rate, Start Timecode
  • Timeline / Output Color Space
  • MediaInfo / ffprobe toggles
  • Metadata Report format and Resolve Markers option
  • The complete extras list (names + paths)
  • The bin structure from the Bin Editor

Use Reset Defaults to wipe everything back to factory state.


FILE LOCATIONS
~/Library/Application Support/Chads DaVinci Script/
    ├── user_settings.json     Picker form defaults (auto-saved on OK)
    ├── bin_structure.json     Saved custom bin structure
    ├── presets.json           Named presets dictionary
    ├── reports/               Default location for metadata reports
    └── logs/console.log       Session console log (rolling)

Note: legacy installs that wrote to ~/.chads-davinci/ are migrated to the
new Application Support location automatically on first launch.


KEYBOARD SHORTCUTS
  Cmd+V                       Paste a file path into the focused field
  Cmd+Q                       Quit
  Shift+Cmd+E                 File > Export Settings…
  Shift+Cmd+I                 File > Import Settings…
  Return (when picker is up)  OK (build the project)


TROUBLESHOOTING

App won't open (Gatekeeper warning)
  The signed/notarized build should open with no warnings. If you have an
  unsigned development build, right-click the app and choose Open — that
  bypasses Gatekeeper for the first launch.

Apple wants permission for "Chad's DaVinci Script to control DaVinci Resolve"
  This is the macOS Automation prompt. The script uses AppleScript to set
  the playback frame rate (which is read-only via the Resolve API). Click
  OK / Allow once and you'll never see it again.

"Connect to Resolve" shows orange / no databases
  This means no project is currently open in Resolve. The script falls
  back to "Local Database" which works fine for most use cases.

Bins don't get created / media doesn't import
  Make sure DaVinci Resolve is running BEFORE clicking OK in the picker.

Bit depth shows 8 or 10 instead of 12
  12-bit output is only available with compatible Blackmagic SDI hardware.
  The script attempts 12 → falls back to 10 → 8 based on what's supported.

Drag-and-drop doesn't highlight / nothing happens
  Drop directly onto a path field. The field will outline in blue while
  you hover. Drops outside a path field are ignored.

Extras don't appear in Resolve
  Extras only appear when you click OK (full Build). In Metadata Export
  mode, extras are included for metadata extraction but no Resolve
  timeline is built.

Saved settings won't load / "Reset Defaults" needed
  If a saved state gets out of sync (e.g. after an update), click
  Reset Defaults to wipe and restart fresh.

Crash or unexpected behavior
  Use Help > Export Console Log… and email the log to
  chad.littlepage@gmail.com along with a description of what happened.


CREDITS
Created by Chad Littlepage
chad.littlepage@gmail.com
323.974.0444

© 2026 Chad Littlepage
"""


class ManualController(NSObject):
    """Controller for the manual window."""

    def init(self):
        self = objc.super(ManualController, self).init()
        if self is not None:
            self.window = None
        return self

    def closeClicked_(self, sender):
        if self.window:
            self.window.close()


def show_manual_window() -> None:
    """Show the manual window with scrollable text content."""
    controller = ManualController.alloc().init()

    win_w, win_h = 760, 720
    style = (
        NSWindowStyleMaskTitled
        | NSWindowStyleMaskClosable
        | NSWindowStyleMaskResizable
        | NSWindowStyleMaskMiniaturizable
    )

    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, win_w, win_h),
        style,
        NSBackingStoreBuffered,
        False,
    )
    window.setTitle_("Chad's DaVinci Script — Manual")
    window.setMinSize_(NSMakeSize(500, 400))
    window.center()
    controller.window = window

    content = window.contentView()

    # Scroll view containing the text
    btn_h = 28
    margin = 16
    scroll_y = margin + btn_h + 16
    scroll_h = win_h - margin - 16 - scroll_y
    scroll = NSScrollView.alloc().initWithFrame_(
        NSMakeRect(margin, scroll_y, win_w - 2 * margin, scroll_h)
    )
    scroll.setHasVerticalScroller_(True)
    scroll.setBorderType_(2)  # NSBezelBorder
    scroll.setAutoresizingMask_(2 | 16)  # flexible W + H

    # Text view inside scroll
    text_view = NSTextView.alloc().initWithFrame_(
        NSMakeRect(0, 0, win_w - 2 * margin - 20, scroll_h)
    )
    text_view.setEditable_(False)
    text_view.setSelectable_(True)
    text_view.setDrawsBackground_(True)
    text_view.setBackgroundColor_(NSColor.textBackgroundColor())
    text_view.setRichText_(False)
    text_view.setFont_(NSFont.fontWithName_size_("Menlo", 12) or NSFont.systemFontOfSize_(12))

    # Set text
    text_view.setString_(MANUAL_TEXT)
    text_view.setAutoresizingMask_(2 | 16)

    scroll.setDocumentView_(text_view)
    content.addSubview_(scroll)

    # Close button at the bottom right
    close_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(win_w - margin - 100, margin, 100, btn_h)
    )
    close_btn.setTitle_("Close")
    close_btn.setBezelStyle_(1)
    close_btn.setKeyEquivalent_("\r")
    close_btn.setTarget_(controller)
    close_btn.setAction_("closeClicked:")
    close_btn.setAutoresizingMask_(1 | 32)  # left margin + top margin flex (sticks bottom-right)
    content.addSubview_(close_btn)

    window.makeKeyAndOrderFront_(None)
    NSApp.activateIgnoringOtherApps_(True)

    _RETAINED.append((controller, window))
