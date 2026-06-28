"""A cell that always raises in execute(), to test graceful degradation."""

from __future__ import annotations

from agentos.context import AgentContext


class Cell:
    name = "boom"
    version = "1.0.0"

    def __init__(self, config: dict):
        self.config = config or {}

    def init(self, config: dict) -> None:
        pass

    async def execute(self, context: AgentContext) -> AgentContext:
        raise RuntimeError("kaboom")

    async def teardown(self) -> None:
        pass
