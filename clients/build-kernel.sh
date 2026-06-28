#!/usr/bin/env bash
#
# Compile the AgentOS kernel to a standalone binary (Nuitka). Shared by the local
# build (build-local.sh) and the release build (build-macos.sh). Runs on macOS.
#
# Output: build/nuitka/__main__.dist/  — the binary (__main__.bin) + its libs +
# the bundled data (cells.registry.yaml, manifests/, personas/, dashboards/). LiteLLM is gone
# (replaced by agentos/llm.py over stdlib), so there's no provider lib to bundle;
# chromadb/onnxruntime are skipped because Skipper has no retrieval cell.
#
# Prereqs:  pip install -e .  &&  pip install nuitka
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Use $PYTHON if set, else a repo venv if present, else whatever 'python' resolves to.
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if [ -x "$REPO_ROOT/venv/bin/python" ]; then PY="$REPO_ROOT/venv/bin/python"
  elif [ -x "$REPO_ROOT/.venv/bin/python" ]; then PY="$REPO_ROOT/.venv/bin/python"
  else PY="python"; fi
fi

if ! "$PY" -m nuitka --version >/dev/null 2>&1; then
  echo "ERROR: 'nuitka' not found in this Python: $("$PY" -c 'import sys;print(sys.executable)' 2>/dev/null || echo "$PY")"
  echo "Use the env where you ran 'pip install -e . && pip install nuitka', e.g.:"
  echo "    source venv/bin/activate && ./clients/build-local.sh"
  echo "  or:  PYTHON=/path/to/venv/bin/python ./clients/build-local.sh"
  exit 1
fi

# Clear any prior output first. A plain 'rm -rf' can fail with "Directory not empty"
# if a shell is parked inside build/nuitka, or race with ccache/Spotlight on a fresh
# tree. Renaming is atomic and frees the path even when a shell sits inside it; the
# best-effort delete of the moved-aside copy can fail harmlessly.
if [ -d build/nuitka ]; then
  _old="build/nuitka.old.$$"
  if mv build/nuitka "$_old" 2>/dev/null; then
    rm -rf "$_old" 2>/dev/null || echo "    (note: leftover $_old couldn't be fully removed — harmless)"
  else
    rm -rf build/nuitka 2>/dev/null || {
      echo "ERROR: couldn't clear build/nuitka. A Terminal is probably parked inside it —"
      echo "       run 'cd ~' in any shell sitting in build/nuitka/__main__.dist, then retry."
      exit 1
    }
  fi
fi

# Don't ship Finder metadata inside the bundled data dirs.
find dashboards manifests personas -name '.DS_Store' -delete 2>/dev/null || true

echo "==> Compiling kernel (Nuitka standalone) from $REPO_ROOT  [$PY]"
"$PY" -m nuitka \
  --standalone --assume-yes-for-downloads \
  --include-package=agentos --include-package=cells --include-package=hooks \
  --nofollow-import-to=chromadb --nofollow-import-to=onnxruntime \
  --include-data-files=cells.registry.yaml=cells.registry.yaml \
  --include-data-dir=manifests=manifests \
  --include-data-dir=personas=personas \
  --include-data-dir=dashboards=dashboards \
  --output-dir=build/nuitka \
  agentos/__main__.py

echo "==> kernel → build/nuitka/__main__.dist (binary: __main__.bin → renamed to 'agentos' at embed time)"
