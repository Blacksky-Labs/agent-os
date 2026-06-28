"""Tests for the ingestion cell — deterministic pass only (no model needed).
The LLM signal pass lives in the background signal_extract hook now."""

from agentos.context import AgentContext
from cells.ingestion.cell import Cell


def _ctx(msg: str) -> AgentContext:
    return AgentContext(
        agent_name="skipper", namespace="skipper", session_id="s1", user_message=msg
    )


async def test_deterministic_fills_entities_and_signals():
    cell = Cell({})
    ctx = await cell.execute(
        _ctx("Email mario@blacksky.com about KNowGov and AgentOS, budget $20-25k by Q3")
    )
    assert "mario@blacksky.com" in ctx.extracted_signals["emails"]
    assert "AgentOS" in ctx.entities and "KNowGov" in ctx.entities
    assert ctx.extracted_signals.get("money")
    assert ctx.cell_errors == {}


async def test_empty_message_is_safe():
    cell = Cell({})
    ctx = await cell.execute(_ctx(""))
    assert ctx.cell_errors == {}
    assert ctx.entities == []
