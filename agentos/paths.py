"""Where AgentOS keeps mutable state.

Default: ``./data`` under the repo (dev). In a packaged macOS app, set
``AGENTOS_DATA_DIR`` (e.g. ``~/Library/Application Support/Skipper``) so memory,
config overlays, and vector stores live **outside** the app bundle and survive
software updates — the cornerstone of "updates don't forget."

See macos-packaging-plan.md §0/§6.
"""

from __future__ import annotations

import os
from pathlib import Path


def data_root(repo_root: Path | str = ".") -> Path:
    """Root of all mutable state. ``AGENTOS_DATA_DIR`` overrides the repo's ``./data``."""
    env = os.getenv("AGENTOS_DATA_DIR")
    if env:
        return Path(env).expanduser()
    return Path(repo_root) / "data"


def namespace_dir(namespace: str, repo_root: Path | str = ".") -> Path:
    """Per-entity state directory: ``<data_root>/<namespace>/``."""
    return data_root(repo_root) / namespace
