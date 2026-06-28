#!/usr/bin/env bash
#
# Serve releases/ over http://localhost:8000 so you can test the whole Sparkle update
# flow locally — point SUFeedURL at http://localhost:8000/appcast.xml in project.yml,
# rebuild, then use "Check for Updates…" in the app. (UPDATES.md §2.)
set -euo pipefail
cd "$(dirname "$0")/releases" 2>/dev/null || { echo "No releases/ yet — run ./release-update.sh first"; exit 1; }
echo "Serving $(pwd)"
echo "  appcast: http://localhost:8000/appcast.xml   (Ctrl-C to stop)"
python3 -m http.server 8000
