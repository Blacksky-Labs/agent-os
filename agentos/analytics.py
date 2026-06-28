"""Analytics for the backend dashboard.

Read-only aggregation over each entity's per-namespace SQLite
(``data/<namespace>/memory.db``): conversation turns (memory cell) and the
thread profile (Context Engine). Pure stdlib ``sqlite3``, no writes ever.

Entity-agnostic — works for any entity that runs the memory cell. Consumed by
the dashboard routes in ``main.py``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def _empty_stats(namespace: str) -> dict:
    return {
        "namespace": namespace,
        "has_data": False,
        "total_messages": 0,
        "user_messages": 0,
        "assistant_messages": 0,
        "sessions": 0,
        "avg_messages_per_session": 0.0,
        "first_activity": None,
        "last_activity": None,
        "messages_by_day": [],
        "recent_sessions": [],
        "users": 0,
        "threads": 0,
        "top_threads": [],
        "turns_measured": 0,
        "avg_latency_ms": 0,
        "total_tokens": 0,
        "avg_tokens": 0,
    }


def entity_stats(namespace: str, repo_root: Path | str = ".", days: int = 14) -> dict:
    """Aggregate stats for one entity. Returns zeros if it has no data yet."""
    from cells.memory.store import db_path_for  # path convention lives with the cell

    db = db_path_for(namespace, repo_root)
    stats = _empty_stats(namespace)
    if not Path(db).exists():
        return stats

    conn = sqlite3.connect(str(db))
    try:
        if _table_exists(conn, "turns"):
            total, u, a, sess, first, last = conn.execute(
                "SELECT COUNT(*), "
                "       SUM(CASE WHEN role='user' THEN 1 ELSE 0 END), "
                "       SUM(CASE WHEN role='assistant' THEN 1 ELSE 0 END), "
                "       COUNT(DISTINCT session_id), MIN(created_at), MAX(created_at) "
                "FROM turns"
            ).fetchone()
            total = total or 0
            stats.update(
                total_messages=total,
                user_messages=u or 0,
                assistant_messages=a or 0,
                sessions=sess or 0,
                first_activity=first,
                last_activity=last,
                has_data=total > 0,
            )
            if sess:
                stats["avg_messages_per_session"] = round(total / sess, 1)

            rows = conn.execute(
                "SELECT date(created_at) d, COUNT(*) c FROM turns "
                "GROUP BY d ORDER BY d DESC LIMIT ?",
                (days,),
            ).fetchall()
            stats["messages_by_day"] = [{"date": d, "count": c} for d, c in reversed(rows)]

            rows = conn.execute(
                "SELECT session_id, COUNT(*) c, MAX(created_at) last FROM turns "
                "GROUP BY session_id ORDER BY last DESC LIMIT 8"
            ).fetchall()
            stats["recent_sessions"] = [
                {"session_id": s, "messages": c, "last": last} for s, c, last in rows
            ]

        if _table_exists(conn, "threads"):
            users, nthreads = conn.execute(
                "SELECT COUNT(DISTINCT user_key), COUNT(*) FROM threads"
            ).fetchone()
            stats["users"] = users or 0
            stats["threads"] = nthreads or 0
            rows = conn.execute(
                "SELECT thread_key, kind, SUM(mentions) m, ROUND(SUM(charge),2) c "
                "FROM threads GROUP BY thread_key "
                "ORDER BY (SUM(mentions)+SUM(charge)) DESC LIMIT 10"
            ).fetchall()
            stats["top_threads"] = [
                {"key": k, "kind": kd, "mentions": m, "charge": c} for k, kd, m, c in rows
            ]

        if _table_exists(conn, "turn_metrics"):
            n, avg_ms, tot_tok, avg_tok = conn.execute(
                "SELECT COUNT(*), AVG(turn_ms), SUM(total_tokens), AVG(total_tokens) "
                "FROM turn_metrics"
            ).fetchone()
            stats["turns_measured"] = n or 0
            stats["avg_latency_ms"] = round(avg_ms) if avg_ms else 0
            stats["total_tokens"] = tot_tok or 0
            stats["avg_tokens"] = round(avg_tok) if avg_tok else 0
    finally:
        conn.close()
    return stats


def db_overview(namespace: str, repo_root: Path | str = ".", row_limit: int = 50) -> dict:
    """Dynamic snapshot of an entity's memory.db for the DB explorer: every
    table with its row count, columns, and most-recent rows. Read-only."""
    from cells.memory.store import db_path_for

    db = db_path_for(namespace, repo_root)
    out: dict = {"namespace": namespace, "db_path": str(db), "exists": Path(db).exists(), "tables": []}
    if not out["exists"]:
        return out

    conn = sqlite3.connect(str(db))
    try:
        names = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for t in names:
            count = conn.execute(f"SELECT COUNT(*) FROM '{t}'").fetchone()[0]
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info('{t}')")]
            rows = conn.execute(
                f"SELECT * FROM '{t}' ORDER BY rowid DESC LIMIT ?", (row_limit,)
            ).fetchall()
            out["tables"].append(
                {"name": t, "count": count, "columns": cols, "rows": [list(r) for r in rows]}
            )
    finally:
        conn.close()
    return out


def fleet_summary(agents: list[tuple[str, str]], repo_root: Path | str = ".") -> list[dict]:
    """One row per entity: (name, namespace) -> headline numbers for the overview."""
    out: list[dict] = []
    for name, namespace in agents:
        s = entity_stats(namespace, repo_root, days=7)
        out.append(
            {
                "name": name,
                "namespace": namespace,
                "total_messages": s["total_messages"],
                "sessions": s["sessions"],
                "threads": s["threads"],
                "last_activity": s["last_activity"],
                "has_data": s["has_data"],
            }
        )
    return out
