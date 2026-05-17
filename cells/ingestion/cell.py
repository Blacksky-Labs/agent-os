"""ingestion cell — v1.0.0 stub.

Pass-through. Real implementation will parse ``context.user_message``,
run lightweight deterministic extractors (regex for entities/emails/phones),
and dispatch parallel LLM extractors (sentiment, signals). See SPEC.md §5.
"""

from __future__ import annotations

from agentos.context import AgentContext


class Cell:
    name = "ingestion"
    version = "1.0.0"

    def __init__(self, config: dict):
        self.config = config or {}

    def init(self, config: dict) -> None:
        pass

    async def execute(self, context: AgentContext) -> AgentContext:
        return context

    async def teardown(self) -> None:
        pass
