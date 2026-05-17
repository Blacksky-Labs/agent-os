"""Hook dispatcher.

Hooks are named events fired around pipeline phases. Handlers run *outside*
the cell pipeline and own all side effects. A handler failure is logged but
does not propagate.

See SPEC.md §7.
"""

from __future__ import annotations

import asyncio
import importlib
import time
from typing import Awaitable, Callable

from agentos.context import AgentContext
from agentos.observability import log_event


HookHandler = Callable[[AgentContext, dict, dict], Awaitable[None]]


EVENT_TYPES: tuple[str, ...] = (
    "before_turn",
    "after_turn",
    "on_cell_error",
    "on_tool_call",
    "on_high_intent",
    "on_lead_scored",
    "on_conversation_end",
)


class HookDispatcher:
    """Dispatches hook events to subscribed handlers.

    Handler naming convention: a manifest entry ``handler: log_audit_trail``
    resolves to ``hooks.log_audit_trail.handle`` — a function with signature
    ``async def handle(context, payload, config) -> None``.
    """

    def __init__(self, subscriptions: dict | None):
        self._handlers: dict[str, list[tuple[HookHandler, dict]]] = {}
        for event, entries in (subscriptions or {}).items():
            if event not in EVENT_TYPES:
                log_event(
                    kind="kernel",
                    namespace="*",
                    turn_id="-",
                    error=f"unknown hook event '{event}' — ignored",
                )
                continue
            self._handlers[event] = []
            for entry in entries or []:
                handler_name = entry.get("handler")
                handler_config = entry.get("config", {}) or {}
                if not handler_name:
                    continue
                func = self._load_handler(handler_name)
                if func is not None:
                    self._handlers[event].append((func, handler_config))

    @staticmethod
    def _load_handler(handler_name: str) -> HookHandler | None:
        """Resolve ``<name>`` to ``hooks.<name>.handle``."""
        try:
            module = importlib.import_module(f"hooks.{handler_name}")
            return getattr(module, "handle")
        except (ImportError, AttributeError) as e:
            log_event(
                kind="kernel",
                namespace="*",
                turn_id="-",
                error=f"hook handler 'hooks.{handler_name}.handle' not loadable: {e}",
            )
            return None

    async def fire(
        self,
        event: str,
        context: AgentContext,
        payload: dict | None = None,
    ) -> None:
        """Fire all handlers for an event in parallel."""
        handlers = self._handlers.get(event, [])
        if not handlers:
            return
        payload = payload or {}
        await asyncio.gather(
            *(self._run(event, h, context, payload, c) for h, c in handlers),
            return_exceptions=True,
        )

    async def _run(
        self,
        event: str,
        handler: HookHandler,
        context: AgentContext,
        payload: dict,
        config: dict,
    ) -> None:
        start = time.time()
        try:
            await handler(context, payload, config)
            log_event(
                kind="hook",
                namespace=context.namespace,
                turn_id=context.turn_id,
                event=event,
                handler=getattr(handler, "__name__", "?"),
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            log_event(
                kind="hook",
                namespace=context.namespace,
                turn_id=context.turn_id,
                event=event,
                handler=getattr(handler, "__name__", "?"),
                duration_ms=int((time.time() - start) * 1000),
                error=str(e),
            )
