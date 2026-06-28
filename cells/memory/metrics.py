"""Per-turn metrics store — latency + token usage.

Written by the ``turn_metrics`` after_turn hook; read by ``agentos.analytics``
for the dashboard. Lives in the same per-namespace SQLite as turns and threads
(``data/<namespace>/memory.db``). Pure stdlib sqlite3.

Observability data, not conversation data — but co-located in the per-namespace
DB so an entity's whole footprint is one file. Entity-agnostic.
"""

from __future__ import annotations

import asyncio
import sqlite3

METRICS_SCHEMA = """
CREATE TABLE IF NOT EXISTS turn_metrics (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT,
    turn_id           TEXT,
    turn_ms           REAL,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    total_tokens      INTEGER,
    model             TEXT,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_metrics_created ON turn_metrics(created_at);
"""


def _record_sync(db_path, row: tuple) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(METRICS_SCHEMA)
        conn.execute(
            "INSERT INTO turn_metrics "
            "(session_id, turn_id, turn_ms, prompt_tokens, completion_tokens, total_tokens, model) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            row,
        )
        conn.commit()


async def record_turn(
    db_path, session_id: str, turn_id: str, turn_ms, usage: dict | None, model
) -> None:
    """Persist one turn's latency + token usage. Tolerates missing usage."""
    usage = usage or {}
    row = (
        session_id,
        turn_id,
        turn_ms,
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
        usage.get("total_tokens"),
        model,
    )
    await asyncio.to_thread(_record_sync, db_path, row)
