"""A trivial pass-through cell used by pipeline/registry tests.

Records that it ran by appending its name to ``context.meta['ran']`` so
tests can assert ordering.
"""

from __future__ import annotations

from agentos.context import AgentContext


class Cell:
    name = "echo"
    version = "1.0.0"

    def __init__(self, config: dict):
        self.config = config or {}
        self.inited_with: dict | None = None
        self.torn_down = False

    def init(self, config: dict) -> None:
        self.inited_with = config

    async def execute(self, context: AgentContext) -> AgentContext:
        context.meta.setdefault("ran", []).append(self.name)
        return context

    async def teardown(self) -> None:
        self.torn_down = True
