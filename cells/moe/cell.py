"""moe cell — v1.1.0 — Mixture-of-Experts reasoning with the activation protocol.

Implements the cheap-by-default cascade from agentos-moe-protocol.md (v0). A turn
exits at the first gate that resolves it:

    tier 1  safety   — synchronous deterministic lexicon (+ crisis_signal flag);
                       routes to the safety lane and short-circuits. Never gated
                       behind a model.
    tier 2  triggers — experts' declared regex / signal conditions force-activate
                       them, for free. (no-op until a roster declares triggers)
    tier 3  similarity — embedding gate (off in v0; config hook only)
    tier 4  triage   — ONE tiny model classifies the turn into a lane.
    tier 5  default  — no expert; the base model answers directly.

An activated expert REPLACES the base generation (it *is* the generation), so a
triaged turn costs triage(tiny) + expert — never a doubled generation. Default and
deterministic paths add zero model calls.

Config (manifest / overlay):
    router_model:  the tiny triage model (defaults to the entity model)
    default:       lane/expert name meaning "no specialist" → base path
    safety:        expert name that handles tier-1 safety (optional)
    safety_extra:  extra regex added to the OS safety lexicon (optional)
    similarity:    enable tier-3 (off in v0)
    experts:       [{name, description, model?, system?, lane?, triggers?, signals?, priority?,
                     api_base?, provider?, api_key?}]

Writes context.response, meta["last_usage"], meta["route"] (expert name or default),
and meta["moe_tier"] (which gate fired). Never raises (SPEC §4).
"""

from __future__ import annotations

import re

from agentos.context import AgentContext
from agentos.llm import chat_completion

DEFAULT_TIMEOUT_S = 60.0

# OS-level base safety lexicon (agentos-moe-protocol.md §1/§10). Conservative,
# high-signal crisis / self-harm expressions evaluated synchronously on the raw
# message. Per-entity additions go through the `safety_extra` config. Routing a
# false positive to the gentler support lane is harmless; missing a real one is not.
_SAFETY_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"\bkill(?:ing)?\s+my\s*self\b",
        r"\bend(?:ing)?\s+my\s+life\b",
        r"\btake\s+my\s+own\s+life\b",
        r"\bend\s+it\s+all\b",
        r"\bsuicid(?:e|al)\b",
        r"\bself[\s-]?harm\b",
        r"\b(?:hurt|cut)(?:ting)?\s+my\s*self\b",
        r"\b(?:want|wanna|wanting)\s+to\s+die\b",
        r"\bdon'?t\s+want\s+to\s+(?:be\s+here|live)\b",
        r"\bno\s+reason\s+to\s+live\b",
        r"\bbetter\s+off\s+dead\b",
        r"\bcan'?t\s+(?:go\s+on|keep\s+going)\b",
        r"\boverdose\b",
    )
]


class Cell:
    name = "moe"
    version = "1.1.0"

    def __init__(self, config: dict):
        self.config = config or {}
        self.experts: list[dict] = list(self.config.get("experts") or [])
        self.router_model = self.config.get("router_model")
        self.default_expert = self.config.get("default")
        self.safety_lane = self.config.get("safety")
        self.similarity_enabled = bool(self.config.get("similarity"))
        self.router_timeout = float(self.config.get("router_timeout_s", 10.0))

        self._safety = list(_SAFETY_PATTERNS)
        for p in self.config.get("safety_extra") or []:
            try:
                self._safety.append(re.compile(p, re.I))
            except re.error:
                pass

        # Per-expert trigger patterns, kept out of the expert dicts so the manifest
        # stays JSON-serializable for the config page.
        self._triggers: dict[str, list] = {}
        for e in self.experts:
            pats = []
            for p in e.get("triggers") or []:
                try:
                    pats.append(re.compile(p, re.I))
                except re.error:
                    pass
            if pats:
                self._triggers[e.get("name")] = pats

    def init(self, config: dict) -> None:
        pass

    async def execute(self, context: AgentContext) -> AgentContext:
        model_cfg = context.meta.get("model", {}) or {}
        if not context.assembled_prompt:
            context.cell_errors[self.name] = (
                "context.assembled_prompt empty — did context-builder run?"
            )
            return context

        # No roster → behave like a single model.
        if not self.experts:
            return await self._respond(context, model_cfg, context.assembled_prompt)

        expert, tier = await self._select(context, model_cfg)
        context.meta["moe_tier"] = tier

        # tier 5 default — no expert; base model answers.
        if expert is None:
            context.meta["route"] = self.default_expert or "default"
            return await self._respond(context, model_cfg, context.assembled_prompt)

        context.meta["route"] = expert.get("name")
        expert_cfg = dict(model_cfg)
        if expert.get("model"):
            expert_cfg["name"] = expert["model"]
        for k in ("api_base", "provider", "api_key"):
            if expert.get(k) is not None:
                expert_cfg[k] = expert[k]
        messages = list(context.assembled_prompt)
        if expert.get("system"):
            at = 1 if messages and messages[0].get("role") == "system" else 0
            messages.insert(at, {"role": "system", "content": expert["system"]})
        return await self._respond(context, expert_cfg, messages)

    # --- the cascade ---------------------------------------------------------

    async def _select(self, context: AgentContext, model_cfg: dict) -> tuple[dict | None, str]:
        # tier 1 — safety (synchronous; never behind a model)
        if self._safety_hit(context):
            return self._expert_named(self.safety_lane), "safety"
        # tier 2 — deterministic triggers (free)
        hits = [e for e in self.experts if self._triggers_match(e, context)]
        if hits:
            return self._highest_priority(hits), "trigger"
        # tier 3 — similarity (off in v0)
        # tier 4 — triage (one tiny-model call)
        try:
            lane = await self._triage(context, model_cfg)
        except Exception as ex:
            context.meta.setdefault("moe_notes", []).append(f"triage failed: {type(ex).__name__}")
            lane = None
        if lane:
            e = self._expert_for_lane(lane)
            if e and e.get("name") != self.default_expert:
                return e, "triage"
        # tier 5 — default
        return None, "default"

    def _safety_hit(self, context: AgentContext) -> bool:
        flags = (context.extracted_signals or {}).get("flags") or []
        if "crisis_signal" in flags:
            return True
        text = context.user_message or ""
        return any(p.search(text) for p in self._safety)

    def _triggers_match(self, expert: dict, context: AgentContext) -> bool:
        text = context.user_message or ""
        if any(p.search(text) for p in self._triggers.get(expert.get("name"), [])):
            return True
        want = (expert.get("signals") or {}).get("flags") or []
        if want:
            have = set((context.extracted_signals or {}).get("flags") or [])
            if any(f in have for f in want):
                return True
        return False

    def _highest_priority(self, experts: list[dict]) -> dict:
        return max(experts, key=lambda e: e.get("priority", 0))

    def _expert_named(self, name: str | None) -> dict | None:
        if not name:
            return None
        return next((e for e in self.experts if e.get("name") == name), None)

    def _expert_for_lane(self, lane: str) -> dict | None:
        key = (lane or "").strip().lower()
        for e in self.experts:
            if (e.get("lane") or e.get("name", "")).lower() == key:
                return e
        return next((e for e in self.experts if e.get("name", "").lower() == key), None)

    async def _triage(self, context: AgentContext, model_cfg: dict) -> str | None:
        lanes = [(e.get("lane") or e.get("name"), e.get("description", "")) for e in self.experts]
        roster = "\n".join(f"- {ln}: {desc}" for ln, desc in lanes)
        cfg = dict(model_cfg)
        if self.router_model:
            cfg["name"] = self.router_model
        result = await chat_completion(
            cfg,
            [
                {
                    "role": "system",
                    "content": (
                        "Classify the user's message into ONE lane.\n"
                        f"Lanes:\n{roster}\n"
                        "Reply with ONLY the lane name, nothing else."
                    ),
                },
                {"role": "user", "content": (context.user_message or "")[:1000]},
            ],
            temperature=0,
            max_tokens=8,
            timeout=self.router_timeout,
        )
        choice = (result.get("content") or "").strip().lower()
        for ln, _ in lanes:
            if ln and ln.lower() in choice:
                return ln
        return None

    async def _respond(self, context: AgentContext, model_cfg: dict, messages: list[dict]) -> AgentContext:
        try:
            result = await chat_completion(
                model_cfg, messages, timeout=model_cfg.get("timeout", DEFAULT_TIMEOUT_S)
            )
            context.response = result.get("content")
            if result.get("usage"):
                context.meta["last_usage"] = result["usage"]
        except Exception as e:
            context.cell_errors[self.name] = f"{type(e).__name__}: {e}"
            context.response = None
        return context

    async def teardown(self) -> None:
        pass
