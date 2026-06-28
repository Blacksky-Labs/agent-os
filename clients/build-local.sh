#!/usr/bin/env bash
#
# Local runnable Skipper.app — no notarization, no Developer ID needed.
# Compiles the kernel, generates + builds the Xcode app, embeds the kernel,
# ad-hoc signs the whole bundle, and launches it. For distribution use build-macos.sh.
#
# Prereqs:
#   brew install xcodegen
#   pip install -e . && pip install nuitka
#   Ollama running with the model pulled:  ollama pull gemma4:e4b
set -euo pipefail

cd "$(dirname "$0")"   # clients/
command -v xcodegen >/dev/null || { echo "Need XcodeGen:  brew install xcodegen"; exit 1; }

echo "==> 1/4  Compile the kernel (always, so it's never stale — SKIP_KERNEL=1 to reuse)"
if [ "${SKIP_KERNEL:-0}" = "1" ] && [ -d ../build/nuitka/__main__.dist ]; then
  echo "    (skipped — reusing existing build/nuitka/__main__.dist)"
else
  ./build-kernel.sh   # handles its own robust cleanup of build/nuitka
fi

echo "==> 2/4  Generate the Xcode project + build (unsigned)"
xcodegen generate
xcodebuild -project Skipper.xcodeproj -scheme Skipper -configuration Debug \
  -derivedDataPath build/dd CODE_SIGNING_ALLOWED=NO build | tail -8

APP="build/dd/Build/Products/Debug/Skipper.app"
[ -d "$APP" ] || APP="$(find build/dd/Build/Products -maxdepth 2 -name Skipper.app 2>/dev/null | head -1)"
[ -d "$APP" ] || { echo "Build failed: Skipper.app not found"; exit 1; }

echo "==> 3/4  Embed the kernel into $APP"
DEST="$APP/Contents/Resources/kernel"; rm -rf "$DEST"; mkdir -p "$DEST"
cp -R ../build/nuitka/__main__.dist/. "$DEST/"
[ -f "$DEST/__main__.bin" ] && mv "$DEST/__main__.bin" "$DEST/agentos"
chmod +x "$DEST/agentos"

echo "==> 4/4  Ad-hoc sign (local run) + launch"
codesign --force --deep --sign - "$APP"
echo ""
echo "Built: clients/$APP"
if [ "${NO_LAUNCH:-0}" = "1" ]; then
  echo "(NO_LAUNCH=1 — built but not opened)"
else
  echo "Launching… (needs Ollama running with gemma4:e4b)"
  open "$APP"
fi
