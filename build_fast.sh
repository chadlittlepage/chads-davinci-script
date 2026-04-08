#!/usr/bin/env bash
#
# FAST local build of "Chad's DaVinci Script".
#
# Skips the second notarization round (DMG itself). The .app inside the
# DMG is still fully signed, notarized, and stapled, so Gatekeeper will
# happily open it from the DMG — Apple verifies the stapled ticket on
# the .app, not on the DMG container.
#
# Time saved vs build_and_sign.sh: ~2-5 minutes (one fewer notarization
# round-trip + no dist wipe between runs).
#
# Use this for iteration. Use build_and_sign.sh for distribution to
# third parties on metered connections (the second DMG notarization
# matters only when the recipient is offline at first run).
#

set -euo pipefail

APP_NAME="Chad's DaVinci Script"
APP_PATH="dist/${APP_NAME}.app"
DMG_NAME="Chads DaVinci Script"
DMG_PATH="dist/${DMG_NAME}.dmg"
ENTITLEMENTS="entitlements.plist"
NOTARY_PROFILE="${NOTARY_PROFILE:-chads-davinci-notary}"

if [[ -z "${SIGN_IDENTITY:-}" ]]; then
    SIGN_IDENTITY="$(security find-identity -v -p codesigning \
        | awk -F'"' '/Developer ID Application/ {print $2; exit}')"
fi

echo "==> [fast] Signing identity: ${SIGN_IDENTITY}"
echo "==> [fast] Notary profile:   ${NOTARY_PROFILE}"

# Don't wipe dist — let py2app do an incremental rebuild. Only remove
# the previous .app + .dmg so we get a clean output without re-shipping
# bundled deps every run.
chflags -R nohidden dist 2>/dev/null || true
rm -rf "${APP_PATH}" "${DMG_PATH}" build

PYPROJECT_HIDDEN=0
if [[ -f pyproject.toml ]]; then
    mv pyproject.toml pyproject.toml.bak
    PYPROJECT_HIDDEN=1
fi
trap '[[ "${PYPROJECT_HIDDEN}" == "1" ]] && [[ -f pyproject.toml.bak ]] && mv pyproject.toml.bak pyproject.toml || true' EXIT

echo "==> [fast] Building .app via py2app..."
PYTHONPATH=src python3 setup.py py2app 2>&1 | tail -3

if [[ "${PYPROJECT_HIDDEN}" == "1" ]] && [[ -f pyproject.toml.bak ]]; then
    mv pyproject.toml.bak pyproject.toml
    PYPROJECT_HIDDEN=0
fi

if [[ ! -d "${APP_PATH}" ]]; then
    echo "ERROR: py2app did not produce ${APP_PATH}"
    exit 1
fi

echo "==> [fast] Signing nested Mach-O binaries..."
find "${APP_PATH}" \
    \( -name "*.dylib" -o -name "*.so" -o -name "mediainfo" -o -name "ffprobe" \
       -o -path "*/Contents/MacOS/*" -o -path "*/Frameworks/*/Versions/*/Python*" \) \
    -type f -print0 \
  | while IFS= read -r -d '' f; do
        codesign --force --options runtime --timestamp \
                 --entitlements "${ENTITLEMENTS}" \
                 --sign "${SIGN_IDENTITY}" "$f" >/dev/null 2>&1 || true
    done

echo "==> [fast] Signing the app bundle..."
codesign --force --deep --options runtime --timestamp \
         --entitlements "${ENTITLEMENTS}" \
         --sign "${SIGN_IDENTITY}" "${APP_PATH}" >/dev/null

ZIP_PATH="dist/${APP_NAME}.zip"
ditto -c -k --sequesterRsrc --keepParent "${APP_PATH}" "${ZIP_PATH}"

echo "==> [fast] Notarizing .app (single round)..."
xcrun notarytool submit "${ZIP_PATH}" \
    --keychain-profile "${NOTARY_PROFILE}" \
    --wait | tail -10

echo "==> [fast] Stapling .app..."
xcrun stapler staple "${APP_PATH}" >/dev/null
rm -f "${ZIP_PATH}"

echo "==> [fast] Building DMG..."
python3 -m dmgbuild -s dmg_settings.py "${DMG_NAME}" "${DMG_PATH}" 2>&1 | tail -3

echo "==> [fast] Signing DMG (no notarization round)..."
codesign --force --sign "${SIGN_IDENTITY}" --timestamp "${DMG_PATH}" >/dev/null

echo
echo "================================================================="
echo " FAST BUILD DONE"
echo " ${DMG_PATH}"
echo " .app inside is notarized + stapled (Gatekeeper passes)."
echo " DMG is signed but NOT separately notarized — use build_and_sign.sh"
echo " for the full belt-and-suspenders distribution build."
echo "================================================================="
