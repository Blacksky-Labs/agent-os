"""Structured logging.

v0.1: emits JSON events to stdout. Sink configurable in v0.2.
See SPEC.md §11.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any


def log_event(
    kind: str,
    namespace: str,
    turn_id: str,
    duration_ms: int | None = None,
    error: str | None = None,
    **extra: Any,
) -> None:
    """Emit a structured event to stdout as JSON.

    Args:
        kind: ``"cell"`` | ``"tool"`` | ``"hook"`` | ``"kernel"``
        namespace: the agent's namespace (use ``"*"`` for kernel-level events)
        turn_id: per-turn identifier (use ``"-"`` for startup/shutdown events)
        duration_ms: how long the action took
        error: error message if the action failed
        **extra: kind-specific fields (cell, tool, event, handler, ...)

    Rules (SPEC §11):
        - Never log secrets, tokens, full prompts, or PII at default verbosity.
        - ``args_hash`` is a SHA-256 of canonical JSON of args, not the args.
        - Every event carries ``turn_id`` so a turn can be reconstructed.
    """
    event: dict[str, Any] = {
        "ts": _iso_now(),
        "kind": kind,
        "namespace": namespace,
        "turn_id": turn_id,
    }
    if duration_ms is not None:
        event["duration_ms"] = duration_ms
    if error is not None:
        event["error"] = error
    event.update(extra)
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def _iso_now() -> str:
    """RFC 3339 UTC timestamp with millisecond precision."""
    t = time.time()
    ms = int((t - int(t)) * 1000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{ms:03d}Z"
