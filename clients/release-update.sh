#!/usr/bin/env bash
#
# Cut a Sparkle update: package the current build as a DMG, EdDSA-sign it, and
# (re)generate the appcast. EdDSA signing is what secures Sparkle updates —
# notarization is NOT required for the update mechanism (it's only for clean
# Gatekeeper on first install; see UPDATES.md §4).
#
# One-time prereq (UPDATES.md §1): run Sparkle's generate_keys once so the private
# EdDSA key is in your keychain and SUPublicEDKey is set in project.yml.
#
# Env:
#   DOWNLOAD_URL_PREFIX  base URL for the <enclosure> in the appcast, e.g.
#                        https://updates.blacksky.org/skipper/  (prod) or
#                        http://localhost:8000/                 (local test)
#   GENERATE_APPCAST     path to Sparkle's generate_appcast (else auto-located)
set -euo pipefail
cd "$(dirname "$0")"   # clients/

REL="releases"; mkdir -p "$REL"

echo "==> 1/2  Package the current build into a DMG"
./build-dmg.sh >/dev/null
ls -1 "$REL"/*.dmg 2>/dev/null | tail -1 | sed 's/^/    /'

echo "==> 2/2  EdDSA-sign + (re)generate the appcast"
GEN="${GENERATE_APPCAST:-}"
[ -n "$GEN" ] || GEN=$(find build/dd/SourcePackages/artifacts -name generate_appcast -type f 2>/dev/null | head -1)
if [ -z "$GEN" ]; then
  echo "ERROR: generate_appcast not found."
  echo "  Build once (./build-local.sh) so SPM fetches Sparkle's tools, or set"
  echo "  GENERATE_APPCAST=/path/to/generate_appcast"
  exit 1
fi

if [ -n "${DOWNLOAD_URL_PREFIX:-}" ]; then
  "$GEN" --download-url-prefix "$DOWNLOAD_URL_PREFIX" "$REL"
else
  "$GEN" "$REL"
fi

echo ""
echo "Appcast → clients/$REL/appcast.xml"
echo "Upload everything in clients/$REL/ to the host your SUFeedURL points at."
echo "(Local test: ./serve-updates.sh, with SUFeedURL = http://localhost:8000/appcast.xml)"
