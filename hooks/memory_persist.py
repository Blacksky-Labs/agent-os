"""after_turn hook — persist the just-completed turn pair.

Writes the user message (always, if present) and the assistant response
(when the LLM produced one) to the same SQLite the memory cell reads from.
Lives outside the cell pipeline because it's a side effect — SPEC §7.

Handler signature contract:
    async def handle(context, payload, config) -> None

Failure inside ``handle`` is caught by the dispatcher and logged, but
never propagates to the user-facing response.
"""

from __future__ import annotations

from agentos.context import AgentContext
from cells.memory.store import append_turn, init_store


async def handle(context: AgentContext, payload: dict, config: dict) -> None:
    """Persist the user turn and the assistant turn (if produced)."""
    db_path = await init_store(context.namespace)

    # Always persist the user's turn — record-of-utterance even if the
    # pipeline failed downstream.
    if context.user_message:
        await append_turn(
            db_path,
            context.session_id,
            context.turn_id,
            "user",
            context.user_message,
        )

    # Only persist the assistant turn if the LLM produced one.
    if context.response:
        await append_turn(
            db_path,
            context.session_id,
            context.turn_id,
            "assistant",
            context.response,
        )
