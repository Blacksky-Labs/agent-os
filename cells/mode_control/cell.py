"""mode-control cell — v1.0.0 stub.

Reads ``context.mode`` and the persona's ``modes`` block; writes the
matching mode constraints onto ``context.mode_constraints``.

See SPEC.md §5 — full implementation lands when first agent ships.
"""

from __future__ import annotations

from agentos.context import AgentContext


class Cell:
    name = "mode-control"
    version = "1.0.0"

    def __init__(self, config: dict):
        self.config = config or {}

    def init(self, config: dict) -> None:
        pass

    async def execute(self, context: AgentContext) -> AgentContext:
        persona_modes = (context.persona or {}).get("modes", {}) or {}
        constraints = persona_modes.get(context.mode, {}) or {}
        context.mode_constraints = dict(constraints)
        return context

    async def teardown(self) -> None:
        pass
