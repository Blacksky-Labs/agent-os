"""llm-interface cell — v1.0.0 stub.

Returns a placeholder string so ``/chat`` produces a visible response without
LiteLLM wired up yet. Real LiteLLM integration lands in MVP step 5.

See SPEC.md §5 — full implementation will read ``context.assembled_prompt``
and ``context.meta['model']`` (provider, name, temperature, max_tokens), run
the tool-use loop, write ``response`` / ``tool_calls`` / ``tool_results``.
"""

from __future__ import annotations

from agentos.context import AgentContext


class Cell:
    name = "llm-interface"
    version = "1.0.0"

    def __init__(self, config: dict):
        self.config = config or {}

    def init(self, config: dict) -> None:
        pass

    async def execute(self, context: AgentContext) -> AgentContext:
        model = context.meta.get("model", {}) or {}
        model_name = model.get("name", "(unconfigured)")
        provider = model.get("provider", "?")
        context.response = (
            f"hello from {context.agent_name} "
            f"(namespace={context.namespace}, mode={context.mode}, "
            f"provider={provider}, model={model_name}). "
            f"you said: {context.user_message!r}. "
            f"this is a v0.1 stub — LiteLLM lands in MVP step 5."
        )
        return context

    async def teardown(self) -> None:
        pass
