"""after_turn hook — persist this turn's latency + token usage.

Reads ``context.meta['turn_ms']`` (set by the /chat handler around the pipeline)
and ``context.meta['last_usage']`` (set by the llm-interface cell), and writes a
row to the per-namespace ``turn_metrics`` table. A side effect → a hook (SPEC §7).
Entity-agnostic; failure here never blocks the response.
"""

from __future__ import annotations

from agentos.context import AgentContext
from cells.memory.metrics import record_turn
from cells.memory.store import init_store


async def handle(context: AgentContext, payload: dict, config: dict) -> None:
    db_path = await init_store(context.namespace)
    model = (context.meta.get("model") or {}).get("name")
    await record_turn(
        db_path,
        context.session_id,
        context.turn_id,
        context.meta.get("turn_ms"),
        context.meta.get("last_usage"),
        model,
    )
