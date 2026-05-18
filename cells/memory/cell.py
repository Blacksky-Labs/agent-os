"""memory cell — v1.0.0.

Hydrates ``context.conversation_history`` from per-namespace SQLite at
``data/<namespace>/memory.db``. The actual write (after each turn) lives
in the after_turn hook handler ``hooks/memory_persist.py``, per SPEC §5
(cells stay pure; side effects belong to hooks).

v1.0.0 scope:
    - Local SQLite, one DB per namespace
    - Read-only on ``execute()``: loads the last N turns for the current
      ``session_id`` into ``context.conversation_history``
    - Lazy: opens the DB on first ``execute()`` (namespace isn't known
      at ``init()``)
    - Configurable history limit via cell config ``max_history`` (default 20)

Future (not in v1.0.0):
    - v2.0.0: Postgres/Redis tiered backend (the Maurice pattern)
    - ``user_profile`` and ``semantic_history`` channels
"""

from __future__ import annotations

from pathlib import Path

from agentos.context import AgentContext
from cells.memory.store import init_store, load_turns


class Cell:
    name = "memory"
    version = "1.0.0"

    def __init__(self, config: dict):
        self.config = config or {}
        self.max_history: int = int(self.config.get("max_history", 20))
        self._db_path: Path | None = None
        self._inited_for_ns: str | None = None

    def init(self, config: dict) -> None:
        # Can't open the DB here — namespace isn't known until execute().
        pass

    async def execute(self, context: AgentContext) -> AgentContext:
        # Lazy init on first turn (or if the namespace changed for some reason).
        if self._db_path is None or self._inited_for_ns != context.namespace:
            self._db_path = await init_store(context.namespace)
            self._inited_for_ns = context.namespace

        context.conversation_history = await load_turns(
            self._db_path,
            context.session_id,
            limit=self.max_history,
        )
        return context

    async def teardown(self) -> None:
        pass
