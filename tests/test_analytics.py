"""Tests for the dashboard analytics — pure SQLite, no server."""

import asyncio

from agentos.analytics import entity_stats, fleet_summary
from cells.memory.profile import update_threads
from cells.memory.store import append_turn, init_store


def test_entity_stats(tmp_path):
    async def seed():
        db = await init_store("acme", repo_root=tmp_path)
        for i in range(3):
            await append_turn(db, "s1", f"t{i}", "user", f"q{i}")
            await append_turn(db, "s1", f"t{i}", "assistant", f"a{i}")
        await append_turn(db, "s2", "tx", "user", "hi")
        await update_threads(db, "mario", [("KNowGov", "entity"), ("AgentOS", "entity")], 0.0)
        await update_threads(db, "mario", [("KNowGov", "entity")], 0.4)

    asyncio.run(seed())
    s = entity_stats("acme", repo_root=tmp_path)
    assert s["has_data"] is True
    assert s["total_messages"] == 7           # 3 pairs + 1 user
    assert s["user_messages"] == 4 and s["assistant_messages"] == 3
    assert s["sessions"] == 2
    assert s["top_threads"][0]["key"] == "KNowGov" and s["top_threads"][0]["mentions"] == 2
    assert s["messages_by_day"]                # at least today


def test_missing_entity_is_empty(tmp_path):
    s = entity_stats("ghost", repo_root=tmp_path)
    assert s["has_data"] is False
    assert s["total_messages"] == 0 and s["top_threads"] == []


def test_fleet_summary(tmp_path):
    async def seed():
        db = await init_store("acme", repo_root=tmp_path)
        await append_turn(db, "s1", "t1", "user", "hi")

    asyncio.run(seed())
    fleet = fleet_summary([("acme", "acme"), ("ghost", "ghost")], repo_root=tmp_path)
    by = {f["name"]: f for f in fleet}
    assert by["acme"]["total_messages"] == 1 and by["acme"]["has_data"] is True
    assert by["ghost"]["has_data"] is False
