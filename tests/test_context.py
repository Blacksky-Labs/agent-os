"""AgentContext contract tests (SPEC §3)."""

from __future__ import annotations

from agentos.context import AgentContext


def test_required_identity_fields(make_context):
    ctx = make_context()
    assert ctx.agent_name == "testbot"
    assert ctx.namespace == "testns"
    assert ctx.session_id == "sess-1"


def test_defaults():
    ctx = AgentContext(agent_name="a", namespace="n", session_id="s")
    assert ctx.mode == "web"
    assert ctx.user_id is None
    assert ctx.response is None
    assert ctx.conversation_history == []
    assert ctx.cell_errors == {}
    assert ctx.assembled_prompt == []


def test_turn_id_is_unique_and_prefixed():
    a = AgentContext(agent_name="a", namespace="n", session_id="s")
    b = AgentContext(agent_name="a", namespace="n", session_id="s")
    assert a.turn_id.startswith("t_")
    assert a.turn_id != b.turn_id


def test_mutable_defaults_are_not_shared():
    """Two contexts must not share the same list/dict instances."""
    a = AgentContext(agent_name="a", namespace="n", session_id="s")
    b = AgentContext(agent_name="a", namespace="n", session_id="s")
    a.conversation_history.append({"role": "user", "content": "hi"})
    a.meta["k"] = "v"
    assert b.conversation_history == []
    assert b.meta == {}


def test_created_at_is_set():
    ctx = AgentContext(agent_name="a", namespace="n", session_id="s")
    assert isinstance(ctx.created_at, float)
    assert ctx.created_at > 0
