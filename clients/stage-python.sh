#!/usr/bin/env bash
#
# Stage the AgentOS Python into the iOS app bundle resources. Only what the in-process
# runtime (agentos/runtime.py → ao_call) needs — the HTTP layer (FastAPI/uvicorn/pydantic)
# and the dashboard UI modules are dropped. `pyyaml` is the sole third-party dependency;
# install it as an iOS wheel separately (IOS_BUILD.md §2).
#
# Run as a build step before each iOS build (the "edit Python → redeploy" loop).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$REPO_ROOT/clients/AgentOSiOS/Resources/app}"

echo "==> staging Python → $DEST"
rm -rf "$DEST"; mkdir -p "$DEST"

# `dashboards/` rides along as static files so a future iOS WKWebView bridge can
# load a pack's index.html directly (the packs are pure HTML/JS — no platform code).
# iOS has no HTTP layer (the FastAPI routes are dropped below), so the pack's API
# calls will need an injected JS↔ao_call bridge when the iOS dashboard is wired up.
for item in agentos cells hooks manifests personas dashboards cells.registry.yaml; do
  cp -R "$REPO_ROOT/$item" "$DEST/"
done

# Vendor PyYAML as pure Python (our only third-party dep — works without its C extension,
# so no iOS binary wheel needed). Copy the installed `yaml/` package, minus any compiled bits.
PY="${PYTHON:-python3}"
YAML_DIR="$("$PY" -c 'import os,yaml; print(os.path.dirname(yaml.__file__))' 2>/dev/null || true)"
if [ -n "$YAML_DIR" ] && [ -d "$YAML_DIR" ]; then
  cp -R "$YAML_DIR" "$DEST/"
  rm -f "$DEST"/yaml/_yaml*.so "$DEST"/yaml/*.dylib 2>/dev/null || true
else
  echo "warning: PyYAML not found in '$PY' — run 'pip install pyyaml' or vendor yaml/ manually"
fi

# Drop the HTTP/CLI/UI modules — never imported by the in-process runtime, and they
# pull FastAPI/uvicorn/pydantic which we don't bundle for iOS.
for mod in main.py __main__.py cli.py ui.py dashboard_ui.py config_ui.py dbexplorer_ui.py analytics.py; do
  rm -f "$DEST/agentos/$mod"
done

# Prune caches + tests.
find "$DEST" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "$DEST" -type d -name "tests" -prune -exec rm -rf {} + 2>/dev/null || true

echo "==> staged: $(du -sh "$DEST" 2>/dev/null | cut -f1) at $DEST"
echo "    Add this folder to the AgentOSiOS target as a folder reference, and make sure"
echo "    pyyaml is installed into the embedded Python (IOS_BUILD.md §2)."
