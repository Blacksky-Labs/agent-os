"""context-builder cell tests (SPEC §5/§8)."""

from __future__ import annotations

from cells.context_builder.cell import Cell


def _system(messages):
    assert messages[0]["role"] == "system"
    return messages[0]["content"]


async def test_basic_shape_system_then_user(make_context):
    cell = Cell({})
    ctx = make_context(user_message="hello", persona={"display_name": "Stan"})
    out = await cell.execute(ctx)
    msgs = out.assembled_prompt
    assert msgs[0]["role"] == "system"
    assert msgs[-1] == {"role": "user", "content": "hello"}


async def test_identity_uses_display_name(make_context):
    cell = Cell({})
    ctx = make_context(persona={"display_name": "Stan"})
    out = await cell.execute(ctx)
    assert "You are Stan." in _system(out.assembled_prompt)


async def test_identity_falls_back_to_agent_name(make_context):
    cell = Cell({})
    ctx = make_context(agent_name="fallbackbot", persona={})
    out = await cell.execute(ctx)
    assert "You are fallbackbot." in _system(out.assembled_prompt)


async def test_mission_included_but_placeholder_skipped(make_context):
    cell = Cell({})
    real = await cell.execute(make_context(persona={"mission": "Track the halving."}))
    assert "Track the halving." in _system(real.assembled_prompt)

    placeholder = await cell.execute(make_context(persona={"mission": "(fill in later)"}))
    assert "(fill in later)" not in _system(placeholder.assembled_prompt)


async def test_conversation_history_threaded_between_system_and_user(make_context):
    cell = Cell({})
    ctx = make_context(
        user_message="and now?",
        conversation_history=[
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
        ],
    )
    out = await cell.execute(ctx)
    roles = [m["role"] for m in out.assembled_prompt]
    assert roles == ["system", "user", "assistant", "user"]
    assert out.assembled_prompt[-1]["content"] == "and now?"


async def test_malformed_history_entries_dropped(make_context):
    cell = Cell({})
    ctx = make_context(
        conversation_history=[
            {"role": "system", "content": "nope"},  # wrong role
            {"role": "user", "content": ""},          # empty content
            {"role": "assistant", "content": "kept"},
        ],
    )
    out = await cell.execute(ctx)
    contents = [m["content"] for m in out.assembled_prompt]
    assert "nope" not in contents
    assert "kept" in contents


async def test_retrieved_chunks_render_with_source(make_context):
    cell = Cell({})
    ctx = make_context(
        retrieved_chunks=[
            {"source": "/corpus/btc.md", "content": "halving every 210k blocks", "similarity": 0.91},
        ],
    )
    sysmsg = _system((await cell.execute(ctx)).assembled_prompt)
    assert "Reference material" in sysmsg
    assert "btc.md" in sysmsg          # short source, not full path
    assert "halving every 210k blocks" in sysmsg


async def test_voice_emojis_never(make_context):
    cell = Cell({})
    ctx = make_context(persona={"voice": {"emojis": "never", "tone": "dry"}})
    sysmsg = _system((await cell.execute(ctx)).assembled_prompt)
    assert "Never use emoji." in sysmsg
    assert "dry" in sysmsg


async def test_refusals_rendered(make_context):
    cell = Cell({})
    ctx = make_context(
        persona={"refusals": [{"topic": "tax advice", "response": "I can't advise on taxes."}]}
    )
    sysmsg = _system((await cell.execute(ctx)).assembled_prompt)
    assert "tax advice" in sysmsg
    assert "I can't advise on taxes." in sysmsg


async def test_anti_drift_anchor_always_present(make_context):
    cell = Cell({})
    sysmsg = _system((await cell.execute(make_context(persona={}))).assembled_prompt)
    assert "Stay in character." in sysmsg
