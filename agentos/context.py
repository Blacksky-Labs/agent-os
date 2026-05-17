"""AgentContext — the single object that flows through the cell pipeline.

See SPEC.md §3 for the full contract.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


def _new_turn_id() -> str:
    return f"t_{uuid.uuid4().hex[:12]}"


@dataclass
class AgentContext:
    """The single object that flows through the cell pipeline.

    Cells read what they need, write what they produce, pass forward.
    No cell knows what other cells exist. The kernel owns ordering.

    Rules of the road:
        - Cells never delete fields populated by upstream cells.
        - A cell that fails records the error to ``cell_errors`` and
          returns the context unchanged. The pipeline does not crash.
        - Hook payloads are derived from the final AgentContext; hooks
          never modify it.
    """

    # --- Identity (kernel sets these at request time) ---
    agent_name: str
    namespace: str
    session_id: str
    turn_id: str = field(default_factory=_new_turn_id)
    user_id: str | None = None

    # --- Mode ---
    mode: str = "web"
    mode_constraints: dict = field(default_factory=dict)

    # --- Persona (loaded once at agent init, propagated per turn) ---
    persona: dict = field(default_factory=dict)

    # --- Incoming ---
    user_message: str = ""

    # --- Memory channels ---
    conversation_history: list[dict] = field(default_factory=list)
    user_profile: dict = field(default_factory=dict)
    semantic_history: list[dict] = field(default_factory=list)

    # --- NLP / ingestion ---
    intent: str | None = None
    entities: list[str] = field(default_factory=list)
    sentiment: dict | None = None
    extracted_signals: dict = field(default_factory=dict)

    # --- Retrieval ---
    retrieved_chunks: list[dict] = field(default_factory=list)
    live_data: dict = field(default_factory=dict)

    # --- Assembly ---
    assembled_prompt: list[dict] = field(default_factory=list)

    # --- LLM output ---
    response: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)

    # --- Observability ---
    cell_timings: dict = field(default_factory=dict)
    cell_errors: dict = field(default_factory=dict)

    # --- Free-form metadata for hooks and downstream ---
    meta: dict = field(default_factory=dict)

    # --- Implicit ---
    created_at: float = field(default_factory=time.time)
