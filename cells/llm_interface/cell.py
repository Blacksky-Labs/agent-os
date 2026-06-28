"""llm-interface cell — v1.1.0.

Calls the configured model via ``agentos.llm.chat_completion`` — a thin
OpenAI-compatible client (Ollama, Together, OpenAI, …). Reads
``context.assembled_prompt`` and the manifest's ``model`` block
(``context.meta["model"]``); writes ``context.response`` and token usage to
``context.meta["last_usage"]``.

v1.1.0 vs v1.0.0:
    - Replaced LiteLLM with the in-house OpenAI-compatible client. Same contract,
      same model config (provider/name/api_base/temperature/max_tokens), far
      lighter footprint — bundles cleanly for the macOS app, no lazy-import sprawl.

Errors recorded to ``context.cell_errors`` per SPEC §4; never raises. Streaming
and the tool-use loop remain deferred.

See SPEC.md §5 (llm-interface contract).
"""

from __future__ import annotations

from agentos.context import AgentContext
from agentos.llm import chat_completion


DEFAULT_TIMEOUT_S = 60.0


class Cell:
    name = "llm-interface"
    version = "1.1.0"

    def __init__(self, config: dict):
        self.config = config or {}

    def init(self, config: dict) -> None:
        pass

    async def execute(self, context: AgentContext) -> AgentContext:
        model_cfg = context.meta.get("model", {}) or {}

        if not model_cfg.get("name"):
            context.cell_errors[self.name] = "manifest.model.name missing — nothing to call"
            return context
        if not context.assembled_prompt:
            context.cell_errors[self.name] = (
                "context.assembled_prompt empty — did context-builder run?"
            )
            return context

        try:
            result = await chat_completion(
                model_cfg,
                context.assembled_prompt,
                timeout=model_cfg.get("timeout", DEFAULT_TIMEOUT_S),
            )
            context.response = result.get("content")
            if result.get("usage"):
                context.meta["last_usage"] = result["usage"]
        except Exception as e:
            context.cell_errors[self.name] = f"{type(e).__name__}: {e}"
            context.response = None

        return context

    async def teardown(self) -> None:
        pass
