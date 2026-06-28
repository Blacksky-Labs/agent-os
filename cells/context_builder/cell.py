"""context-builder cell — v1.3.0.

Assembles the LLM prompt from the persona, mode constraints, retrieved
corpus chunks, conversation history, and the current user message.
Pure assembly — no I/O, no LLM calls, no side effects.

v1.3.0 vs v1.2.1:
    - Context Engine: renders ``context.user_profile['threads']`` — the
      subjects the user keeps returning to (recurrence/charge-weighted) — into
      the system prompt, so the entity surfaces continuity instead of starting
      cold each session.

v1.2.1 vs v1.2.0:
    - Anti-recap: the closing anchor now tells the model to reply only with
      its next message and never restate/quote/continue its earlier replies.
      Fixes small local models (e.g. gemma3:4b) compounding their own prior
      answers turn over turn (each reply swallowing the last).

v1.2.0 vs v1.1.0:
    - System prompt now includes a "Reference material" section with
      retrieved corpus chunks when the retrieval cell populated
      ``context.retrieved_chunks``.
    - Chunks render with source attribution and similarity score so the
      LLM can cite them by file.
    - Closing anchor extended to ask the model to cite source filenames
      when it uses reference material.

v1.1.0 vs v1.0.0:
    - System prompt uses the full persona schema (identity, mission,
      voice, refusals, escalations) — not just ``mission``.
    - Pulls mode constraints from ``context.mode_constraints``.
    - Threads ``context.conversation_history`` between system and user.
    - Anti-drift "stay in character" anchor.

See SPEC.md §5 (cell contract) and §8 (persona format).
"""

from __future__ import annotations

from agentos.context import AgentContext


class Cell:
    name = "context-builder"
    version = "1.3.1"

    def __init__(self, config: dict):
        self.config = config or {}
        self.surface_threads = bool(self.config.get("surface_threads", True))

    def init(self, config: dict) -> None:
        pass

    async def execute(self, context: AgentContext) -> AgentContext:
        system_content = _build_system_prompt(
            persona=context.persona or {},
            agent_name=context.agent_name,
            mode_constraints=context.mode_constraints or {},
            retrieved_chunks=context.retrieved_chunks or [],
            user_profile=context.user_profile or {},
            surface_threads=self.surface_threads,
        )

        messages: list[dict] = [{"role": "system", "content": system_content}]

        # Prior turns — memory cell populates these.
        for turn in context.conversation_history or []:
            role = turn.get("role")
            content = turn.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        # Current user message
        messages.append({"role": "user", "content": context.user_message})

        context.assembled_prompt = messages
        return context

    async def teardown(self) -> None:
        pass


# ----------------------------------------------------------------------
# System-prompt assembly
# ----------------------------------------------------------------------

PLACEHOLDER_MISSIONS: frozenset[str] = frozenset({
    "",
    "(fill in later)",
})


def _build_system_prompt(
    persona: dict,
    agent_name: str,
    mode_constraints: dict,
    retrieved_chunks: list[dict],
    user_profile: dict | None = None,
    surface_threads: bool = True,
) -> str:
    """Render persona + mode constraints + retrieved chunks into a system prompt."""
    sections: list[str] = []

    # --- 1. Identity ---
    name = (
        persona.get("display_name")
        or persona.get("name")
        or agent_name
    )
    sections.append(f"You are {name}.")

    # --- 2. Mission ---
    mission = (persona.get("mission") or "").strip()
    if mission.lower() not in PLACEHOLDER_MISSIONS:
        sections.append(mission)

    # --- 3. Voice ---
    voice = persona.get("voice", {}) or {}
    voice_lines: list[str] = []
    if voice.get("tone"):
        voice_lines.append(f"Tone: {voice['tone']}.")
    if voice.get("formality"):
        voice_lines.append(f"Formality: {voice['formality']}.")
    emojis = voice.get("emojis")
    if emojis == "never":
        voice_lines.append("Never use emoji.")
    elif emojis == "sparing":
        voice_lines.append("Use emoji sparingly, only when clearly helpful.")
    catchphrases = voice.get("catchphrases", []) or []
    if catchphrases:
        joined = "; ".join(f'"{c}"' for c in catchphrases)
        voice_lines.append(f"Lines you naturally say: {joined}.")
    if voice_lines:
        sections.append("Voice: " + " ".join(voice_lines))

    # --- 4. Format constraints from the current mode ---
    fmt_lines: list[str] = []
    if "max_words" in mode_constraints:
        fmt_lines.append(
            f"Keep responses under {mode_constraints['max_words']} words."
        )
    if mode_constraints.get("markdown") is False:
        fmt_lines.append("Do not use markdown formatting.")
    if mode_constraints.get("no_lists"):
        fmt_lines.append("Avoid bullet or numbered lists.")
    if fmt_lines:
        sections.append("Format: " + " ".join(fmt_lines))

    # --- 4b. Context Engine: ongoing threads ---
    threads = (user_profile or {}).get("threads") or []
    if surface_threads and threads:
        thread_lines = [
            "Ongoing threads — subjects this person keeps returning to. "
            "Reference them naturally when relevant; do not list them back:"
        ]
        for t in threads[:8]:
            mentions = t.get("mentions")
            suffix = f" ({mentions}×)" if isinstance(mentions, int) and mentions > 1 else ""
            thread_lines.append(f"- {t.get('key')}{suffix}")
        sections.append("\n".join(thread_lines))

    # --- 5. Reference material (retrieved chunks) ---
    if retrieved_chunks:
        ref_lines = ["Reference material from the corpus (cite sources when you use them):"]
        for c in retrieved_chunks:
            source = c.get("source") or "unknown"
            short = _short_source(source)
            sim = c.get("similarity")
            sim_str = f", similarity {sim:.2f}" if isinstance(sim, (int, float)) else ""
            ref_lines.append(f"\n[Source: {short}{sim_str}]\n{c.get('content', '').strip()}")
        sections.append("\n".join(ref_lines))

    # --- 6. Refusal rules ---
    refusal_lines: list[str] = []
    for r in (persona.get("refusals") or []):
        topic = r.get("topic")
        response = r.get("response")
        if topic and response:
            refusal_lines.append(f"If asked about {topic}, respond: {response}")
    if refusal_lines:
        sections.append(
            "Refusal rules:\n" + "\n".join(f"- {line}" for line in refusal_lines)
        )

    # --- 7. Escalation triggers ---
    escalation_lines: list[str] = []
    for e in (persona.get("escalations") or []):
        condition = e.get("condition")
        action = e.get("action")
        if condition and action:
            escalation_lines.append(f"When {condition}, signal {action}.")
    if escalation_lines:
        sections.append(
            "Escalation triggers:\n"
            + "\n".join(f"- {line}" for line in escalation_lines)
        )

    # --- 8. Anti-drift anchor (extended for reference material) ---
    anchor = (
        "Stay in character. Do not break the fourth wall or invent a "
        "different persona unless the user directly asks for one. "
        "Reply only with your next message in response to the most recent "
        "user turn. Never restate, quote, or continue your earlier replies — "
        "the conversation above is context, not something to repeat."
    )
    if retrieved_chunks:
        anchor += (
            " When you use any reference material, cite the source "
            "filename inline. If the corpus doesn't cover a question, "
            "say so plainly rather than inventing facts."
        )
    sections.append(anchor)

    return "\n\n".join(sections)


def _short_source(source: str) -> str:
    """Trim a full path to just the filename for compact citation."""
    if "/" in source:
        return source.rsplit("/", 1)[-1]
    return source
