"""ingestion cell — v1.2.0 — the Sentiment Engine (deterministic pass).

Fast, pure, always-on: regex extraction of structured references — emails,
phones, URLs, @mentions, money, dates, and proper-noun entities. Writes
``context.entities`` and structured refs into ``context.extracted_signals``.
Runs in the pipeline because it's instant and feeds context-builder and the
``context_update`` hook live.

The LLM signal pass (intent / sentiment / topics) moved OUT of the pipeline into
the background ``signal_extract`` after_turn hook (v1.2.0) so it never blocks the
reply — it informs the *next* turn instead. That's where everyday tasks/errands
(common nouns the proper-noun pass can't catch) get captured.

Never raises (SPEC §4). Entity-agnostic.

See SPEC.md §5 and agentos-v1-spec.md §5.
"""

from __future__ import annotations

from agentos.context import AgentContext
from cells.ingestion.extractors import extract_all


class Cell:
    name = "ingestion"
    version = "1.2.0"

    def __init__(self, config: dict):
        self.config = config or {}

    def init(self, config: dict) -> None:
        pass

    async def execute(self, context: AgentContext) -> AgentContext:
        try:
            det = extract_all(context.user_message or "")
            context.entities = det.pop("entities", [])
            for key, value in det.items():
                if value:
                    context.extracted_signals[key] = value
        except Exception as e:  # pragma: no cover — defensive, must never raise
            context.cell_errors[self.name] = f"deterministic: {type(e).__name__}: {e}"
        return context

    async def teardown(self) -> None:
        pass
