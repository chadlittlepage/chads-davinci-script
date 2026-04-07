# Bundled third-party binaries

`mediainfo` (GPL v3) and `ffprobe` (LGPL v2.1+) are bundled into the
`.app` at build time. They are **not** checked into the git repository
because of license/redistribution friction and file size.

You must download them once and place them in this directory before
running `build_and_sign.sh` or `python3 setup.py py2app`.

## Required files

```
bin/mediainfo    arm64 static binary
bin/ffprobe      arm64 static binary
```

## Where to get them

### mediainfo
- Official downloads: <https://mediaarea.net/en/MediaInfo/Download/Mac_OS>
- Choose "MediaInfo CLI" for macOS arm64.
- Extract the archive and copy the `mediainfo` executable here.

### ffprobe
- Official builds (from ffmpeg.org): <https://evermeet.cx/ffmpeg/>
  (Mac arm64 static builds, signed)
- Or build from source via Homebrew: `brew install ffmpeg` then copy
  `$(brew --prefix ffmpeg)/bin/ffprobe` here.

## Verify

```bash
chmod +x bin/mediainfo bin/ffprobe
./bin/mediainfo --version
./bin/ffprobe -version
file bin/mediainfo bin/ffprobe   # should report 'arm64' or 'universal'
```

If both commands print version info, you're ready to build.

## Notes

- The `.app` bundle ships these in `Contents/Resources/bin/` and the
  Python code resolves them via `chads_davinci.metadata._find_bundled_tool`.
- They are signed at build time by `build_and_sign.sh` along with the
  rest of the bundle, so notarization succeeds without extra setup.
- Do **not** commit the binaries; `.gitignore` already excludes them.
