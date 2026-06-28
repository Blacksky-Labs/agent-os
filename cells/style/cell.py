"""style cell — v1.0.0 — the first MoE expert (presentation / refinement).

A post-generation expert: reads ``context.response`` and normalizes its
presentation to the entity's style. v0 is **deterministic** (no model): it
normalizes list markers (``*``, ``•``, ``1.`` …) at line-start to a consistent
``- `` bullet, so lists render cleanly and consistently.

Pairs with an entity's persona nudge ("show lists as bullets"): the model
produces the list, this expert guarantees the formatting.

A future ``mode: model`` runs a small, fast style model (see
agentos-moe-design.md) for richer reformatting — prose→bullets, tone, length.
Per the MoE principle, experts bring their OWN (smaller) model via config and
call it through ``agentos.llm.chat_completion``; the entity's main model is
reserved for the primary response.

Content-agnostic — works for any entity. Never raises (SPEC §4).
"""

from __future__ import annotations

import re

from agentos.context import AgentContext

# Line-start list markers we normalize to "- " (excludes "-", already the target).
_MARKER_RE = re.compile(r"^(\s*)(?:[*•·‣▪◦]|\d+[.)])\s+")


class Cell:
    name = "style"
    version = "1.0.0"

    def __init__(self, config: dict):
        self.config = config or {}
        self.normalize_bullets = bool(self.config.get("normalize_bullets", True))

    def init(self, config: dict) -> None:
        pass

    async def execute(self, context: AgentContext) -> AgentContext:
        try:
            if self.normalize_bullets and context.response:
                context.response = _normalize_bullets(context.response)
        except Exception as e:  # pragma: no cover — must never raise
            context.cell_errors[self.name] = f"{type(e).__name__}: {e}"
        return context

    async def teardown(self) -> None:
        pass


def _normalize_bullets(text: str) -> str:
    out: list[str] = []
    for line in text.split("\n"):
        m = _MARKER_RE.match(line)
        out.append(f"{m.group(1)}- {line[m.end():]}" if m else line)
    return "\n".join(out)
