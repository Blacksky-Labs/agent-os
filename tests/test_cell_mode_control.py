"""mode-control cell tests (SPEC §5)."""

from __future__ import annotations

from cells.mode_control.cell import Cell


async def test_constraints_pulled_from_persona_for_active_mode(make_context):
    cell = Cell({})
    ctx = make_context(
        mode="phone",
        persona={"modes": {"phone": {"max_words": 40, "markdown": False}}},
    )
    out = await cell.execute(ctx)
    assert out.mode_constraints == {"max_words": 40, "markdown": False}


async def test_unknown_mode_yields_empty_constraints(make_context):
    cell = Cell({})
    ctx = make_context(mode="carrier-pigeon", persona={"modes": {"web": {"x": 1}}})
    out = await cell.execute(ctx)
    assert out.mode_constraints == {}


async def test_no_persona_modes_is_safe(make_context):
    cell = Cell({})
    ctx = make_context(mode="web", persona={})
    out = await cell.execute(ctx)
    assert out.mode_constraints == {}


async def test_constraints_are_copied_not_aliased(make_context):
    """Mutating context constraints must not mutate the persona dict."""
    cell = Cell({})
    persona = {"modes": {"web": {"max_words": 100}}}
    ctx = make_context(mode="web", persona=persona)
    out = await cell.execute(ctx)
    out.mode_constraints["max_words"] = 999
    assert persona["modes"]["web"]["max_words"] == 100
