#!/usr/bin/env bash
#
# Publish a Skipper update under the Blacksky-Labs org — entirely on GitHub, no
# separate server:
#
#   build DMG -> EdDSA-sign + appcast (enclosure -> GitHub Release asset) ->
#   commit docs/appcast.xml -> push main -> push tag v<version> ->
#   create GitHub Release + upload the DMG.
#
# Pushing the v<version> tag triggers .github/workflows/deploy-pages.yml, which
# serves docs/appcast.xml from GitHub Pages — that URL is your SUFeedURL.
#
# Run on your Mac AFTER ./build-local.sh (the app must be built and the Sparkle
# EdDSA key must be in your Keychain — UPDATES.md §1).
#
# One-time prereqs:
#   - gh CLI authed:            brew install gh && gh auth login   (repo scope)
#   - Pages enabled:            repo Settings -> Pages -> Source: GitHub Actions
#   - repo is PUBLIC            (Sparkle fetches the asset + feed without auth;
#                               for a private repo, host the feed elsewhere)
#   - SUFeedURL in project.yml  -> https://blacksky-labs.github.io/agent-os/appcast.xml
set -euo pipefail
cd "$(dirname "$0")"            # clients/
ROOT="$(cd .. && pwd)"
REPO="${REPO:-Blacksky-Labs/agent-os}"
REL="releases"

command -v gh >/dev/null || { echo "ERROR: gh CLI not found — brew install gh && gh auth login"; exit 1; }

# Sparkle's appcast signer ships with the Sparkle SPM package after a build.
GEN="${GENERATE_APPCAST:-}"
[ -n "$GEN" ] || GEN=$(find build/dd/SourcePackages/artifacts -name generate_appcast -type f 2>/dev/null | head -1)
[ -n "$GEN" ] || { echo "ERROR: generate_appcast not found — run ./build-local.sh once (fetches Sparkle), or set GENERATE_APPCAST"; exit 1; }

# Sparkle can only fetch a Release asset + feed from a PUBLIC repo without auth.
VIS=$(gh repo view "$REPO" --json visibility -q .visibility 2>/dev/null || echo UNKNOWN)
if [ "$VIS" != "PUBLIC" ]; then
  echo "WARNING: $REPO visibility is '$VIS'. Sparkle needs PUBLIC asset + feed URLs."
  echo "         Make the repo public, or host the feed on updates.blacksky.org instead."
  read -r -p "Continue anyway? [y/N] " ans; [ "${ans:-N}" = "y" ] || exit 1
fi

echo "==> 1/5  Package DMG"
./build-dmg.sh >/dev/null
DMG=$(ls -t "$REL"/Skipper-*.dmg 2>/dev/null | head -1)
{ [ -n "$DMG" ] && [ -f "$DMG" ]; } || { echo "ERROR: no DMG in $REL/ — run ./build-local.sh first"; exit 1; }
VERSION=$(basename "$DMG" .dmg | sed 's/^Skipper-//')
TAG="v$VERSION"
PREFIX="https://github.com/$REPO/releases/download/$TAG/"
echo "    $DMG  ->  $TAG"

echo "==> 2/5  EdDSA-sign + build single-item appcast (enclosure -> release asset)"
# Sign only THIS version in an isolated dir so the enclosure URL gets exactly one
# (correct) per-tag prefix — generate_appcast applies one prefix to every DMG.
SIGN_DIR=$(mktemp -d)
cp "$DMG" "$SIGN_DIR/"
"$GEN" --download-url-prefix "$PREFIX" "$SIGN_DIR"
mkdir -p "$ROOT/docs"
cp "$SIGN_DIR/appcast.xml" "$ROOT/docs/appcast.xml"
rm -rf "$SIGN_DIR"

echo "==> 3/5  Commit appcast + push main"
(
  cd "$ROOT"
  git add docs/appcast.xml
  git commit -m "Publish appcast for $VERSION" || echo "    (appcast unchanged — nothing to commit)"
  git push origin main
)

echo "==> 4/5  Tag $TAG + push (triggers the Pages deploy workflow)"
(
  cd "$ROOT"
  git tag -f "$TAG"
  git push -f origin "$TAG"
)

echo "==> 5/5  Create GitHub Release + upload DMG"
if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  gh release upload "$TAG" "$DMG" --repo "$REPO" --clobber
else
  gh release create "$TAG" "$DMG" --repo "$REPO" --verify-tag \
    --title "Skipper $VERSION" --notes "Skipper $VERSION. Auto-updates via Sparkle."
fi

echo ""
echo "Published $TAG."
echo "  Release: https://github.com/$REPO/releases/tag/$TAG"
echo "  Feed:    https://blacksky-labs.github.io/agent-os/appcast.xml"
echo "Set SUFeedURL to that feed URL (already done in project.yml) and rebuild so"
echo "installed copies check the org feed from this version on."
