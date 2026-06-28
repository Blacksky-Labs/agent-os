#!/usr/bin/env bash
#
# Build + release Skipper.app — direct download, Sparkle auto-update.
# Runs on macOS. Compiles the kernel, assembles it into the .app Xcode built,
# signs, notarizes, and cuts a Sparkle release. This is a starting point — the
# Nuitka + notarization step in particular will need iteration on your machine.
#
# One-time prereqs:
#   - Xcode + command line tools
#   - pip install -e .   &&   pip install nuitka
#   - Sparkle release tools (generate_appcast, sign_update, generate_keys)
#   - Apple "Developer ID Application" certificate in your keychain
#   - notarytool profile:  xcrun notarytool store-credentials skipper-notary \
#                            --apple-id you@blacksky.com --team-id TEAMID --password <app-specific>
#   - EdDSA keys:  ./Sparkle/bin/generate_keys   (put the printed public key in Info.plist → SUPublicEDKey)
#
set -euo pipefail

APP="${1:?Usage: build-macos.sh /path/to/Skipper.app   (the .app Xcode built)}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${VERSION:-0.1.0}"
DEV_ID="${DEV_ID:-Developer ID Application: Blacksky LLC (TEAMID)}"
NOTARY_PROFILE="${NOTARY_PROFILE:-skipper-notary}"
SPARKLE_BIN="${SPARKLE_BIN:-$REPO_ROOT/clients/Sparkle/bin}"
RELEASES_DIR="${RELEASES_DIR:-$REPO_ROOT/clients/releases}"
ENTITLEMENTS="$REPO_ROOT/clients/AgentOSMac/Skipper.entitlements"
KERNEL_DST="$APP/Contents/Resources/kernel"

echo "==> 1/6  Compile the kernel (Nuitka standalone) — IP-protected, no Python install needed"
"$REPO_ROOT/clients/build-kernel.sh"
# → build/nuitka/__main__.dist/ (binary "__main__.bin" + libs + the data files).
# Shared with the local build (build-local.sh) so the compile is defined in one place.

echo "==> 2/6  Assemble kernel into the app bundle"
rm -rf "$KERNEL_DST"; mkdir -p "$KERNEL_DST"
cp -R build/nuitka/__main__.dist/. "$KERNEL_DST/"
mv "$KERNEL_DST/__main__.bin" "$KERNEL_DST/agentos"  # Nuitka names it __main__.bin on macOS; KernelController launches 'agentos'

echo "==> 3/6  Code-sign — nested kernel binaries first, then the app (hardened runtime)"
find "$KERNEL_DST" -type f \( -name "*.dylib" -o -name "*.so" -o -perm +111 \) -print0 \
  | xargs -0 -I{} codesign --force --timestamp --options runtime \
      --entitlements "$ENTITLEMENTS" --sign "$DEV_ID" "{}"
codesign --force --deep --timestamp --options runtime \
  --entitlements "$ENTITLEMENTS" --sign "$DEV_ID" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

echo "==> 4/6  Package DMG"
mkdir -p "$RELEASES_DIR"
DMG="$RELEASES_DIR/Skipper-$VERSION.dmg"; rm -f "$DMG"
hdiutil create -volname "Skipper" -srcfolder "$APP" -ov -format UDZO "$DMG"

echo "==> 5/6  Notarize + staple (Gatekeeper clears it on direct download)"
xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
xcrun stapler staple "$DMG"

echo "==> 6/6  EdDSA-sign + (re)generate the Sparkle appcast"
"$SPARKLE_BIN/generate_appcast" "$RELEASES_DIR"
# Upload everything in $RELEASES_DIR (the DMG + appcast.xml) to the host that
# Info.plist's SUFeedURL points at. Sparkle verifies EdDSA + Apple signature
# before installing, then relaunches → `resume` → nothing forgotten.

echo "Done → $DMG  +  $RELEASES_DIR/appcast.xml"
