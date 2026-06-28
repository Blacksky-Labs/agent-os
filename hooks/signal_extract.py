"""after_turn hook — the Sentiment Engine's LLM signal pass, in the background.

Runs after the reply is sent (via BackgroundTasks in /chat), so it never adds
latency to the response — it informs the *next* turn. Extracts intent /
sentiment / topics from the user's message and writes the topics straight into
the thread profile (everyday tasks/errands the deterministic pass misses).

Writes topics to threads itself rather than relying on hook ordering, because the
dispatcher fires after_turn handlers in parallel. ``context_update`` owns entities;
this hook owns topics — no double-counting.

Config (manifest hook subscription):
    enabled:    bool       — default True
    deadline_s: float      — default 12.0 (generous; it's off the response path)
    model:      str        — model override; defaults to the entity's model
    guidance:   str        — domain steer
    flags:      list[str]  — extra boolean flags to request

Entity-agnostic. Best-effort: any failure is caught and logged, never user-facing.
"""

from __future__ import annotations

import asyncio
import json
import re

from agentos.context import AgentContext
from agentos.llm import chat_completion
from cells.memory.profile import profile_key, update_threads
from cells.memory.store import init_store

_BASE_SCHEMA = (
    'You extract structured signals from one message a user sent to an AI '
    "assistant. Respond with ONLY a minified JSON object — no prose, no code "
    "fences. Fields: "
    '"intent" (short verb phrase), '
    '"sentiment" {"label": one of positive|neutral|negative, "score": 0-100}, '
    '"topics" (array of short strings — people, projects, orgs, tasks, or concerns), '
    '"is_task" (boolean), "needs_followup" (boolean)'
)


def _parse_json(text: str) -> dict | None:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _charge(sentiment) -> float:
    if not isinstance(sentiment, dict):
        return 0.0
    raw = sentiment.get("emotional_charge", sentiment.get("score"))
    if not isinstance(raw, (int, float)):
        return 0.0
    charge = max(0.0, min(1.0, float(raw) / 100.0))
    if str(sentiment.get("label", "")).lower() in ("negative", "distress"):
        charge = min(1.0, charge + 0.25)
    return charge


async def handle(context: AgentContext, payload: dict, config: dict) -> None:
    if not config.get("enabled", True):
        return
    message = (context.user_message or "").strip()
    if not message:
        return

    model_cfg = dict(context.meta.get("model", {}) or {})
    if config.get("model"):
        model_cfg["name"] = config["model"]
    if not model_cfg.get("name"):
        return

    flags = list(config.get("flags") or [])
    prompt = _BASE_SCHEMA
    if flags:
        prompt += ". Also include booleans: " + ", ".join(f'"{f}"' for f in flags)
    if config.get("guidance"):
        prompt += ". Domain focus: " + config["guidance"]
    prompt += ". If unsure, use neutral defaults."

    deadline = float(config.get("deadline_s", 12.0))
    try:
        result = await asyncio.wait_for(
            chat_completion(
                model_cfg,
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": message[:2000]},
                ],
                temperature=0,
                max_tokens=240,
                timeout=deadline,
            ),
            timeout=deadline,
        )
    except Exception:
        return  # background, best-effort

    parsed = _parse_json(result.get("content") or "")
    if not isinstance(parsed, dict):
        return

    if isinstance(parsed.get("sentiment"), dict):
        context.sentiment = parsed["sentiment"]
    if parsed.get("intent"):
        context.intent = str(parsed["intent"])
    signals = {
        k: parsed[k]
        for k in ("topics", "is_task", "is_commitment", "needs_followup", *flags)
        if k in parsed
    }
    if signals:
        context.extracted_signals["signals"] = signals

    # Write topics straight to the thread profile (this hook owns topics).
    topics = [t for t in (parsed.get("topics") or []) if isinstance(t, str) and t.strip()]
    if topics:
        db_path = await init_store(context.namespace)
        await update_threads(
            db_path,
            profile_key(context),
            [(t, "topic") for t in topics],
            charge=_charge(context.sentiment),
        )
