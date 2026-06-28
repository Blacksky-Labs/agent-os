# AgentOS v1 — Spec Delta & Gap Map

*Blacksky Labs | 2026-06-20 | Companion to SPEC.md (v0.1) and `plans-21/` (the v1 product vision)*

---

## 0. Purpose

`plans-21/` paints the **product**: AgentOS v1 as a platform for deploying configurable **entities** assembled from swappable layers via a no-code configurator. `SPEC.md` defines the **kernel**: agents as manifests over a pure cell pipeline. This document is the bridge — it maps every v1 concept onto the existing architecture, marks what exists vs. what's missing, and states the one rule v1 must not break.

**Headline:** v1 is mostly a *re-skin and a build-out*, not a re-architecture. The kernel's `AgentContext` already carries the channels the v1 "Reasoning Engines" need, and the hook system already owns the side effects. What's missing is implementation (engines, configurator, dashboard, extra backends) — not new foundations.

---

## 1. Vocabulary delta (v0.1 → v1)

| v0.1 (kernel / SPEC.md) | v1 (product / plans-21) | Reconciliation |
|---|---|---|
| Agent | **Entity** ("expert oracle on a domain") | Same thing. One entity = one manifest + persona. Rename is cosmetic; the kernel can keep `agent` internally. |
| *(none)* | **Archetype** — Focused / Wide | A starting manifest template with default layer configs. New concept; expressible as presets. |
| Cells (6, pure pipeline) | **Layers** (Model / Database / Interface / Reasoning) | Layers are *groupings* of cells + config, not a new primitive. One layer = one or more cells/hooks. |
| Manifest (`<agent>.yaml`) | Output of the **Configurator** | The configurator is a manifest generator. Every UI choice sets a manifest field. |
| Persona (`persona.yaml`) | Entity voice/mission | Unchanged. |
| Namespace | Per-entity isolation | Unchanged — still the kernel's hard boundary. |
| Hooks | Engine side effects (cron, alerts, persistence) | Unchanged — the v1 engines lean on exactly this. |

---

## 2. The entity model — archetypes & default layer configs

Two archetypes, each a preset of the four layers (from `configurator.html`):

| Layer | **Focused** default | **Wide** default |
|---|---|---|
| Model | Cloud LLM *(or Local for privacy)* | MoE Framework |
| Database | Lightweight DB | Prism |
| Interface | CRM Dashboard | Standard Dashboard |
| Reasoning | Single Model | MoE Routing |
| Data scale | Business records | 250k+ · real-time |

"Same platform. Same engine. Different defaults. Fully configurable." Nothing is locked — any layer can be overridden. **Skipper is a Focused entity with the Model overridden to Local** (see §7).

---

## 3. The architectural through-line (the one rule)

v1 must preserve the v0.1 invariants (SPEC §2/§4/§10):

1. **Cells stay pure** functions of `AgentContext`; side effects live in hooks.
2. **The kernel stays entity-agnostic** — no `if entity == "skipper"` anywhere. Layers/engines are generic; the manifest configures them.
3. **Namespace isolation** holds across every layer and engine.
4. **One manifest = one entity.** The configurator emits that manifest; it does not introduce a parallel config system.
5. **LiteLLM is the only inference path** (the Model Layer is LiteLLM config).

If a v1 feature seems to require breaking one of these, it belongs in a hook, a tool, or the interface layer in front of the kernel — not in the kernel.

---

## 4. Layer → architecture mapping

### 4.1 Model Layer → `llm-interface` cell (LiteLLM)

| v1 option | Code path | Status |
|---|---|---|
| Local LLM (Gemma/Llama·MLX) | `model.name: ollama/gemma4:e4b` | **✓ works** (Skipper) |
| Cloud LLM (Together AI 70B+) | `model.name: together_ai/…` | **✓ by design** (LiteLLM); needs key + presets |
| Vertex AI (Gemini/GCP) | `model.name: vertex_ai/gemini-…` | **partial** — LiteLLM supports it; untested, no config |
| MoE Framework | routing over multiple models | **missing** — a Reasoning component, not one call (see §5) |

The cell is already model-agnostic (`SPEC §5`), so most of this layer is configuration, not code.

### 4.2 Database Layer → `memory` + `retrieval` cells

| v1 option | Code path | Status |
|---|---|---|
| Lightweight DB | `memory` cell — SQLite `data/<ns>/memory.db` | **✓ works** (Skipper) |
| Vector RAG | `retrieval` cell — ChromaDB + Ollama embeddings | **✓ works** (exists; Skipper omits it for now) |
| PostgreSQL | a future `memory` backend (a v2 cell) | **missing** — no cell registered, no `cell_v2.py` on disk; only sketched in the build-handoff |
| Prism | adapter cell → `prism-platform` API (Zero→T1→T2→T3) | **missing wiring** — Prism is a separate, running platform; needs a retrieval/memory adapter cell |

### 4.3 Interface Layer → HTTP surface + UI + clients

| v1 option | Code path | Status |
|---|---|---|
| Standard (chat + analytics + cron builder + config) | `main.py` `/chat`, `ui.py` web chat, `clients/` native app, corpus endpoints | **partial** — chat ✓; analytics, cron-builder UI, layer-config dashboard **missing** |
| CRM (pipeline, lead scoring, timelines) | new dashboard + tools | **missing** |
| CRM + Salesforce / HubSpot | bidirectional sync tools (MCP) | **missing** |

This is the largest greenfield: the **dashboard/configurator web app does not exist** (the `plans-21` pages are static mockups; the only real UI is `ui.py`'s single chat page).

### 4.4 Reasoning Layer → cell pipeline + hooks + engines

The Reasoning Layer has **two parts**:

**(a) Thinking architecture** — how inference is structured:

| v1 option | Code path | Status |
|---|---|---|
| Single Model | one `llm-interface` call (current default) | **✓ works** |
| MoE Routing | classify query → route to specialist model(s) → assemble | **missing** |
| Domain Specialists | fine-tuned sub-models per area | **missing** |
| Nano-models | lightweight cascaded chains | **missing** |

**(b) The five always-on Engines** — detailed in §5.

---

## 5. The five Reasoning Engines

The v1 "always working" intelligence. Crucially, **`AgentContext` already declares the channels these write to** — the engines are implementations, the data model is in place.

| Engine | Writes to (AgentContext) | Today | To build |
|---|---|---|---|
| **Context Engine** | `conversation_history`, `user_profile`, `semantic_history` | `memory` cell fills `conversation_history` (SQLite turns) ✓ | Unified cross-channel **profile** (`user_profile`/`semantic_history` unfilled); merge web+chat+phone per identity |
| **Sentiment Engine** | `intent`, `entities`, `sentiment`, `extracted_signals` | `ingestion` cell is a **stub** | Make ingestion real: deterministic extractors + time-boxed LLM signals (per SPEC §5) |
| **Cron Jobs** | side effects via hooks; reads memory | **missing** | A per-namespace **scheduler** running user-defined overnight jobs (summaries/predictions/follow-ups). **= Skipper's sleep cycle.** |
| **Identity Layer** | `user_id`, profile merge | `user_id` exists; auth deferred (SPEC §14) | Soft login (cookie/local → anonymous profile), merge on OAuth/account |
| **Phone Intelligence** | same pipeline; `mode="phone"` | `phone` mode constraints exist ✓ | Telephony ingest (transcripts → pipeline), caller match by number (BlackOne surface) |

The hook events to hang engine side-effects on already exist (SPEC §7): `after_turn`, `on_high_intent`, `on_lead_scored`, `on_conversation_end`. **Cron Jobs** is the one genuinely new kernel primitive — a time-driven trigger rather than a turn-driven one.

---

## 6. The Configurator contract (configurator → manifest)

A "configured entity" is a generated `manifest.yaml` + `persona.yaml`. Each configurator choice maps to a manifest mutation:

| Configurator choice | Manifest effect |
|---|---|
| Archetype (Focused/Wide) | Base template: cell list + default layer configs |
| Model Layer | `model: { provider, name, api_base, … }` |
| Database Layer | Which DB cells (`memory`/`retrieval`/`prism-adapter`) + their `config` |
| Interface Layer | Dashboard variant + CRM sync tools in `tools:` |
| Reasoning Layer | Cell ordering + thinking architecture + which engines enabled |
| Voice add-on | `phone` mode + telephony tool/hook |

So the configurator is a **manifest generator with a GUI** — it never bypasses the kernel's manifest contract. Building it = (1) the form (web), (2) a manifest emitter, (3) `agentos` accepting a generated manifest (already does).

---

## 7. Entity presets (the catalog as layer configs)

| Entity | Archetype | Model | Database | Interface | Reasoning | Delivery |
|---|---|---|---|---|---|---|
| **Skipper** | Focused | **Local** (gemma4:e4b) | Lightweight (SQLite) | Standard (native app) | Single + Context/Sentiment/**Cron** | **Local / on-device, private** |
| Maurice | Focused | Cloud | Lightweight | CRM | Single + all 5 engines | Hosted (GCP) |
| Judy | Wide | MoE | Prism | Standard | MoE routing + engines | Hosted (GCP) |
| Ife | Focused | Configurable | Configurable | Standard | Single | Hosted |

**Skipper is the local reference entity** and the proving ground for the Context/Sentiment/Cron engines. Its "brain" work *is* the v1 Reasoning Layer, built first on the simplest (local, private) configuration.

> **Delivery note:** the catalog entities are **hosted** (GCP + Prism + CRM); Skipper is **local-first**. These are opposite ends of the same swappable-layer model — which is the v1 thesis, not a contradiction. The kernel is identical; only the layer configs and the deployment differ.

---

## 8. Master gap table

| Capability | Status | Lands in |
|---|---|---|
| Entity = manifest + persona | ✓ | kernel |
| Archetype presets (Focused/Wide) | missing | templates + `agentos new` |
| Model: Local, Cloud | ✓ / by-design | `llm-interface` |
| Model: Vertex, MoE | partial / missing | `llm-interface` + new router |
| DB: SQLite, ChromaDB | ✓ | `memory`, `retrieval` |
| DB: PostgreSQL, Prism | missing / unwired | new `memory` backend, new Prism adapter |
| Context Engine | partial | `memory` upgrade |
| Sentiment Engine | stub | `ingestion` (make real) |
| Cron Jobs (sleep cycle) | missing | new scheduler + hooks |
| Identity Layer | missing | interface + profile store |
| Phone Intelligence | missing | `phone` mode + telephony |
| Standard chat interface | ✓ (basic) | `main.py`, `ui.py`, `clients/` |
| Dashboard / analytics / cron builder | missing | new web app |
| CRM / Salesforce / HubSpot | missing | dashboard + MCP tools |
| Configurator (no-code) | missing (static mockup) | new web app → manifest emitter |

---

## 9. Phased path to v1

- **Phase A — Reasoning engines on Skipper (local).** Context Engine upgrade, real Sentiment (ingestion), Cron Jobs (the sleep cycle). Proves the hardest layer on the simplest config.
- **Phase B — Archetype presets + configurator core.** Focused/Wide templates; the configurator form → manifest emitter.
- **Phase C — Database Layer for Wide.** Postgres tier; the Prism adapter cell (wire `prism-platform` in).
- **Phase D — Interface Layer.** Dashboard, analytics, cron-builder UI, CRM + Salesforce/HubSpot tools.
- **Phase E — Identity + Phone/Voice; Cloud/Vertex/MoE model options.** The hosted-entity surfaces.

---

## 10. What does *not* change

The v0.1 SPEC stands. Entities are still manifests; layers and engines are still cells, hooks, and config; namespace still isolates; LiteLLM is still the only inference path; the kernel still knows nothing about any specific entity. **v1 adds capability and a product skin on top of an unchanged kernel contract.**

---

## 11. Open decisions

1. **"Entity" rename** — surface-only (UI/docs) or also in code/CLI? (Recommend: surface-only; keep `agent` internally to avoid churn.)
2. **Where the dashboard/configurator lives** — the missing web app. New stack (the `plans-21` mockups are static HTML) — Node/Next.js (like `axis/ui`) or server-rendered from the kernel?
3. **Prism adapter** — does Prism appear to the kernel as a `retrieval` backend, a `memory` backend, or both?
4. **Cron Jobs** — in-kernel scheduler vs. external trigger hitting a kernel route. (Skipper's on-device sleep cycle vs. hosted entities' server cron may differ.)
5. **MoE** — routing across LiteLLM models vs. a dedicated framework.
