"""Hook dispatcher tests (SPEC §7)."""

from __future__ import annotations

import sys
import types

import pytest

from agentos.hooks import HookDispatcher


@pytest.fixture
def hook_module(monkeypatch):
    """Install a fake ``hooks.spy`` module with a recording handler."""
    calls: list[dict] = []

    async def handle(context, payload, config):
        if config.get("explode"):
            raise RuntimeError("handler blew up")
        calls.append({"payload": payload, "config": config, "ns": context.namespace})

    mod = types.ModuleType("hooks.spy")
    mod.handle = handle
    monkeypatch.setitem(sys.modules, "hooks.spy", mod)
    return calls


async def test_handler_fires_on_event(hook_module, make_context):
    d = HookDispatcher({"after_turn": [{"handler": "spy"}]})
    await d.fire("after_turn", make_context(), {"x": 1})
    assert hook_module == [{"payload": {"x": 1}, "config": {}, "ns": "testns"}]


async def test_unknown_event_is_ignored(make_context):
    d = HookDispatcher({"not_a_real_event": [{"handler": "spy"}]})
    # Should not register anything; firing a real event is a no-op.
    await d.fire("after_turn", make_context())  # no raise


async def test_missing_handler_module_does_not_register(make_context):
    d = HookDispatcher({"after_turn": [{"handler": "does_not_exist"}]})
    # Firing is a safe no-op even though the handler failed to load.
    await d.fire("after_turn", make_context())


async def test_handler_failure_is_isolated(hook_module, make_context):
    d = HookDispatcher({"after_turn": [{"handler": "spy", "config": {"explode": True}}]})
    # Dispatcher swallows handler exceptions — never propagates to caller.
    await d.fire("after_turn", make_context())
    assert hook_module == []


async def test_fire_with_no_subscribers_is_noop(make_context):
    d = HookDispatcher({})
    await d.fire("after_turn", make_context())


async def test_handler_config_passed_through(hook_module, make_context):
    d = HookDispatcher(
        {"after_turn": [{"handler": "spy", "config": {"channel": "email"}}]}
    )
    await d.fire("after_turn", make_context(), {})
    assert hook_module[0]["config"] == {"channel": "email"}
