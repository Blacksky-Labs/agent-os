"""Thread profile store for the Context Engine (memory cell v1.1.0+).

A *thread* is a tracked subject — an entity or topic the user keeps returning
to. Threads are weighted by **recurrence** (mention count) and **emotional
charge** (accumulated from the Sentiment Engine). The thing mentioned five times
outranks the thing mentioned once; an emotionally heavy thread is boosted.

Lives in the same per-namespace SQLite as conversation turns
(``data/<namespace>/memory.db``). Pure stdlib ``sqlite3``; blocking I/O wrapped
via ``asyncio.to_thread`` so the cell's async contract holds.

Entity-agnostic: every AgentOS entity that runs the memory cell gets this. The
read happens in the cell; the write happens in the ``context_update`` hook
(side effects belong to hooks, SPEC §7).
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

THREADS_SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    user_key   TEXT NOT NULL,
    thread_key TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'entity',
    mentions   INTEGER NOT NULL DEFAULT 0,
    charge     REAL NOT NULL DEFAULT 0.0,
    first_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_key, thread_key)
);
CREATE INDEX IF NOT EXISTS idx_threads_user ON threads(user_key);
"""


def _norm(s: str) -> str:
    return " ".join(str(s).split()).strip()


def _ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(THREADS_SCHEMA)


def _update_sync(db_path, user_key: str, items: list[tuple[str, str]], charge: float) -> None:
    with sqlite3.connect(db_path) as conn:
        _ensure(conn)
        for raw_key, kind in items:
            key = _norm(raw_key)
            if not key:
                continue
            conn.execute(
                "INSERT INTO threads (user_key, thread_key, kind, mentions, charge) "
                "VALUES (?, ?, ?, 1, ?) "
                "ON CONFLICT(user_key, thread_key) DO UPDATE SET "
                "  mentions  = mentions + 1, "
                "  charge    = charge + excluded.charge, "
                "  last_seen = CURRENT_TIMESTAMP, "
                # a thread that was ever a 'topic' stays a topic
                "  kind = CASE WHEN threads.kind='topic' THEN 'topic' ELSE excluded.kind END",
                (user_key, key, kind, float(charge)),
            )
        conn.commit()


def _load_sync(db_path, user_key: str, limit: int) -> list[dict]:
    if not Path(db_path).exists():
        return []
    with sqlite3.connect(db_path) as conn:
        _ensure(conn)
        rows = conn.execute(
            "SELECT thread_key, kind, mentions, charge, last_seen FROM threads "
            "WHERE user_key = ? "
            "ORDER BY (mentions + charge) DESC, last_seen DESC "
            "LIMIT ?",
            (user_key, limit),
        ).fetchall()
    return [
        {
            "key": r[0],
            "kind": r[1],
            "mentions": r[2],
            "charge": round(r[3], 2),
            "last_seen": r[4],
        }
        for r in rows
    ]


async def update_threads(
    db_path, user_key: str, items: list[tuple[str, str]], charge: float = 0.0
) -> None:
    """Increment recurrence (and add charge) for each (key, kind) this turn."""
    await asyncio.to_thread(_update_sync, db_path, user_key, list(items), charge)


async def load_profile(db_path, user_key: str, limit: int = 12) -> list[dict]:
    """Top threads for a user, weighted by recurrence + charge."""
    return await asyncio.to_thread(_load_sync, db_path, user_key, limit)


def profile_key(context) -> str:
    """The Context Engine profile key.

    Single-owner by default: every AgentOS instance has one owner, so all
    surfaces (web, app, phone) roll up to one profile keyed by the owner —
    a per-request ``user_id`` is ignored. Agents that serve external users
    (``multi_user: true`` — Maurice's leads, Judy's constituents) key by the
    incoming ``user_id`` instead, so each contact gets their own profile.
    """
    meta = context.meta or {}
    if meta.get("multi_user"):
        return context.user_id or "_default"
    return meta.get("owner") or "owner"
