"""Tasks + Entities store — Skipper's dashboard data.

Goals/Tasks are what Skipper *does*; Entities are what Skipper *knows*. Both
live in the same per-namespace SQLite as the memory cell
(``data/<namespace>/memory.db``) so an entity's whole footprint stays one file —
the same convention as ``turns``, ``threads``, and ``turn_metrics``.

Stdlib ``sqlite3`` only, no new deps. These are plain sync helpers (like
``agentos.analytics``); the kernel calls them from its route handlers. The
schema is created on demand (``CREATE TABLE IF NOT EXISTS``) so reads never hit
a missing table.

Schemas are SKIPPER-DASH-SEED-001 Part 1, verbatim. The only adaptation from the
seed is the storage location: per-namespace ``memory.db`` (resolved via
``cells.memory.store.db_path_for``) instead of a global ``~/.skipper/skipper.db``,
to match AgentOS's existing per-entity data model.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cells.memory.store import db_path_for  # single source of truth for the DB path

__all__ = [
    "db_path_for",
    "ensure_schema",
    "list_tasks",
    "get_task",
    "create_task",
    "update_task",
    "delete_task",
    "list_entities",
    "get_entity",
    "create_entity",
    "entity_linked",
    "update_entity",
    "delete_entity",
]


# ── Schema (SKIPPER-DASH-SEED-001 Part 1) ──────────────────────────────

TASKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
        -- pending | active | complete | escalated | cancelled
    step_type TEXT NOT NULL DEFAULT 'autonomous',
        -- autonomous | breakpoint | handoff | conditional
    parent_task_id TEXT REFERENCES tasks(id),
    goal_id TEXT,
        -- references goals.id when Goals table exists; nullable for now
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    metadata TEXT
        -- JSON blob for extension without schema migration
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_goal ON tasks(goal_id);
"""

ENTITIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    surface_form TEXT NOT NULL,
        -- the raw text as extracted ("Dr. Angela Davis", "Baltimore", "USDA")
    entity_type TEXT NOT NULL,
        -- PERSON | ORG | PLACE | CONCEPT | EVENT | OTHER
    canonical_form TEXT,
        -- normalized/resolved form if known
    confidence REAL DEFAULT 1.0,
        -- 0.0-1.0, NLP extraction confidence
    source_type TEXT,
        -- task | goal | message | document
    source_id TEXT,
        -- id of the source record
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata TEXT
        -- JSON blob for tags, aliases, notes
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_source ON entities(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_entities_surface ON entities(surface_form);
"""

# Columns a PATCH is allowed to touch. Whitelisted because column names cannot be
# parameterized — never interpolate a key that isn't in one of these sets.
_TASK_UPDATE_COLUMNS = frozenset(
    {"title", "description", "status", "step_type", "parent_task_id", "goal_id", "completed_at"}
)
_ENTITY_UPDATE_COLUMNS = frozenset(
    {"surface_form", "canonical_form", "entity_type", "confidence", "source_type", "source_id"}
)


# ── Connection helpers ─────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_schema(db_path) -> None:
    """Create the tasks + entities tables (and indexes) if absent. Idempotent."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript(TASKS_SCHEMA)
        conn.executescript(ENTITIES_SCHEMA)
        conn.commit()


# ── Tasks ──────────────────────────────────────────────────────────────

def list_tasks(db_path, status: str | None = None) -> list[dict]:
    ensure_schema(db_path)
    with _connect(db_path) as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_task(db_path, task_id: str) -> dict | None:
    ensure_schema(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def create_task(
    db_path,
    title: str,
    *,
    description: str | None = None,
    status: str = "pending",
    step_type: str = "autonomous",
    parent_task_id: str | None = None,
    goal_id: str | None = None,
    task_id: str | None = None,
) -> dict:
    """Insert a task. Not exposed to the dashboard (read+edit only per the seed);
    used by Skipper's reasoning loop, the demo seeder, and tests."""
    ensure_schema(db_path)
    tid = task_id or uuid.uuid4().hex
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO tasks (id, title, description, status, step_type, parent_task_id, goal_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tid, title, description, status, step_type, parent_task_id, goal_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone()
    return dict(row)


def update_task(db_path, task_id: str, patch: dict) -> dict | None:
    """Apply a partial update. Unknown/None fields are ignored. Returns the row,
    or None if the task does not exist."""
    ensure_schema(db_path)
    updates = {
        k: v for k, v in patch.items() if k in _TASK_UPDATE_COLUMNS and v is not None
    }
    with _connect(db_path) as conn:
        if conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone() is None:
            return None
        # Stamp completed_at when a task transitions to complete and the caller
        # didn't set it explicitly.
        if updates.get("status") == "complete" and "completed_at" not in updates:
            updates["completed_at"] = _now()
        updates["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ?",
            (*updates.values(), task_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row)


def delete_task(db_path, task_id: str) -> bool:
    """Delete a task. Returns True if a row was removed."""
    ensure_schema(db_path)
    with _connect(db_path) as conn:
        if conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone() is None:
            return False
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
    return True


# ── Entities ───────────────────────────────────────────────────────────

def list_entities(db_path, entity_type: str | None = None) -> list[dict]:
    ensure_schema(db_path)
    with _connect(db_path) as conn:
        if entity_type:
            rows = conn.execute(
                "SELECT * FROM entities WHERE entity_type = ? ORDER BY surface_form ASC",
                (entity_type,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM entities ORDER BY entity_type ASC, surface_form ASC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_entity(db_path, entity_id: str) -> dict | None:
    ensure_schema(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    return dict(row) if row else None


def create_entity(
    db_path,
    surface_form: str,
    entity_type: str,
    *,
    canonical_form: str | None = None,
    confidence: float = 1.0,
    source_type: str | None = None,
    source_id: str | None = None,
    entity_id: str | None = None,
) -> dict:
    """Insert an entity. Normally written by Skipper's NLP extraction; used here
    by the demo seeder and tests."""
    ensure_schema(db_path)
    eid = entity_id or uuid.uuid4().hex
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO entities "
            "(id, surface_form, entity_type, canonical_form, confidence, source_type, source_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (eid, surface_form, entity_type, canonical_form, confidence, source_type, source_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone()
    return dict(row)


def entity_linked(db_path, entity_id: str) -> dict | None:
    """Return the entity plus any tasks it links to via (source_type, source_id).
    None if the entity does not exist."""
    ensure_schema(db_path)
    with _connect(db_path) as conn:
        entity = conn.execute(
            "SELECT * FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        if not entity:
            return None
        entity_dict = dict(entity)
        tasks: list[dict] = []
        if entity_dict.get("source_type") == "task" and entity_dict.get("source_id"):
            task = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (entity_dict["source_id"],)
            ).fetchone()
            if task:
                tasks = [dict(task)]
    return {"entity": entity_dict, "linked_tasks": tasks}


def update_entity(db_path, entity_id: str, patch: dict) -> dict | None:
    ensure_schema(db_path)
    updates = {
        k: v for k, v in patch.items() if k in _ENTITY_UPDATE_COLUMNS and v is not None
    }
    with _connect(db_path) as conn:
        if conn.execute("SELECT 1 FROM entities WHERE id = ?", (entity_id,)).fetchone() is None:
            return None
        updates["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE entities SET {set_clause} WHERE id = ?",
            (*updates.values(), entity_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    return dict(row)


def delete_entity(db_path, entity_id: str) -> bool:
    ensure_schema(db_path)
    with _connect(db_path) as conn:
        if conn.execute("SELECT 1 FROM entities WHERE id = ?", (entity_id,)).fetchone() is None:
            return False
        conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        conn.commit()
    return True
