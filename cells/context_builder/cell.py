"""context-builder cell — v1.0.0 stub.

Minimal real-but-stub behavior: assembles a tiny ``assembled_prompt`` from
the persona mission and the user message so the LLM cell has something to
look at. Real implementation will assemble persona + RAG + history + signals
into a full role-tagged message list. See SPEC.md §5.
"""

from __future__ import annotations

from agentos.context import AgentContext


class Cell:
    name = "context-builder"
    version = "1.0.0"

    def __init__(self, config: dict):
        self.config = config or {}

    def init(self, config: dict) -> None:
        pass

    async def execute(self, context: AgentContext) -> AgentContext:
        mission = (context.persona or {}).get("mission") or "You are a helpful assistant."
        context.assembled_prompt = [
            {"role": "system", "content": mission},
            {"role": "user", "content": context.user_message},
        ]
        return context

    async def teardown(self) -> None:
        pass
