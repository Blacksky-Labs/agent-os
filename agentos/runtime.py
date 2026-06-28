"""In-process kernel runtime — run a turn through the pipeline without the HTTP layer.

This is the transport-agnostic core. The macOS app reaches the kernel over loopback HTTP
(FastAPI/uvicorn in ``main.py``); iOS embeds CPython and calls ``ao_call`` directly,
in-process. Both run the *same* pipeline — this module is the seam that makes that possible,
and it imports **no FastAPI**, so the iOS bundle can drop the web stack entirely.

See agentos-ios-build-plan.md §5 (Phase 1).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from agentos.config import ManifestError, load_manifest
from agentos.context import AgentContext
from agentos.hooks import HookDispatcher
from agentos.pipeline import Pipeline
from agentos.registry import Registry


class Kernel:
    """Owns the registry + per-agent pipeline cache and runs turns in-process."""

    def __init__(self, repo_root: str | Path = ".", registry: Registry | None = None):
        self.repo_root = Path(repo_root)
        self.registry = registry or Registry(self.repo_root / "cells.registry.yaml", kind="cells")
        self._pipelines: dict[str, Pipeline] = {}
        self._dispatchers: dict[str, HookDispatcher] = {}
        self._manifests: dict[str, dict] = {}

    def _pipeline(self, agent: str) -> tuple[Pipeline, HookDispatcher, dict]:
        if agent in self._pipelines:
            return self._pipelines[agent], self._dispatchers[agent], self._manifests[agent]

        manifest = load_manifest(agent, repo_root=self.repo_root)   # raises ManifestError

        # Honor live reasoning toggles (cells/hooks turned off in the config overlay).
        disabled_cells = set(manifest.get("_disabled_cells") or [])
        disabled_hooks = set(manifest.get("_disabled_hooks") or [])
        pm = manifest
        if disabled_cells:
            pm = {**manifest, "cells": [c for c in manifest.get("cells", [])
                                        if c.get("name") not in disabled_cells]}
        hooks_cfg = manifest.get("hooks", {}) or {}
        if disabled_hooks:
            hooks_cfg = {evt: [h for h in handlers if h.get("handler") not in disabled_hooks]
                         for evt, handlers in hooks_cfg.items()}

        pipeline = Pipeline(pm, self.registry)
        dispatcher = HookDispatcher(hooks_cfg)
        self._pipelines[agent] = pipeline
        self._dispatchers[agent] = dispatcher
        self._manifests[agent] = manifest
        return pipeline, dispatcher, manifest

    def reset(self, agent: str | None = None) -> None:
        """Drop cached pipeline(s) so the next turn rebuilds (e.g. after a config change)."""
        if agent is None:
            self._pipelines.clear(); self._dispatchers.clear(); self._manifests.clear()
        else:
            self._pipelines.pop(agent, None)
            self._dispatchers.pop(agent, None)
            self._manifests.pop(agent, None)

    async def run_turn(
        self,
        agent: str,
        message: str,
        *,
        session_id: str | None = None,
        mode: str = "web",
        user_id: str | None = None,
        run_hooks: bool = True,
    ) -> dict:
        """Run one turn end to end. Mirrors POST /chat, minus HTTP/BackgroundTasks —
        after_turn hooks run synchronously (iOS has no BackgroundTasks)."""
        pipeline, dispatcher, manifest = self._pipeline(agent)
        context = AgentContext(
            agent_name=agent,
            namespace=pipeline.namespace,
            session_id=session_id or "default",
            user_id=user_id,
            mode=mode,
            user_message=message,
            persona=manifest.get("_persona_data", {}),
            meta={
                "model": manifest.get("model", {}),
                "owner": manifest.get("owner"),
                "multi_user": bool(manifest.get("multi_user", False)),
            },
        )
        await dispatcher.fire("before_turn", context)
        t0 = time.perf_counter()
        context = await pipeline.run(context)
        context.meta["turn_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if run_hooks:
            await dispatcher.fire("after_turn", context)
        return {
            "response": context.response,
            "turn_id": context.turn_id,
            "namespace": context.namespace,
            "session_id": context.session_id,
            "cell_errors": context.cell_errors,
            "usage": context.meta.get("last_usage"),
        }


# --- C-ABI-shaped entry for embedded hosts (iOS) ---------------------------------

_KERNEL: Kernel | None = None


def ao_init(repo_root: str = ".", data_dir: str | None = None) -> None:
    """Initialize the singleton kernel. Swift calls this once at launch and passes the iOS
    sandbox container as ``data_dir`` so memory survives app updates (AGENTOS_DATA_DIR).

    Named ``ao_init`` (not ``init``) so PythonKit doesn't read it as a Swift initializer."""
    global _KERNEL
    if data_dir:
        os.environ["AGENTOS_DATA_DIR"] = data_dir
    _KERNEL = Kernel(repo_root)


def ao_call(json_input: str) -> str:
    """JSON in, JSON out — the single function the Swift C-ABI bridge calls per turn.
    Input: ``{"agent","message","session_id"?,"mode"?,"user_id"?}``. Synchronous; never raises."""
    try:
        payload = json.loads(json_input or "{}")
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"bad json: {e}"})
    if _KERNEL is None:
        return json.dumps({"error": "kernel not initialized — call ao_init() first"})
    agent = payload.get("agent")
    if not agent:
        return json.dumps({"error": "missing 'agent'"})
    try:
        result = asyncio.run(_KERNEL.run_turn(
            agent,
            payload.get("message", ""),
            session_id=payload.get("session_id"),
            mode=payload.get("mode", "web"),
            user_id=payload.get("user_id"),
        ))
        return json.dumps(result)
    except ManifestError as e:
        return json.dumps({"error": f"manifest: {e}"})
    except Exception as e:                              # never let an exception cross the C ABI
        return json.dumps({"error": f"{type(e).__name__}: {e}"})
