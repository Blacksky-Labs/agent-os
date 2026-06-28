# AgentOS — Reasoning-Layer MoE (design sketch)

*Blacksky Labs | 2026-06-20 | Companion to agentos-v1-spec.md (Reasoning Layer)*

The v1 spec lists **MoE Routing** as a Reasoning-Layer option that isn't built yet.
This is the basic concept and the first concrete expert.

**Status (2026-06-20):** shipped — `style` post-expert (deterministic) and the
`moe` reasoning cell (router → expert dispatch, each expert on its own model via
`chat_completion`), addable to any entity via the config overlay (Single ↔ MoE +
roster editor). This doc covers *what experts are*. **When an expert is brought in
— the activation protocol — is specified separately in `agentos-moe-protocol.md`**
(the gating cascade, the declarative activation contract, and the v0 tiny-model
triage). The current `moe` cell is still "route-always"; the protocol replaces that
with cheap-by-default gating.

---

## 0. The idea in one line

A **router** dispatches a turn to one or more **experts** — specialists that each
do one thing well — instead of asking a single prompt to do everything.

## 1. Two kinds of expert

- **Pre-experts** shape *generation*: a router classifies the query and routes to a
  specialist (sales scoring for Maurice, policy analysis for Judy, a "Seth" deeper
  emotional-support layer for Skipper). They run around / instead of `llm-interface`.
- **Post-experts** shape *the response*: they refine what was generated —
  presentation, length, tone. They run **after** `llm-interface`.

A **style/presentation expert is the cleanest first one**, because it's
content-agnostic: it doesn't need to know about comics or doors, it just shapes the
output. That's why we start here.

## 2. The contract (reuse what we have)

An expert is just a **cell**. The cell interface already gives us `execute(context)`
— a pre-expert reads `assembled_prompt`/`intent` and influences generation; a
post-expert reads/rewrites `context.response`. No new primitive needed.

A **router** is a cell (or a small selector) that decides which experts fire for a
turn, based on `context.intent` / query shape and the entity's enabled roster. With
a single expert the router is trivial (the expert is a cell that no-ops when it
doesn't apply); it earns its keep once there are several experts to choose between.

## 3. When experts fire (the latency rule)

We just moved a model call off the response path — so cost matters.

- **Deterministic experts** (no model) run **always** — effectively free.
- **Model experts** run **only when the router flags the turn** (e.g. a "list / summary"
  intent, or a response over N words), so the second model call is the exception,
  not every turn.

The first style expert is **deterministic**, so it's always-on and costs nothing.

## 3b. Experts bring their own (smaller) models

MoE isn't just routing — it's using the *right-sized* model for each job. A narrow
expert (classify intent, reformat a list, score a lead) doesn't need the entity's
big model; a small, fast one (e.g. `gemma4:e2b`, or a tiny classifier) is cheaper
and quicker. So:

- Each expert declares its **own** `model` in config and calls it through
  `agentos.llm.chat_completion` — the entity's main model stays reserved for the
  primary response.
- The router itself can be deterministic or a tiny model.
- This is also the v1 **"nano-models"** reasoning option: lightweight cascaded
  chains of small specialists.

The plumbing already exists: `chat_completion(model_cfg, …)` takes any model, and
the `signal_extract` hook already overrides its own model — so an expert can pull a
smaller model with zero new infrastructure.

## 4. The roster (vision)

| Expert | Kind | Fires when | Status |
|---|---|---|---|
| **style** (presentation) | post | always (deterministic) | **v0 — this drop** |
| style (model reformat: prose→bullets, tone, length) | post | router flags list/long | next |
| **Seth** (deeper emotional support) | pre/parallel | distress/charge signal | seed roadmap |
| domain — sales scoring (Maurice) | pre | lead/buying intent | later |
| domain — policy analysis (Judy) | pre | bill/policy query | later |

Same router, different roster per entity — that's the MoE.

## 5. v0 — the `style` expert (shipping now)

- A `style` cell, placed **after `llm-interface`** in the pipeline.
- Deterministic: normalizes list markers (`*`, `•`, `1.`, …) at line-start to a
  consistent `- ` bullet. Pure, instant, never raises.
- Pairs with Skipper's persona nudge ("show lists as bullets"): the model produces
  the list, the expert guarantees clean, consistent formatting.
- Toggleable like any reasoning cell (it shows up in the config page); disable it
  and responses pass through unformatted.

## 6. Phased path

1. **v0 — `style` (deterministic).** *(this drop)*
2. **style `mode: model`** — a small, fast style pass that reformats prose into the
   entity's house style; router-gated so it only fires on list/long responses.
3. **`moe-router` cell** — the real router, once there are ≥2 experts to choose between.
4. **Pre-experts** — Seth (emotional support), then domain experts for Maurice/Judy.

---

*Start small: one deterministic post-expert proves the slot. The router and the
richer experts plug into the same contract as the roster grows.*
