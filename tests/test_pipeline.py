"""Pipeline executor tests (SPEC §4)."""

from __future__ import annotations

import pytest

from agentos.context import AgentContext
from agentos.pipeline import Pipeline
from agentos.registry import Registry


def _manifest(cells):
    return {"name": "testbot", "namespace": "testns", "cells": cells}


@pytest.fixture
def reg(cells_registry):
    return Registry(cells_registry, "cells")


async def test_cells_run_in_declared_order(reg, make_context):
    p = Pipeline(_manifest([{"name": "echo"}, {"name": "echo"}]), reg)
    ctx = await p.run(make_context())
    assert ctx.meta["ran"] == ["echo", "echo"]


async def test_cell_init_receives_config(reg):
    p = Pipeline(_manifest([{"name": "echo", "config": {"foo": "bar"}}]), reg)
    assert p.cells[0].inited_with == {"foo": "bar"}


async def test_timings_recorded(reg, make_context):
    p = Pipeline(_manifest([{"name": "echo"}]), reg)
    ctx = await p.run(make_context())
    assert "echo" in ctx.cell_timings
    assert isinstance(ctx.cell_timings["echo"], int)


async def test_failing_cell_is_recorded_and_pipeline_continues(reg, make_context):
    p = Pipeline(_manifest([{"name": "boom"}, {"name": "echo"}]), reg)
    ctx = await p.run(make_context())
    # boom recorded an error...
    assert "boom" in ctx.cell_errors
    assert "kaboom" in ctx.cell_errors["boom"]
    # ...but echo still ran afterward (graceful degradation, no hard crash)
    assert ctx.meta["ran"] == ["echo"]


async def test_module_without_cell_class_raises_at_load(reg):
    with pytest.raises(RuntimeError, match="no `Cell` class"):
        Pipeline(_manifest([{"name": "noclass"}]), reg)


async def test_teardown_calls_each_cell(reg):
    p = Pipeline(_manifest([{"name": "echo"}]), reg)
    cell = p.cells[0]
    await p.teardown()
    assert cell.torn_down is True


async def test_run_returns_same_context_object(reg, make_context):
    p = Pipeline(_manifest([{"name": "echo"}]), reg)
    ctx_in = make_context()
    ctx_out = await p.run(ctx_in)
    assert ctx_out is ctx_in
