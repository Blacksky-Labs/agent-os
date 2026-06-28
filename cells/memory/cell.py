"""memory cell — v1.1.0 — the Context Engine (read side).

Hydrates two channels from per-namespace SQLite at ``data/<namespace>/memory.db``:
    - ``context.conversation_history`` — the last N turns for this session
    - ``context.user_profile`` — the living *thread profile*: subjects the user
      keeps returning to, weighted by recurrence + emotional charge (v1.1.0)

Reads only. The writes are side effects in hooks (SPEC §5/§7):
``hooks/memory_persist.py`` appends turns; ``hooks/context_update.py`` updates
the thread profile from what the Sentiment Engine extracted.

v1.1.0 vs v1.0.0:
    - Adds the thread profile into ``context.user_profile`` (the Context Engine).
    - Config: ``profile`` (bool, default True), ``profile_limit`` (default 12).

Future:
    - v2.0.0: Postgres/Redis tiered backend (the Maurice pattern)
    - ``semantic_history`` channel
"""

from __future__ import annotations

from pathlib import Path

from agentos.context import AgentContext
from cells.memory.profile import load_profile, profile_key
from cells.memory.store import init_store, load_turns


class Cell:
    name = "memory"
    version = "1.1.0"

    def __init__(self, config: dict):
        self.config = config or {}
        self.max_history: int = int(self.config.get("max_history", 20))
        self.profile_enabled: bool = bool(self.config.get("profile", True))
        self.profile_limit: int = int(self.config.get("profile_limit", 12))
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

        # Context Engine: hydrate the living thread profile (cross-session,
        # per user). Read-only here; the context_update hook does the writes.
        if self.profile_enabled:
            context.user_profile = {
                "threads": await load_profile(
                    self._db_path, profile_key(context), self.profile_limit
                )
            }

        return context

    async def teardown(self) -> None:
        pass
