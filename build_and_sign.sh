#!/usr/bin/env bash
#
# Build, sign, notarize, and package "Chad's DaVinci Script" for distribution.
#
# Output: dist/Chads DaVinci Script.dmg — a notarized, stapled, drag-to-install
# DMG that any third party can open without Gatekeeper warnings.
#
# Prerequisites (one-time setup on the build machine):
#   1. An Apple Developer ID Application certificate installed in the login
#      Keychain (Apple Developer → Certificates → "+" → Developer ID Application).
#      Verify with: security find-identity -v -p codesigning
#
#   2. A notarytool keychain profile saved with your Apple ID + app-specific
#      password + Team ID. Create once with:
#
#        xcrun notarytool store-credentials chads-davinci-notary \
#          --apple-id "you@example.com" \
#          --team-id "ABCDE12345" \
#          --password "xxxx-xxxx-xxxx-xxxx"   # app-specific password
#
#   3. create-dmg installed:  brew install create-dmg
#
# Environment variables you can override:
#   SIGN_IDENTITY        Code signing identity name. Defaults to the first
#                        "Developer ID Application:" identity in the keychain.
#   NOTARY_PROFILE       Notarytool keychain profile name (default chads-davinci-notary)
#
# Usage:  ./build_and_sign.sh
#

set -euo pipefail

# ----- Config ---------------------------------------------------------------

APP_NAME="Chad's DaVinci Script"
APP_PATH="dist/${APP_NAME}.app"
DMG_NAME="Chads DaVinci Script"
DMG_PATH="dist/${DMG_NAME}.dmg"
ENTITLEMENTS="entitlements.plist"
NOTARY_PROFILE="${NOTARY_PROFILE:-chads-davinci-notary}"

# Auto-detect signing identity if not provided
if [[ -z "${SIGN_IDENTITY:-}" ]]; then
    SIGN_IDENTITY="$(security find-identity -v -p codesigning \
        | awk -F'"' '/Developer ID Application/ {print $2; exit}')"
fi
if [[ -z "${SIGN_IDENTITY:-}" ]]; then
    echo "ERROR: No 'Developer ID Application' code-signing identity found."
    echo "Install one from your Apple Developer account, then re-run."
    exit 1
fi

echo "==> Using signing identity: ${SIGN_IDENTITY}"
echo "==> Using notarytool profile: ${NOTARY_PROFILE}"

# ----- 1. Clean + build .app via py2app ------------------------------------

echo "==> Cleaning previous build..."
rm -rf build dist

# py2app refuses install_requires, but pyproject.toml may declare deps.
# Move it aside temporarily so py2app sees a bare setup.py.
PYPROJECT_HIDDEN=0
if [[ -f pyproject.toml ]]; then
    mv pyproject.toml pyproject.toml.bak
    PYPROJECT_HIDDEN=1
fi
trap '[[ "${PYPROJECT_HIDDEN}" == "1" ]] && [[ -f pyproject.toml.bak ]] && mv pyproject.toml.bak pyproject.toml || true' EXIT

echo "==> Building .app via py2app..."
# src-layout: tell modulegraph where to find chads_davinci.
PYTHONPATH=src python3 setup.py py2app

if [[ ! -d "${APP_PATH}" ]]; then
    echo "ERROR: py2app did not produce ${APP_PATH}"
    exit 1
fi

# Restore pyproject.toml early so it's back even if subsequent steps fail.
if [[ "${PYPROJECT_HIDDEN}" == "1" ]] && [[ -f pyproject.toml.bak ]]; then
    mv pyproject.toml.bak pyproject.toml
    PYPROJECT_HIDDEN=0
fi

# ----- 2. Sign every Mach-O inside the bundle ------------------------------

echo "==> Signing nested Mach-O binaries (frameworks, dylibs, .so, helper bins)..."
# Sign deepest-first so containers can re-seal cleanly. We pick up:
#   - Bundled tools (mediainfo, ffprobe) under Contents/Resources/bin
#   - Python .so / .dylib extension modules under Contents/Resources/lib
#   - Embedded Python framework executables
find "${APP_PATH}" \
    \( -name "*.dylib" -o -name "*.so" -o -name "mediainfo" -o -name "ffprobe" \
       -o -path "*/Contents/MacOS/*" -o -path "*/Frameworks/*/Versions/*/Python*" \) \
    -type f -print0 \
  | while IFS= read -r -d '' f; do
        codesign --force --options runtime --timestamp \
                 --entitlements "${ENTITLEMENTS}" \
                 --sign "${SIGN_IDENTITY}" "$f" || true
    done

# ----- 3. Sign the .app bundle itself --------------------------------------

echo "==> Signing the app bundle..."
codesign --force --deep --options runtime --timestamp \
         --entitlements "${ENTITLEMENTS}" \
         --sign "${SIGN_IDENTITY}" "${APP_PATH}"

echo "==> Verifying signature..."
codesign --verify --deep --strict --verbose=2 "${APP_PATH}"

# ----- 4. Notarize the .app ------------------------------------------------

ZIP_PATH="dist/${APP_NAME}.zip"
echo "==> Zipping for notarization..."
ditto -c -k --sequesterRsrc --keepParent "${APP_PATH}" "${ZIP_PATH}"

echo "==> Submitting to Apple notarization service (this can take several minutes)..."
xcrun notarytool submit "${ZIP_PATH}" \
    --keychain-profile "${NOTARY_PROFILE}" \
    --wait

echo "==> Stapling notarization ticket to the app..."
xcrun stapler staple "${APP_PATH}"
xcrun stapler validate "${APP_PATH}"

rm -f "${ZIP_PATH}"

# ----- 5. Build the DMG ----------------------------------------------------

# Use dmgbuild (Python) instead of create-dmg so the .DS_Store is written
# directly with our exact icon size, positions, and background image.
if ! python3 -c "import dmgbuild" 2>/dev/null; then
    echo "WARNING: dmgbuild not installed in current Python. Run:"
    echo "  pip install dmgbuild"
    echo "Skipping DMG creation. The signed/notarized .app is at: ${APP_PATH}"
    exit 0
fi

echo "==> Building DMG via dmgbuild..."
rm -f "${DMG_PATH}"
python3 -m dmgbuild -s dmg_settings.py "Chads DaVinci Script" "${DMG_PATH}"

# ----- 6. Sign + notarize the DMG itself -----------------------------------

echo "==> Signing the DMG..."
codesign --force --sign "${SIGN_IDENTITY}" --timestamp "${DMG_PATH}"

echo "==> Notarizing the DMG..."
xcrun notarytool submit "${DMG_PATH}" \
    --keychain-profile "${NOTARY_PROFILE}" \
    --wait

echo "==> Stapling DMG..."
xcrun stapler staple "${DMG_PATH}"
xcrun stapler validate "${DMG_PATH}"

echo
echo "================================================================="
echo " SUCCESS"
echo " Signed + notarized DMG: ${DMG_PATH}"
echo " Third parties can now drag the .app to /Applications and open it"
echo " without any Gatekeeper warnings."
echo "================================================================="
