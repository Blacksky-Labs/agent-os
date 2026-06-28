"""after_turn hook — update the Context Engine thread profile.

Consumes what the Sentiment Engine produced this turn — ``context.entities``,
the optional ``signals.topics``, and ``context.sentiment`` — and folds it into
the per-user thread profile: recurrence (mention counts) and emotional charge.

A side effect, so it lives in a hook, not a cell (SPEC §7). Entity-agnostic:
any entity that subscribes ``after_turn → context_update`` gets thread tracking.
Failure here is caught by the dispatcher and never blocks the response.
"""

from __future__ import annotations

from agentos.context import AgentContext
from cells.memory.profile import profile_key, update_threads
from cells.memory.store import init_store


def _charge_from_sentiment(sentiment) -> float:
    """Map sentiment to a 0–1 charge. Uses emotional_charge if present, else
    score; negative sentiment is weighted a touch heavier (it tends to matter)."""
    if not isinstance(sentiment, dict):
        return 0.0
    raw = sentiment.get("emotional_charge", sentiment.get("score"))
    if not isinstance(raw, (int, float)):
        return 0.0
    charge = max(0.0, min(1.0, float(raw) / 100.0))
    if str(sentiment.get("label", "")).lower() in ("negative", "distress"):
        charge = min(1.0, charge + 0.25)
    return charge


async def handle(context: AgentContext, payload: dict, config: dict) -> None:
    items: list[tuple[str, str]] = [(e, "entity") for e in (context.entities or [])]
    # Topics are owned by the background signal_extract hook (they need the LLM
    # pass); this hook owns the deterministic entities.
    if not items:
        return

    db_path = await init_store(context.namespace)
    await update_threads(
        db_path, profile_key(context), items, charge=_charge_from_sentiment(context.sentiment)
    )
