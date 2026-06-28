#!/usr/bin/env python3
"""Seed Skipper's per-namespace DB with demo tasks + entities.

The dashboard is read + direct-edit only — tasks/entities are normally authored
by Skipper's reasoning loop — so this script gives you something to look at and
click while that loop is still being built.

Idempotent: every row uses a deterministic ``demo-*`` id, so re-running replaces
rather than duplicates. ``--clear`` removes the demo rows again.

    python tools/seed_skipper_demo.py                 # seed namespace "skipper"
    python tools/seed_skipper_demo.py --namespace foo  # seed another entity
    python tools/seed_skipper_demo.py --clear          # remove demo rows

Honors AGENTOS_DATA_DIR (so it writes to the same place the app reads). Without
it, rows land in ./data/<namespace>/memory.db under the repo.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Allow `python tools/seed_skipper_demo.py` from anywhere: put the repo root
# (this file's grandparent) on sys.path so `agentos` imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentos import skipper_store  # noqa: E402

# (id, title, description, status, step_type, parent_task_id, goal_id)
DEMO_TASKS = [
    ("demo-task-grant", "Plan Q3 community garden grant", "USDA People's Garden grant — due Sept 1.", "active", "autonomous", None, "demo-goal-garden"),
    ("demo-task-budget", "Draft the grant budget", "Line items for soil, seed, irrigation, and labor.", "active", "breakpoint", "demo-task-grant", "demo-goal-garden"),
    ("demo-task-letters", "Collect letters of support", "Reach out to neighborhood association + two local orgs.", "pending", "handoff", "demo-task-grant", "demo-goal-garden"),
    ("demo-task-soil", "Order soil test kits", "Confirmed delivered — close this out.", "complete", "autonomous", "demo-task-grant", "demo-goal-garden"),
    ("demo-task-venue", "Confirm winter market venue", "Original venue double-booked — needs a human call.", "escalated", "conditional", None, None),
    ("demo-task-news", "Send the May newsletter", "Drafted, scheduled, sent.", "complete", "autonomous", None, None),
]

# (id, surface_form, entity_type, canonical_form, confidence, source_type, source_id)
DEMO_ENTITIES = [
    ("demo-ent-davis", "Dr. Angela Davis", "PERSON", "Angela Y. Davis", 0.94, "task", "demo-task-letters"),
    ("demo-ent-usda", "USDA", "ORG", "U.S. Department of Agriculture", 0.99, "task", "demo-task-grant"),
    ("demo-ent-assoc", "the neighborhood association", "ORG", "Oakdale Neighborhood Association", 0.71, "task", "demo-task-letters"),
    ("demo-ent-baltimore", "Baltimore", "PLACE", "Baltimore, MD", 0.97, "task", "demo-task-grant"),
    ("demo-ent-sovereignty", "food sovereignty", "CONCEPT", None, 0.82, "message", None),
    ("demo-ent-market", "winter market", "EVENT", "Oakdale Winter Market", 0.88, "task", "demo-task-venue"),
]

DEMO_IDS = [t[0] for t in DEMO_TASKS] + [e[0] for e in DEMO_ENTITIES]


def clear(db_path) -> None:
    skipper_store.ensure_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany("DELETE FROM tasks WHERE id = ?", [(t[0],) for t in DEMO_TASKS])
        conn.executemany("DELETE FROM entities WHERE id = ?", [(e[0],) for e in DEMO_ENTITIES])
        conn.commit()


def seed(db_path) -> None:
    skipper_store.ensure_schema(db_path)
    clear(db_path)  # replace, don't duplicate
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO tasks (id, title, description, status, step_type, parent_task_id, goal_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            DEMO_TASKS,
        )
        # stamp completed_at on the ones marked complete
        conn.execute(
            "UPDATE tasks SET completed_at = datetime('now') WHERE status = 'complete' AND id LIKE 'demo-%'"
        )
        conn.executemany(
            "INSERT INTO entities (id, surface_form, entity_type, canonical_form, confidence, source_type, source_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            DEMO_ENTITIES,
        )
        conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed/clear Skipper demo tasks + entities.")
    ap.add_argument("--namespace", default="skipper", help="entity namespace (default: skipper)")
    ap.add_argument("--clear", action="store_true", help="remove demo rows instead of seeding")
    args = ap.parse_args()

    db_path = skipper_store.db_path_for(args.namespace)
    if args.clear:
        clear(db_path)
        print(f"Cleared {len(DEMO_IDS)} demo rows from {db_path}")
        return

    seed(db_path)
    print(f"Seeded {len(DEMO_TASKS)} tasks + {len(DEMO_ENTITIES)} entities → {db_path}")
    print("Open Skipper → Overview tab (or GET /dashboard) to see them.")


if __name__ == "__main__":
    main()
