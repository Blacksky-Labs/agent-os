"""llm-interface cell tests (SPEC §5).

The cell must never raise: any failure is recorded to ``cell_errors``. The model
call (``agentos.llm.chat_completion``) is mocked — no network/model required.
"""

from __future__ import annotations

import cells.llm_interface.cell as cell_mod
from cells.llm_interface.cell import Cell


async def test_missing_model_name_records_error(make_context):
    cell = Cell({})
    ctx = make_context()
    ctx.meta["model"] = {}  # no name
    ctx.assembled_prompt = [{"role": "user", "content": "hi"}]
    out = await cell.execute(ctx)
    assert "llm-interface" in out.cell_errors
    assert out.response is None


async def test_empty_prompt_records_error(make_context):
    cell = Cell({})
    ctx = make_context()
    ctx.meta["model"] = {"name": "ollama/llama3.1"}
    ctx.assembled_prompt = []
    out = await cell.execute(ctx)
    assert "llm-interface" in out.cell_errors


async def test_happy_path_sets_response_and_usage(monkeypatch, make_context):
    async def fake_chat(model_cfg, messages, **kwargs):
        assert model_cfg["name"] == "ollama/llama3.1"
        assert messages[-1]["content"] == "hi"
        return {
            "content": "hello world",
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        }

    monkeypatch.setattr(cell_mod, "chat_completion", fake_chat)

    cell = Cell({})
    ctx = make_context()
    ctx.meta["model"] = {"name": "ollama/llama3.1", "temperature": 0.5}
    ctx.assembled_prompt = [{"role": "user", "content": "hi"}]
    out = await cell.execute(ctx)

    assert out.response == "hello world"
    assert out.meta["last_usage"]["total_tokens"] == 7
    assert "llm-interface" not in out.cell_errors


async def test_model_error_is_caught(monkeypatch, make_context):
    async def boom(model_cfg, messages, **kwargs):
        raise ConnectionError("ollama down")

    monkeypatch.setattr(cell_mod, "chat_completion", boom)

    cell = Cell({})
    ctx = make_context()
    ctx.meta["model"] = {"name": "ollama/llama3.1"}
    ctx.assembled_prompt = [{"role": "user", "content": "hi"}]
    out = await cell.execute(ctx)

    assert out.response is None
    assert "ConnectionError" in out.cell_errors["llm-interface"]
