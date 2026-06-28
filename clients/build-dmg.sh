#!/usr/bin/env bash
#
# Quick DMG of the current local build — drag-to-Applications, ad-hoc signed (no
# notarization). Good for testing on another Mac or handing to a tester. For a
# clean-Gatekeeper notarized DMG, see UPDATES.md §4 / build-macos.sh.
set -euo pipefail
cd "$(dirname "$0")"   # clients/

APP="build/dd/Build/Products/Debug/Skipper.app"
[ -d "$APP" ] || { echo "Build the app first:  ./build-local.sh"; exit 1; }

VER=$(/usr/libexec/PlistBuddy -c "Print CFBundleShortVersionString" "$APP/Contents/Info.plist" 2>/dev/null || echo "0.0.0")
REL="releases"; mkdir -p "$REL"
DMG="$REL/Skipper-$VER.dmg"; rm -f "$DMG"

STAGE="$(mktemp -d)/dmg"; mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"          # drag-to-install target

hdiutil create -volname "Skipper $VER" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$(dirname "$STAGE")"

echo "DMG → clients/$DMG"
echo "Drag Skipper.app onto Applications. (Ad-hoc build: first open may need right-click → Open,"
echo "or:  xattr -dr com.apple.quarantine /Applications/Skipper.app)"
open "$REL"
