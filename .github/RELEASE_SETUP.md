# Release pipeline — one-time setup

The `release.yml` workflow builds, signs, notarizes, and publishes a DMG
to GitHub Releases whenever you push a tag like `v0.2.1`. Before it can
run successfully you need to provision the macOS runner with your Apple
credentials.

## 1. Apple side (one time, on apple.com)

1. **Developer ID Application certificate**
   - Apple Developer → Certificates → "+" → "Developer ID Application"
   - Generate a CSR locally with Keychain Access → Certificate Assistant
   - Download the resulting `.cer`, double-click to install in your login keychain
   - Open Keychain Access → My Certificates → right-click → Export → save as
     `developer-id-application.p12` with a strong password

2. **App-specific password for notarytool**
   - <https://appleid.apple.com> → Sign-In and Security → App-Specific Passwords
   - Generate a new one named "chads-davinci-notary"
   - Save it somewhere safe — it's only shown once

3. **Find your Team ID**
   - Apple Developer → Membership → Team ID (10-character string)

## 2. GitHub side (one time, in this repo)

Settings → Secrets and variables → Actions

### Repository secrets (Secrets tab)

| Name | Value |
|---|---|
| `DEVELOPER_ID_CERT_P12_BASE64` | `base64 -i developer-id-application.p12 \| pbcopy` |
| `DEVELOPER_ID_CERT_PASSWORD`   | the password you set on the .p12 |
| `KEYCHAIN_PASSWORD`            | any random string (it's just a temp keychain password) |
| `APPLE_ID`                     | your Apple ID email (e.g. `chad.littlepage@gmail.com`) |
| `APPLE_TEAM_ID`                | your 10-char Team ID |
| `APPLE_APP_SPECIFIC_PASSWORD`  | the app-specific password from step 1.2 |

### Bundled binaries (mediainfo + ffprobe)

These are NOT in the repo (license + 65MB). They're stored as assets on a
dedicated GitHub Release tagged `build-deps-v1` in this same repo, and the
workflow downloads them via `gh release download` using the standard
workflow token. No extra setup is required — it just works as long as the
`build-deps-v1` release exists with `mediainfo` and `ffprobe` as assets.

To rotate the binaries (e.g. new ffmpeg version):

```bash
# Replace the local files at bin/mediainfo and bin/ffprobe, then:
gh release upload build-deps-v1 bin/mediainfo bin/ffprobe --clobber
```

To create a fresh release version (e.g. when you want a clean break):

```bash
gh release create build-deps-v2 bin/mediainfo bin/ffprobe \
  --title "Build dependencies v2" \
  --notes "..." \
  --prerelease
# then update the tag in .github/workflows/release.yml
```

## 3. Cut a release

```bash
# Bump version in src/chads_davinci/__init__.py and setup.py first.
git commit -am "Release v0.2.1"
git tag -a v0.2.1 -m "v0.2.1"
git push origin main v0.2.1
```

The workflow runs in 5–15 minutes (most of that is Apple notarization).
When it finishes, the new release with its DMG appears at:
<https://github.com/chadlittlepage/chads-davinci-script/releases>

## Troubleshooting

- **`Could not find a Developer ID Application identity`** — the .p12 base64
  is wrong, the password is wrong, or `set-key-partition-list` failed. Check
  the `Import Developer ID Application certificate` step's logs.
- **`Notarization failed: Invalid`** — run `xcrun notarytool log <submission-id>
  --keychain-profile chads-davinci-notary` locally to see Apple's reasons.
  Common cause: a nested binary was missed by codesign — re-check the
  `Sign nested Mach-O binaries` step in `build_and_sign.sh`.
- **`unzip: cannot find ...`** — the binary inside the downloaded zip has a
  different name than expected. Adjust the `unzip -p ... <NAME> > bin/...`
  line in the download step.
