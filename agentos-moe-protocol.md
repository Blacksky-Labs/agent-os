# AgentOS — MoE Activation Protocol (spec)

*Blacksky Labs | 2026-06-20 | Companion to `agentos-moe-design.md` and `agentos-v1-spec.md` (Reasoning Layer)*

This spec answers one question: **when is an expert brought in?** It defines the
decision procedure — the *protocol* — that every AgentOS entity uses to decide
whether a turn deserves an expert, which one, and whether it's worth the cost.

---

## 0. Why this is an OS primitive, not a Skipper feature

AgentOS runs many entities — Skipper (personal), Maurice (sales), Judy (civic),
Stan (economics), and whatever comes next. Each carries a different roster of
experts, but every one of them needs the *same* question answered on every turn:
**should an expert be engaged, which one, and is it worth the latency?**

That decision procedure belongs to the **kernel**, not to any entity. It is
declared by config and evaluated uniformly, so:

- an entity author writes **a roster, never routing code**;
- every entity inherits the same gating, cost guarantees, and safety behavior;
- improving the protocol improves the whole fleet at once.

Skipper is simply the first roster to run on it. This is what makes MoE a
property of the OS rather than a bespoke feature — the reason AgentOS is an OS.

## 1. Core principle — cheap by default, escalate on signal

Single-model reasoning answers every turn directly with one model call. **MoE must
never cost more than that by default.** So the protocol is a **cascade of gates,
cheapest first**: a turn exits at the first gate that resolves it, and the common
case exits at the top having spent nothing extra. A model-based decision is the
*last* resort, not the first.

## 2. The cascade

Evaluated top to bottom; first gate to resolve wins.

| Tier | Gate | Cost | Mechanism | Outcome |
|------|------|------|-----------|---------|
| 0 | **Post-experts** | ~free | deterministic, out of band | always run *after* generation (e.g. `style`) — not gated |
| 1 | **Safety** | free | deterministic lexicon + `crisis_signal` | crisis/self-harm → force the support lane, **short-circuit** |
| 2 | **Hard triggers** | free | regex / keywords / signal conditions | an expert's declared trigger fires → force-activate it |
| 3 | **Similarity** *(opt, later)* | cheap | one embedding vs expert centroids | above threshold with clear margin → activate |
| 4 | **Triage** | cheap | one **tiny** model, ~4 tokens out | classify the turn into a lane → activate that expert |
| 5 | **Default** | — | none | base model answers; **no expert** |

Note the ordering of the two cheap gates: **similarity (no generation) is tried
before the triage model (a call).** v0 ships without similarity, so triage is the
only model gate.

## 3. The expert activation contract (declarative)

Each expert declares *how it is selected*. This is the only thing an entity author
writes — it lives in the manifest (and is editable live via the config overlay):

```yaml
experts:
  - name: seth
    model: ollama/gemma4:e4b      # its own (often smaller) model
    system: "deeper emotional-support register…"
    # --- activation ---
    lane: emotional               # tier 4: the label the triage model emits
    triggers: ["\\bI feel\\b", "\\bhopeless\\b"]   # tier 2: force-activate (free)
    signals: { flags: [crisis_signal] }            # tier 2: AgentContext conditions
    examples: ["I've had an awful day", "I can't cope"]  # tier 3: similarity centroid
    description: "emotional support, venting, distress, reflection"  # triage prompt text
    priority: 80                  # tie-break when several activate (safety highest)
    threshold: 0.62               # similarity bar
    activation: per_turn          # cadence — see §5
```

The kernel evaluates the cascade against these declarations. No entity ships
routing logic.

## 4. Signals the gate can see — and *when*

The protocol reads `AgentContext`. The critical subtlety is **timing**:

- **Synchronous (this turn).** Deterministic `ingestion` output — `entities`,
  `extracted_signals` (emails, money, dates, urls), and the raw message. Populated
  *before* the reasoning slot runs. Free.
- **Lagged (previous turn).** `intent`, `sentiment`, topics, `is_commitment`,
  `crisis_signal` — produced by the **background** `signal_extract` hook *after* the
  turn completes. On turn *N* the gate sees turn *N−1*'s values.

Implication: tiers 1–2 must rest on **synchronous deterministic signals + the
message text**. LLM-grade understanding of the *current* turn is the triage model's
job (tier 4). Pulling `signal_extract` back onto the response path is **explicitly
rejected** — that is the latency we deliberately moved to the background.

One exception: tier-1 safety runs a **synchronous deterministic lexicon**; it must
not wait for the background `crisis_signal` flag. Safety is never lagged and never
gated behind a model.

## 5. Activation cadence — "when" beyond the turn

"When" has two meanings. The cascade above governs **per-turn** activation. But
some experts shouldn't run per turn at all. Three activation classes:

- **`per_turn`** — message-triggered; the cascade evaluates it every turn
  (general, emotional, code…).
- **`on_signal`** — fires only when a condition crosses, not every turn (a planner
  on `is_commitment`; a follow-up on an unresolved thread). May run in the
  background hook lane rather than on the response path.
- **`scheduled`** — cron-driven, with no user turn at all (a nightly
  reflection/summarizer; a weekly digest). Ties to the sleep-cycle scheduler in
  `agentos-v1-spec.md` (Cron Jobs).

Orthogonally: **pre-experts** shape generation (`per_turn`/`on_signal`);
**post-experts** shape the response and always run out of band (`style`);
**scheduled** experts produce artifacts (summaries, surfaced threads), not replies.

## 6. The decision (kernel pseudocode)

```text
select_expert(ctx, roster):
    # tier 0 post-experts run separately, after generation — not here.

    # tier 1 — safety (synchronous, deterministic)
    if safety_lexicon.matches(ctx.user_message) or ctx.flag("crisis_signal"):
        return highest_priority(experts_with_lane(roster, "safety"))

    # tier 2 — hard triggers (free)
    hits = [e for e in roster if e.triggers_match(ctx)]      # regex / keywords / signals
    if hits:
        return highest_priority(hits)

    # tier 3 — similarity (cheap, no generation; optional)
    if similarity_enabled:
        e, score = nearest_centroid(ctx.user_message, roster)
        if score >= e.threshold and clear_margin(score):
            return e

    # tier 4 — triage (one tiny-model call)
    if triage_enabled:
        lane = triage_model(ctx.user_message, lanes(roster))  # ~4 tokens, temp 0
        e = expert_for_lane(roster, lane)
        if e:
            return e

    # tier 5 — default
    return None     # base model answers, no expert
```

The selected expert then *is* the generation step (see §7). A `None` result means
the base model answers — the single-model path, unchanged.

## 7. Cost & latency contract

The protocol exists to protect latency, so it makes explicit guarantees:

- **Default and deterministic paths add zero model calls.**
- **Triage adds exactly one tiny-model call** (tens to low-hundreds of ms warm),
  and only when cheaper gates didn't resolve.
- **An activated expert replaces the base generation — it is not additional.** A
  triaged turn costs `triage(tiny) + generate(expert)`; a default turn costs
  `generate(base)`. The tax is one tiny call, never a doubled generation.
- **Similarity (later) removes most triage calls**, pushing common turns back to
  zero added cost.

This is the line that separates a real MoE from the naive "route-always" cell:
the protocol must be *cheaper on average* than single-model, not more expensive.

## 8. v0 — the simplest real instantiation

One tiny model, one simple decision — generic mechanism, Skipper as the first
roster.

- **Kernel.** The `moe` cell gains the cascade with **tier 1** (synchronous safety
  lexicon) + **tier 4** (triage) + **tier 5** (default). Tiers 2 and 3 are config
  hooks that no-op until populated — the cascade is whole, the cheap gates land
  later.
- **Triage model.** A tiny model (`gemma4:e2b`), temp 0, emits one lane label from
  the roster's declared lanes. This is the "small model doing something simple."
- **Skipper roster (example).** lanes `general` (default) + `emotional` → `seth`;
  the safety lexicon routes to the support lane and short-circuits.
- **Same machinery, other entities.** Rosters are config, so:
  - Maurice (sales): `general` + `objection` + `pricing`
  - Judy (civic): `general` + `policy`
  - Stan (econ): `general` + `analysis`
  (Illustrative — no entity writes routing code; they write lanes.)
- **Latency.** Replaces today's always-on `e4b` router with a tiny binary triage;
  once tier-2 triggers and tier-3 similarity land, default turns skip the triage
  entirely.

## 9. Phased path

1. **v0 cascade** in the `moe` cell — safety lexicon + tiny triage + default. *(this spec → build)*
2. **Deterministic triggers** (tier 2) — experts declare regex/signal triggers for free force-activation.
3. **Confidence + priority** — thresholds, tie-breaks, an explicit "unsure → default."
4. **Similarity gate** (tier 3) — centroids built from `examples`, cached in `data/<ns>/`; removes most triage calls.
5. **Cadence** — `on_signal` and `scheduled` experts (ties to the cron / sleep-cycle).
6. **Fleet rosters** — Maurice / Judy / Stan and beyond, same protocol, different config.

## 10. Open questions (settle as we build)

- **Lane space** — fixed per entity vs learned. Start fixed.
- **Multi-expert turns** — v0 selects one; later allow a primary + advisors with aggregation.
- **Centroid storage** — precompute from `examples`, cache under `data/<ns>/`.
- **Safety lexicon** — a shared OS-level base list plus per-entity additions.
- **Triage reliability** — measure: does a tiny model hit the lane correctly often enough? If not, fall back to default rather than mis-route.
