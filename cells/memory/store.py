"""SQLite helpers for the memory cell + memory_persist hook.

One DB per namespace at ``data/<namespace>/memory.db``. Schema is intentionally
minimal for v1.0.0 — just a ``turns`` table. The memory cell reads via
``load_turns()`` on each execute(); the after_turn hook writes via
``append_turn()``.

Stdlib ``sqlite3`` only — no new deps. Blocking I/O is wrapped via
``asyncio.to_thread`` so the cell's async contract holds.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_id    TEXT NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_turns_session    ON turns(session_id);
CREATE INDEX IF NOT EXISTS idx_turns_session_id ON turns(session_id, id);
"""


def db_path_for(namespace: str, repo_root: Path | str = ".") -> Path:
    """Return the canonical SQLite path for a namespace's memory DB."""
    return Path(repo_root) / "data" / namespace / "memory.db"


# ----------------------------------------------------------------------
# Sync internals
# ----------------------------------------------------------------------

def _init_sync(namespace: str, repo_root: Path | str) -> Path:
    path = db_path_for(namespace, repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()
    return path


def _load_sync(db_path: Path, session_id: str, limit: int) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT role, content FROM turns "
            "WHERE session_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    # newest-first → reverse for oldest-first prompt order
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def _append_sync(
    db_path: Path,
    session_id: str,
    turn_id: str,
    role: str,
    content: str,
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO turns (session_id, turn_id, role, content) "
            "VALUES (?, ?, ?, ?)",
            (session_id, turn_id, role, content),
        )
        conn.commit()


# ----------------------------------------------------------------------
# Async surface (cells + hooks call these)
# ----------------------------------------------------------------------

async def init_store(namespace: str, repo_root: Path | str = ".") -> Path:
    """Ensure ``data/<namespace>/memory.db`` exists with the schema."""
    return await asyncio.to_thread(_init_sync, namespace, repo_root)


async def load_turns(
    db_path: Path,
    session_id: str,
    limit: int = 20,
) -> list[dict]:
    """Load the most recent ``limit`` turns for a session, oldest-first."""
    return await asyncio.to_thread(_load_sync, db_path, session_id, limit)


async def append_turn(
    db_path: Path,
    session_id: str,
    turn_id: str,
    role: str,
    content: str,
) -> None:
    """Append one turn (user or assistant) to the memory store."""
    await asyncio.to_thread(
        _append_sync, db_path, session_id, turn_id, role, content
    )
