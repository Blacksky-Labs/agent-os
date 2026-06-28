"""memory store + memory_persist hook tests (SPEC §5/§7)."""

from __future__ import annotations

import pytest

from cells.memory.store import append_turn, db_path_for, init_store, load_turns
from hooks.memory_persist import handle as persist_handle


async def test_init_creates_db(tmp_path):
    path = await init_store("ns1", repo_root=tmp_path)
    assert path.exists()
    assert path == db_path_for("ns1", tmp_path)


async def test_append_and_load_roundtrip(tmp_path):
    path = await init_store("ns1", repo_root=tmp_path)
    await append_turn(path, "sess-1", "t1", "user", "hello")
    await append_turn(path, "sess-1", "t1", "assistant", "hi there")
    turns = await load_turns(path, "sess-1")
    assert turns == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]


async def test_oldest_first_ordering(tmp_path):
    path = await init_store("ns1", repo_root=tmp_path)
    for i in range(5):
        await append_turn(path, "s", f"t{i}", "user", f"msg{i}")
    turns = await load_turns(path, "s")
    assert [t["content"] for t in turns] == ["msg0", "msg1", "msg2", "msg3", "msg4"]


async def test_limit_returns_most_recent_in_order(tmp_path):
    path = await init_store("ns1", repo_root=tmp_path)
    for i in range(10):
        await append_turn(path, "s", f"t{i}", "user", f"msg{i}")
    turns = await load_turns(path, "s", limit=3)
    # most recent 3, still oldest-first
    assert [t["content"] for t in turns] == ["msg7", "msg8", "msg9"]


async def test_sessions_are_isolated(tmp_path):
    path = await init_store("ns1", repo_root=tmp_path)
    await append_turn(path, "sessA", "t1", "user", "from A")
    await append_turn(path, "sessB", "t1", "user", "from B")
    assert [t["content"] for t in await load_turns(path, "sessA")] == ["from A"]
    assert [t["content"] for t in await load_turns(path, "sessB")] == ["from B"]


async def test_namespaces_are_isolated(tmp_path):
    p1 = await init_store("ns1", repo_root=tmp_path)
    p2 = await init_store("ns2", repo_root=tmp_path)
    assert p1 != p2
    await append_turn(p1, "s", "t1", "user", "ns1 only")
    assert await load_turns(p2, "s") == []


async def test_invalid_role_rejected_by_schema(tmp_path):
    path = await init_store("ns1", repo_root=tmp_path)
    with pytest.raises(Exception):  # sqlite CHECK constraint
        await append_turn(path, "s", "t1", "system", "not allowed")


# --- memory_persist hook ---

async def test_hook_persists_user_and_assistant(tmp_path, monkeypatch, make_context):
    # Point the store at tmp by patching init_store inside the hook module.
    import hooks.memory_persist as hm

    async def fake_init(namespace, repo_root="."):
        return await init_store(namespace, repo_root=tmp_path)

    monkeypatch.setattr(hm, "init_store", fake_init)

    ctx = make_context(
        namespace="ns1", session_id="s", user_message="ping", response="pong"
    )
    await persist_handle(ctx, {}, {})

    path = db_path_for("ns1", tmp_path)
    turns = await load_turns(path, "s")
    assert turns == [
        {"role": "user", "content": "ping"},
        {"role": "assistant", "content": "pong"},
    ]


async def test_hook_persists_user_even_without_response(tmp_path, monkeypatch, make_context):
    import hooks.memory_persist as hm

    async def fake_init(namespace, repo_root="."):
        return await init_store(namespace, repo_root=tmp_path)

    monkeypatch.setattr(hm, "init_store", fake_init)

    ctx = make_context(namespace="ns1", session_id="s", user_message="ping", response=None)
    await persist_handle(ctx, {}, {})

    turns = await load_turns(db_path_for("ns1", tmp_path), "s")
    assert turns == [{"role": "user", "content": "ping"}]
