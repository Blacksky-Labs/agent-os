# AgentOS Specification — v0.1

*Blacksky LLC | Foundation Infrastructure*

---

## 0. Status & Scope

**Draft.** Foundation-only. Agent-agnostic.

This document specifies the AgentOS kernel and the v1 cell library. It does not specify any particular agent. Stan, Maurice, Judy, Ife, and every future agent run on agentOS as personas; nothing in this document is written *for* them.

**v0.1 covers:**
- Kernel: pipeline, registry, configuration, lifecycle
- Cell library v1: six cell specifications
- Tool registry and contract
- Hook system
- Persona format
- Manifest format
- Namespace isolation
- Observability primitives
- Directory layout
- Versioning policy

**v0.1 does not cover:**
- Any specific agent's design, persona, or tools
- Front-end surfaces (web chat widget, admin dashboards, phone integrations)
- Deployment topology (Docker images, hosting, scaling)
- Streaming responses (deferred; v0.1 is request/response)
- Authentication / authorization (handled by the agent's HTTP surface, not agentOS)
- Distributed deployment across multiple hosts
- Remote cell installation (Drupal/npm-style registry); v0.1 is local-only

---

## 1. Vocabulary

The OS is described with exactly six terms. Every contributor uses them the same way.

**Cell** — a versioned, swappable module implementing the AgentOS Cell interface (`init`, `execute`, `teardown`). Takes an `AgentContext`, returns an `AgentContext`. Pure functions, no side effects, no I/O outside its declared config. Domain-agnostic — `memory` does not know one agent from another. Analog: a Drupal module, an npm package.

**Tool** — a callable function the LLM invokes during inference via tool-use. Typed signature, versioned, declared in the agent's manifest. Lives in `tools.registry.yaml` parallel to cells. Executed by the `llm_interface` cell during a tool-use loop. Never *is* a cell. Analog: a Drupal API plugin, an npm utility package.

**Hook** — a named event that fires around pipeline phases. Handlers run *outside* the cell pipeline and own all side effects (sending email, firing webhooks, writing telemetry, post-turn DB writes). Agents subscribe to hooks in their manifest. Analog: Drupal's `hook_X` system, npm lifecycle scripts, GitHub Actions events.

**Persona** — the data that gives an agent its voice, mission, refusal patterns, and escalation rules. Lives in `persona.yaml`, referenced by the agent manifest. Consumed by `context_builder` and `mode_control`. Never hardcoded in cell code or prompt strings. Analog: a Drupal theme, system-prompt-as-data.

**Manifest** — the `<agent>.yaml` file that fully specifies one runnable agent: name, version, namespace, persona reference, cell list with versions and config, tool list with versions and config, hook subscriptions, model config. One manifest equals one agent. Analog: `package.json`, Drupal module's `info.yml`, `Cargo.toml`.

**Namespace** — the isolation scope for one agent's state across shared infrastructure. Every agent owns its own user records, RAG collections, tool credentials, session keys, and telemetry stream. Enforced by the kernel, declared once in the manifest, propagated to every cell via `AgentContext`. Analog: tenant ID in multi-tenant SaaS, npm scope (`@blacksky/maurice`), Drupal site within a multi-site.

**Deliberately not in the vocabulary:** *skill* (overlaps with tool and adds confusion), *plugin* (too generic; Drupal claims it), *module* (Drupal claims it; we use *cell* so the biology metaphor stays consistent).

---

## 2. Architecture Overview

```
                    Manifest (<agent>.yaml)
                            │
                            ▼
                   ┌────────────────────┐
                   │       Kernel       │
                   │  loads manifest,   │
                   │  builds pipeline,  │
                   │  enforces namespace│
                   └────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
      Cells              Tools                Hooks
   (pure, ordered)   (LLM-callable)      (side effects)
        │                   │                   │
        └───── AgentContext ─┴───── flows ──────┘
                            │
                       HTTP response
```

**One sentence:** an agent is a manifest; the manifest names a persona, declares which cells run in what order with what config, declares which tools the LLM can invoke, and subscribes to which hooks; the kernel loads the manifest, instantiates the pipeline, executes a turn, fires the hooks, and returns.

**Three invariants:**
1. Cells are pure functions of `AgentContext`. Side effects live in hooks.
2. The kernel knows nothing about any specific agent. Agent-specific behavior is fully specified by the manifest and persona.
3. Namespace propagates everywhere. No cross-namespace reads or writes, ever.

---

## 3. The AgentContext

The single object that flows through the cell pipeline.

```python
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class AgentContext:

    # Identity (set by kernel at request time)
    agent_name: str
    namespace: str                          # = manifest.namespace
    session_id: str
    turn_id: str                            # unique per turn
    user_id: str | None = None

    # Mode (set by mode_control)
    mode: str = "web"                       # web | phone | embedded | api
    mode_constraints: dict = field(default_factory=dict)

    # Persona (loaded once at agent init, passed in via meta)
    persona: dict = field(default_factory=dict)

    # Incoming
    user_message: str = ""

    # Memory channels (memory cell fills these)
    conversation_history: list[dict] = field(default_factory=list)
    user_profile: dict = field(default_factory=dict)
    semantic_history: list[dict] = field(default_factory=list)

    # NLP channels (ingestion + context_builder fill these)
    intent: str | None = None
    entities: list[str] = field(default_factory=list)
    sentiment: dict | None = None
    extracted_signals: dict = field(default_factory=dict)

    # Retrieval
    retrieved_chunks: list[dict] = field(default_factory=list)
    live_data: dict = field(default_factory=dict)

    # Assembly
    assembled_prompt: list[dict] = field(default_factory=list)

    # LLM output
    response: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)

    # Observability
    cell_timings: dict = field(default_factory=dict)
    cell_errors: dict = field(default_factory=dict)

    # Free-form metadata for hooks and downstream
    meta: dict = field(default_factory=dict)
```

**Rules of the road:**
- Cells read fields they need, write fields they produce, pass forward.
- Cells never delete fields populated by upstream cells.
- A cell that fails records the error to `cell_errors` and returns the context unchanged. The pipeline does not crash.
- Hook payloads are derived from the final `AgentContext`; hooks never modify it.

---

## 4. The Cell Contract

```python
class AgentOSCell:
    name: str           # kebab-case, matches registry key
    version: str        # SemVer

    def __init__(self, config: dict) -> None: ...
    def init(self, config: dict) -> None: ...
    async def execute(self, context: AgentContext) -> AgentContext: ...
    async def teardown(self) -> None: ...
```

**Lifecycle:**
- `__init__(config)` — called when the cell is loaded into a pipeline. Stash config, do nothing expensive.
- `init(config)` — called once after instantiation. Open connections, warm caches, load models.
- `execute(context)` — called once per turn. Must be idempotent if called twice with the same context.
- `teardown()` — called on agent unload. Close connections, flush state.

**Hard rules:**
- All execution is async.
- No raw exceptions out of `execute()`. Catch and write to `context.cell_errors`.
- No reaching outside declared config (no global state, no env vars beyond what the kernel passes in).
- No knowledge of any other cell. If cell B's output is needed, that's the pipeline's job to order, not cell A's to fetch.
- No agent-specific identifiers. No `if agent_name == "maurice"` anywhere, ever.

**Determinism:**
A cell's behavior is determined by its config (set at load) and its input `AgentContext` (set at turn). Two cells of the same version with the same config and the same input must produce the same output, modulo external I/O (LLM calls, DB reads).

---

## 5. Cell Library v1

The six cells that ship with agentOS v0.1. Each is a one-paragraph contract. Implementations are mined from existing best-of-breed code in Maurice and Judy; the cells *are* canonical going forward.

**`mode-control`** — reads `context.mode` and the persona's mode preferences; writes `context.mode_constraints` (max response length, allowed formatting, expected output shape). Modes in v0.1: `web` (full responses, markdown ok), `phone` (short, no markdown, voice-optimized), `embedded` (scoped, rate-checked), `api` (raw, no formatting).

**`memory`** — hydrates `context.conversation_history`, `context.user_profile`, and `context.semantic_history` from the persistence layer scoped by `context.namespace`. After the turn completes, the kernel calls memory's append paths via a hook (`after_turn`), not in-line; memory writes are side effects. Reference implementation backed by tiered storage (hot session store + warm relational DB); the spec does not prescribe the backend.

**`ingestion`** — parses `context.user_message`, runs lightweight deterministic extractors (regex for entities, emails, phones, structured references), and dispatches optional parallel LLM extractors (sentiment, signals) that race with a deadline. Writes to `context.entities`, `context.sentiment`, `context.extracted_signals`. Pure within the cell; the parallel LLM tasks are owned by the cell and time-boxed.

**`retrieval`** — uses `context.user_message` (and optionally `context.intent`) to query vector stores and structured lookups, all scoped by `context.namespace`. Writes `context.retrieved_chunks` (RAG results with source attribution) and `context.live_data` (typed lookups). Reference implementation supports multiple collections per namespace (one corpus per domain).

**`context-builder`** — consumes everything memory, ingestion, and retrieval produced, plus the persona, and produces `context.assembled_prompt`: an ordered list of role-tagged messages ready for the LLM. The persona's voice, mission, refusal patterns, and escalation rules are injected here. This cell is where the prompt template lives — *not* in a `prompts.py` per agent. Templates are parameterized by persona fields.

**`llm-interface`** — reads `context.assembled_prompt` and the manifest's model config; calls the model via LiteLLM; if the manifest declares tools, runs a tool-use loop (model emits tool call → llm-interface dispatches via tool registry → result back into the loop → model continues) until the model emits a terminal message; writes `context.response`, `context.tool_calls`, `context.tool_results`.

**Order of execution in v0.1:** `mode-control` → `memory` → `ingestion` → `retrieval` → `context-builder` → `llm-interface`. The manifest may reorder or add/remove cells; the kernel does not enforce this order, only the contract.

---

## 6. The Tool Contract

```python
class AgentOSTool:
    name: str                 # kebab-case, matches registry key
    version: str              # SemVer
    description: str          # natural language; shown to the LLM
    parameters: dict          # JSON Schema for arguments

    def __init__(self, config: dict) -> None: ...
    async def init(self, config: dict) -> None: ...
    async def execute(self, args: dict, namespace: str) -> dict: ...
    async def teardown(self) -> None: ...
```

**Rules:**
- Declared in `tools.registry.yaml`.
- Referenced by the manifest with a version constraint.
- Receives `namespace` at execute time for credential scoping and data isolation.
- Returns a JSON-serializable dict.
- Errors are returned as `{"success": false, "error": "..."}`, never raised.
- The LLM sees `name`, `description`, and `parameters`; the agentOS kernel handles dispatch.

**Tools vs. cells:**
- Cells run on every turn, in order, regardless of what the user asked.
- Tools run only when the model decides to call one, mid-inference.
- A cell may not call a tool. A tool may not call a cell. Both communicate only via `AgentContext` and the LLM's tool-use loop.

---

## 7. The Hook Contract

A hook is a named event the kernel fires at known points in the request lifecycle. Hook handlers are registered functions that agents subscribe to in their manifest. Handlers receive `(context, payload, config)` and return nothing meaningful — they exist for side effects.

**Hook event types, v0.1:**
- `before_turn` — fires before the cell pipeline runs
- `after_turn` — fires after the cell pipeline completes, before the response returns
- `on_cell_error` — fires when any cell records an error
- `on_tool_call` — fires for every tool invocation (audit trail)
- `on_high_intent` — fires when ingestion or context-builder flags high engagement (signal in `context.extracted_signals`)
- `on_lead_scored` — fires when a lead score is computed and crosses a threshold
- `on_conversation_end` — fires when a session is closed

**Handler signature:**
```python
async def handle(context: AgentContext, payload: dict, config: dict) -> None: ...
```

**Manifest subscription example:**
```yaml
hooks:
  after_turn:
    - handler: log_audit_trail
      config: { sink: stdout }
  on_lead_scored:
    - handler: send_email_alert
      config: { threshold: 4, to: mario@blacksky.com }
```

**Rules:**
- Hooks are fired in registration order per event; failure of one handler does not prevent others.
- Hook handlers run after the response has been returned to the client (post-turn hooks) or before the pipeline starts (pre-turn hooks). They never block the user-facing response path beyond a short deadline.
- The kernel times every hook and records the duration in observability.

---

## 8. Persona Format

```yaml
# persona.yaml
name: maurice
display_name: Maurice
mission: |
  Qualify sales leads for Blacksky LLC. Answer questions about
  services and projects. Capture contact info when appropriate.

voice:
  tone: dry-wit
  formality: casual
  emojis: never
  catchphrases:
    - "We've shipped that."
    - "Federal projects are our gym."

modes:
  web:
    max_words: 250
    markdown: true
  phone:
    max_words: 60
    markdown: false
    no_lists: true
  api:
    max_words: 500
    markdown: false

refusals:
  - topic: specific_pricing
    response: I can connect you with Mario for a quote.
  - topic: competitor_disparagement
    response: I'll let our work speak for itself.

escalations:
  - condition: user_asks_for_human
    action: hand_off
  - condition: lead_score_gte_4
    action: alert_mario
```

**Rules:**
- Persona is data. No code in the yaml beyond declarative fields.
- The persona schema is open; cells reference fields by path (`persona.voice.tone`).
- Unknown fields are tolerated; cells that don't need a field ignore it.

---

## 9. Manifest Format

```yaml
# <agent>.yaml
name: maurice
version: 1.0.0
namespace: maurice
persona: ./personas/maurice.yaml

cells:
  - name: mode-control
    version: ^1.0
  - name: memory
    version: ^1.0
    config:
      hot_store: redis
      cold_store: postgres
  - name: ingestion
    version: ^1.0
    config:
      parallel_signals: [sentiment, contact_fields]
  - name: retrieval
    version: ^1.0
    config:
      collections: [company_docs]
  - name: context-builder
    version: ^1.0
  - name: llm-interface
    version: ^1.0

tools:
  - name: research-company
    version: ^1.0
  - name: lookup-user-context
    version: ^1.0

hooks:
  after_turn:
    - handler: log_audit_trail
      config: { sink: stdout }
  on_lead_scored:
    - handler: send_email_alert
      config: { threshold: 4, to: mario@blacksky.com }

model:
  provider: together
  name: meta-llama/Llama-3.1-70B-Instruct
  temperature: 0.5
  max_tokens: 1024
```

**Rules:**
- Every field below `name` and `version` is optional. Cells, tools, hooks all default to empty lists.
- Cell ordering in the manifest determines pipeline execution order.
- A manifest that references a cell or tool not in the registry fails to load; the kernel refuses to start the agent.

---

## 10. Namespace Enforcement

Namespace is the kernel's single biggest job after pipeline orchestration.

**How it propagates:**
- Set once: `manifest.namespace`.
- Loaded by the kernel into every `AgentContext` it creates.
- Passed to every cell via `context.namespace`.
- Passed to every tool via the `namespace` argument on `execute(args, namespace)`.
- Tagged onto every log line, metric, and trace.

**What it scopes:**
- Memory cell reads and writes — user records, session state, conversation history, semantic facts.
- Retrieval cell vector queries — RAG collections are namespaced (`<namespace>__docs`, `<namespace>__corpus`, etc.).
- Tool credentials — tools read `namespace`-scoped keys from a secrets backend.
- Telemetry — every emitted event carries the namespace.

**Hard rule:** no cell or tool may read or write data in a namespace other than the one in its current `AgentContext`. There is no cross-agent state access. If two agents need to share data, they share it via an external system (a database one queries via a tool), never via the kernel.

---

## 11. Observability Primitives

Every cell, tool, and hook emits structured telemetry. v0.1 ships stdout JSON; the sink is configurable.

**Per-cell event:**
```json
{
  "ts": "2026-05-17T14:32:01.123Z",
  "kind": "cell",
  "namespace": "maurice",
  "agent": "maurice",
  "turn_id": "t_abc123",
  "cell": "retrieval",
  "version": "1.0.0",
  "duration_ms": 142,
  "error": null
}
```

**Per-tool event:**
```json
{
  "ts": "...", "kind": "tool", "namespace": "maurice",
  "turn_id": "t_abc123", "tool": "research-company",
  "version": "1.0.0", "duration_ms": 1820, "args_hash": "sha256:...",
  "error": null
}
```

**Per-hook event:**
```json
{
  "ts": "...", "kind": "hook", "namespace": "maurice",
  "turn_id": "t_abc123", "event": "on_lead_scored",
  "handler": "send_email_alert", "duration_ms": 312, "error": null
}
```

**Rules:**
- Never log secrets, tokens, full prompts, full responses, or user PII at default verbosity.
- `args_hash` is a SHA-256 of the canonical JSON of the args, not the args themselves.
- A debug-level log can include full payloads, gated by the manifest's log level.
- Every event carries `turn_id` so a full turn can be reconstructed from logs alone.

---

## 12. Directory Layout

```
agentOS/
├── SPEC.md                       # this document
├── LESSONS.md                    # what we learned that justifies the spec
├── README.md                     # how to run
├── pyproject.toml                # package metadata
│
├── agentos/                      # kernel (Python package: `agentos`)
│   ├── __init__.py
│   ├── context.py                # AgentContext dataclass
│   ├── pipeline.py               # cell pipeline executor
│   ├── registry.py               # cell + tool registries
│   ├── config.py                 # manifest loader & validator
│   ├── hooks.py                  # hook dispatcher
│   ├── observability.py          # structured logging + metrics
│   ├── cli.py                    # `agentos` command-line entry point
│   └── main.py                   # FastAPI entry, /chat endpoint
│
├── cells/                        # cell library v1
│   ├── mode_control/
│   │   ├── __init__.py
│   │   ├── cell.py
│   │   ├── tests/
│   │   └── README.md
│   ├── memory/
│   ├── ingestion/
│   ├── retrieval/
│   ├── context_builder/
│   └── llm_interface/
│
├── tools/                        # tool library (populated by agents over time)
│   └── _template/                # SDK template
│
├── hooks/                        # hook handler library
│   ├── log_audit_trail.py
│   ├── send_email_alert.py
│   └── ...
│
├── personas/                     # shared persona components (optional)
│
├── manifests/                    # agent manifests live here
│   ├── stan.yaml
│   ├── maurice.yaml
│   └── judy.yaml
│
├── cells.registry.yaml           # cell registry
├── tools.registry.yaml           # tool registry
└── tests/                        # cross-cell integration tests
```

---

## 13. Versioning Policy

**SemVer everywhere.** Cells and tools both use `MAJOR.MINOR.PATCH`.

- **MAJOR** bumps when the cell's contract changes — new required `AgentContext` field, removed field, changed interface, breaking config schema.
- **MINOR** bumps when capability is added without breaking existing manifests.
- **PATCH** bumps for bug fixes that don't change behavior.

**Manifest version constraints:**
- `=1.2.3` — exact pin
- `^1.0` — latest 1.x.y (caret = compatible)
- `~1.2` — latest 1.2.x (tilde = patch-only)
- `latest` — current latest registered version (discouraged in production)

**Concurrent versions:** a cell may ship multiple major versions concurrently in the registry. The handoff already shows `memory v1.0.0` and `memory v2.0.0` paths side by side. This is the mechanism by which agents migrate at their own pace.

**Resolution failure is fatal.** If any cell or tool in a manifest cannot be resolved, the kernel refuses to start the agent and logs the unresolved references.

---

## 14. Out of Scope for v0.1

Listed explicitly so future contributors know what *not* to build into v0.1:

- **Streaming responses.** v0.1 is request/response. Streaming is a v0.2 feature and changes the `llm-interface` contract.
- **Voice surfaces.** No audio in v0.1.
- **Authentication and authorization.** The HTTP layer in front of agentOS owns auth; agentOS trusts the `user_id` it's handed.
- **Distributed / multi-host deployment.** v0.1 runs on one host.
- **Remote cell registry / install.** v0.1 reads `cells.registry.yaml` from disk. The Drupal-modules / npm-style fetch-and-install flow is a v0.3 goal.
- **Web UI for managing agents.** Manifests are edited by hand or by tooling outside agentOS.
- **Inter-agent communication.** Agents do not call each other directly. If two agents need to coordinate, they do so via shared external systems exposed as tools.
- **Hot reload of cells.** Manifest changes require an agent restart in v0.1.

---

## 15. The Tests That Prove v0.1 Works

The spec is met when the following can be demonstrated:

1. A new agent can be created by writing a `<name>.yaml` manifest and a `<name>.persona.yaml` — no code changes to the kernel or any cell.
2. Two agents can run concurrently on the same kernel with no observable cross-talk in memory, retrieval, or telemetry.
3. A cell can be upgraded from `1.0.0` to `1.1.0` and a manifest pinned to `^1.0` picks up the new version on restart.
4. A failure in any single cell does not crash the pipeline; the error is recorded and the turn continues with degraded context.
5. A tool invocation is logged with its namespace, turn_id, and timing; no payload secrets leak into default logs.
6. A hook subscribed in a manifest fires when its event is emitted; a handler failure does not prevent the response from returning.

---

*End of v0.1 spec. Companion document: `LESSONS.md` — the line-by-line citations from Maurice and Judy that justify each choice in this spec.*
