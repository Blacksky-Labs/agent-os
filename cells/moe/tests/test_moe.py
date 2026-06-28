"""MoE activation-protocol tests — the cascade. chat_completion is mocked.

A mock distinguishes the triage call (its system prompt classifies into a lane)
from a generation/dispatch call, so tests can assert *which gate* fired and whether
the tiny triage model was even consulted.
"""

import cells.moe.cell as moe_mod
from agentos.context import AgentContext
from cells.moe.cell import Cell

ROSTER = {
    "router_model": "ollama/gemma4:e2b",
    "default": "general",
    "safety": "seth",
    "experts": [
        {"name": "general", "lane": "general", "description": "everyday"},
        {"name": "seth", "lane": "emotional", "description": "emotional support",
         "model": "ollama/gemma4:e4b", "system": "SETH"},
    ],
}


def make_fake(triage_return="general"):
    calls = []

    async def fake(model_cfg, messages, **kw):
        sys = messages[0]["content"] if messages else ""
        is_triage = "Classify the user's message into ONE lane" in sys
        calls.append({"name": model_cfg.get("name"), "triage": is_triage, "messages": messages})
        if is_triage:
            return {"content": triage_return, "usage": None}
        return {"content": "GEN", "usage": {"total_tokens": 3}}

    return fake, calls


def ctx(msg, flags=None):
    c = AgentContext(agent_name="d", namespace="d", session_id="s", user_message=msg)
    c.meta["model"] = {"name": "ollama/gemma4:e4b", "provider": "ollama", "api_base": "http://localhost:11434"}
    c.assembled_prompt = [{"role": "system", "content": "persona"}, {"role": "user", "content": msg}]
    if flags:
        c.extracted_signals = {"flags": flags}
    return c


async def test_safety_lexicon_skips_triage_to_seth(monkeypatch):
    fake, calls = make_fake("general")
    monkeypatch.setattr(moe_mod, "chat_completion", fake)
    out = await Cell(ROSTER).execute(ctx("honestly I want to kill myself"))
    assert out.meta["moe_tier"] == "safety"
    assert out.meta["route"] == "seth"
    assert not any(c["triage"] for c in calls)                          # never consulted the model to gate
    assert any(m.get("content") == "SETH" for m in calls[0]["messages"])


async def test_crisis_flag_routes_safety(monkeypatch):
    fake, calls = make_fake("general")
    monkeypatch.setattr(moe_mod, "chat_completion", fake)
    out = await Cell(ROSTER).execute(ctx("anything", flags=["crisis_signal"]))
    assert out.meta["moe_tier"] == "safety" and out.meta["route"] == "seth"
    assert not any(c["triage"] for c in calls)


async def test_trigger_forces_expert_skips_triage(monkeypatch):
    fake, calls = make_fake("general")
    monkeypatch.setattr(moe_mod, "chat_completion", fake)
    roster = dict(ROSTER)
    roster["experts"] = [
        {"name": "general", "lane": "general", "description": "everyday"},
        {"name": "code", "lane": "code", "description": "code", "model": "ollama/x",
         "system": "CODE", "triggers": [r"\btraceback\b"]},
    ]
    out = await Cell(roster).execute(ctx("here's a Traceback from my script"))
    assert out.meta["moe_tier"] == "trigger" and out.meta["route"] == "code"
    assert not any(c["triage"] for c in calls)


async def test_triage_routes_emotional_to_seth(monkeypatch):
    fake, calls = make_fake("emotional")
    monkeypatch.setattr(moe_mod, "chat_completion", fake)
    out = await Cell(ROSTER).execute(ctx("had a really hard day, feeling low"))
    assert out.meta["moe_tier"] == "triage" and out.meta["route"] == "seth"
    assert calls[0]["triage"] and calls[0]["name"] == "ollama/gemma4:e2b"   # triage on the tiny model
    assert calls[1]["name"] == "ollama/gemma4:e4b"                          # seth dispatch (own model)
    assert any(m.get("content") == "SETH" for m in calls[1]["messages"])


async def test_triage_general_is_base_path(monkeypatch):
    fake, calls = make_fake("general")
    monkeypatch.setattr(moe_mod, "chat_completion", fake)
    out = await Cell(ROSTER).execute(ctx("what's on my list today"))
    assert out.meta["moe_tier"] == "default" and out.meta["route"] == "general"
    disp = [c for c in calls if not c["triage"]][0]
    assert disp["name"] == "ollama/gemma4:e4b"                              # base entity model
    assert not any(m.get("content") == "SETH" for m in disp["messages"])    # no specialist system


async def test_no_experts_is_single_model(monkeypatch):
    fake, calls = make_fake()
    monkeypatch.setattr(moe_mod, "chat_completion", fake)
    out = await Cell({}).execute(ctx("hi"))
    assert out.response == "GEN" and "moe_tier" not in out.meta
