#!/usr/bin/env bash
#
# Assemble the embedded CPython "home" for iOS from Python-Apple-support's xcframework:
# the pure-Python stdlib + the device (arm64) binary modules (lib-dynload, incl. _sqlite3).
# Run once after downloading Python-Apple-support (IOS_BUILD.md §2). At runtime PythonKernel
# sets PYTHONHOME to this folder, so the interpreter finds lib/python3.13.
set -euo pipefail
cd "$(dirname "$0")"   # clients/

XC="Frameworks/Python.xcframework"
[ -d "$XC" ] || { echo "ERROR: $XC not found — download Python-Apple-support first (IOS_BUILD.md §2)"; exit 1; }

HOME_DIR="AgentOSiOS/Resources/python"
DEST="$HOME_DIR/lib/python3.13"
echo "==> assembling CPython home → $HOME_DIR"
rm -rf "$HOME_DIR"; mkdir -p "$DEST"

# 1) pure-Python stdlib (shared across slices)
cp -R "$XC/lib/python3.13/." "$DEST/"
# 2) device arm64 binary modules (the compiled .so extensions, including _sqlite3)
cp -R "$XC/ios-arm64/lib-arm64/python3.13/lib-dynload" "$DEST/"
# 3) platform sysconfig data, if present (some stdlib paths look for it)
[ -d "$XC/ios-arm64/platform-config" ] && cp -R "$XC/ios-arm64/platform-config/." "$DEST/" 2>/dev/null || true

# Trim to keep the bundle lean — drop the stdlib test suites + caches.
find "$HOME_DIR" -type d \( -name "__pycache__" -o -name "test" -o -name "tests" -o -name "idlelib" -o -name "turtledemo" \) \
  -prune -exec rm -rf {} + 2>/dev/null || true

echo "==> home assembled: $(du -sh "$HOME_DIR" 2>/dev/null | cut -f1)"
echo "    _sqlite3 present: $(ls "$DEST/lib-dynload/"_sqlite3* 2>/dev/null | wc -l | tr -d ' ')"
