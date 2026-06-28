"""Tests for the style expert (deterministic bullet normalization)."""

from agentos.context import AgentContext
from cells.style.cell import Cell, _normalize_bullets


def test_normalizes_markers_to_dash():
    src = "Here's your list:\n* make a song\n1. fix the door\n- already a bullet\nplain line"
    out = _normalize_bullets(src)
    assert out == (
        "Here's your list:\n- make a song\n- fix the door\n- already a bullet\nplain line"
    )


def test_leaves_prose_and_decimals_alone():
    assert _normalize_bullets("it took 3.5 hours") == "it took 3.5 hours"
    assert _normalize_bullets("no list here") == "no list here"


async def test_cell_rewrites_response():
    cell = Cell({})
    ctx = AgentContext(agent_name="skipper", namespace="skipper", session_id="s1")
    ctx.response = "Today:\n* song\n2) door"
    out = await cell.execute(ctx)
    assert out.response == "Today:\n- song\n- door"
    assert out.cell_errors == {}


async def test_no_response_is_safe():
    cell = Cell({})
    ctx = AgentContext(agent_name="skipper", namespace="skipper", session_id="s1")
    ctx.response = None
    out = await cell.execute(ctx)
    assert out.response is None and out.cell_errors == {}
