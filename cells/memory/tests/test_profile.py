"""Tests for the Context Engine thread profile store — pure SQLite, no model."""

import asyncio

from cells.memory.profile import load_profile, update_threads


def test_recurrence_and_charge_ordering(tmp_path):
    db = tmp_path / "memory.db"

    async def run():
        await update_threads(db, "mario", [("KNowGov", "entity")], 0.0)
        await update_threads(db, "mario", [("KNowGov", "entity"), ("AgentOS", "entity")], 0.0)
        await update_threads(db, "mario", [("KNowGov", "entity")], 0.0)
        await update_threads(db, "mario", [("Dana", "topic")], 0.9)  # 1 mention, high charge
        return await load_profile(db, "mario", 10)

    threads = asyncio.run(run())
    by = {t["key"]: t for t in threads}
    assert by["KNowGov"]["mentions"] == 3
    assert by["AgentOS"]["mentions"] == 1
    keys = [t["key"] for t in threads]
    assert keys[0] == "KNowGov"                       # recurrence wins
    assert keys.index("Dana") < keys.index("AgentOS")  # charge breaks the tie


def test_user_isolation(tmp_path):
    db = tmp_path / "memory.db"

    async def run():
        await update_threads(db, "mario", [("X", "entity")], 0.0)
        await update_threads(db, "jane", [("Y", "entity")], 0.0)
        return (
            await load_profile(db, "mario", 10),
            await load_profile(db, "jane", 10),
        )

    mario, jane = asyncio.run(run())
    assert [t["key"] for t in mario] == ["X"]
    assert [t["key"] for t in jane] == ["Y"]
