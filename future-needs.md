# Future Needs

A running capture of items deferred from the current cut. Not a roadmap — a backlog. New entries get appended with date and a one-liner reason; entries get removed when they ship.

Format:
- **Item** — what
- **Why deferred** — what made us not do it now
- **Trigger to revisit** — what condition makes this important enough to take up

---

## v0.1 MVP deferrals

**Ollama auto-pull from the scaffolder** *(2026-05-17)*
- Why deferred: managing a multi-GB download from inside a CLI scaffolder gets complicated — progress bars, retries, disk space, cancellation, daemon-running checks. Ollama already does this well from its own CLI.
- Trigger: when first-time user friction becomes the bottleneck (someone scaffolds, gets confused, doesn't run `ollama pull`).

**Together AI as a provider in the scaffolder** *(2026-05-17)*
- Why deferred: Ollama-first for MVP per Mario's call. Together AI presets are sketched but not wired into the picker.
- Trigger: any agent needs a cloud-hosted model that doesn't fit Ollama's memory profile (large parameter sizes, very low latency, distributed serving).

**Qwen direct API** *(2026-05-17)*
- Why deferred: Qwen models are reachable via Ollama and Together AI for v0.1.
- Trigger: cost/latency advantage from going direct to dashscope/alibaba becomes meaningful, or Qwen ships a model only available on its native API.

**DeepSeek direct API** *(2026-05-17)*
- Why deferred: not in MVP scope.
- Trigger: same as Qwen — direct access becomes meaningful.

**llama.cpp provider (separate from Ollama)** *(2026-05-17)*
- Why deferred: Ollama covers the local-model case for MVP. llama.cpp without Ollama is a second integration path.
- Trigger: someone wants to run a custom GGUF that Ollama doesn't have, or run on hardware Ollama doesn't support well.

**`agentos doctor` command** *(2026-05-17)*
- Why deferred: validation tooling is a v0.2 quality-of-life addition. Checks: Ollama daemon up, manifest's models actually pulled, API keys present, cells/tools all resolvable.
- Trigger: first time someone scaffolds an agent and `agentos run` fails for a reason that doctor would have caught.

**`agentos pull <model>` command** *(2026-05-17)*
- Why deferred: scope creep. Users `ollama pull` themselves.
- Trigger: bundling pulls into the agentOS UX becomes valuable (e.g., "agentos run will pull the model if missing").

**Per-namespace credential isolation** *(2026-05-17)*
- Why deferred: shared `.env` is simpler. Two agents using the same provider can share one key.
- Trigger: two agents on the same install need *different* keys for the same provider (e.g., Maurice and Judy on separate Anthropic billing accounts), or compliance requires isolation.

**Always-current model lists from LiteLLM catalog** *(2026-05-17)*
- Why deferred: curated preset list + "custom" option is good enough for MVP and never breaks.
- Trigger: keeping the preset list current becomes a chore, or users complain about not seeing new models.

**Anthropic and OpenAI as providers** *(2026-05-17)*
- Why deferred: Mario's call — Ollama + Together AI cover the open-stack story he's building toward.
- Trigger: a paying customer or a partner agent ships requiring one of these specifically.

**Streaming responses** *(2026-05-17, also SPEC §14)*
- Why deferred: v0.1 is request/response. Streaming changes the `llm-interface` contract.
- Trigger: real users on web/phone experience the wait and ask why it's not streaming.

**Voice surfaces** *(2026-05-17, also SPEC §14)*
- Why deferred: out of scope for v0.1.
- Trigger: a voice agent (Maurice VOIP, Judy iPad agent) needs to run on agentOS.

**Authentication / authorization layer** *(2026-05-17, also SPEC §14)*
- Why deferred: agentOS trusts the `user_id` the HTTP layer hands it.
- Trigger: agentOS is exposed publicly without an HTTP layer in front.

**Distributed / multi-host deployment** *(2026-05-17, also SPEC §14)*
- Why deferred: single-host is fine for MVP.
- Trigger: an agent's load exceeds one host.

**Remote cell registry (Drupal-modules / npm-style fetch)** *(2026-05-17, also SPEC §14)*
- Why deferred: local file registry is simpler.
- Trigger: someone outside Blacksky wants to publish a cell.

**Hot reload of cells** *(2026-05-17, also SPEC §14)*
- Why deferred: a restart works fine in dev.
- Trigger: cell development velocity slows down because of restart latency.

**Cell SDK with test scaffolding** *(2026-05-17)*
- Why deferred: until we have ~3+ cells written, we don't know what the SDK should automate. Premature abstraction.
- Trigger: writing a fourth cell is annoyingly repetitive.

**judy-ipad — agent for an agent** *(2026-05-17)*
- Why deferred: empty placeholder folder in /sites/nia. Future scope.
- Trigger: Judy is running on agentOS and a voice/iPad surface needs an agent that controls her.

**Maurice and Judy ports** *(2026-05-17)*
- Why deferred: foundation first. Stan is the POC.
- Trigger: kernel + cell library v1 are stable; ready to migrate production agents.

**Purge agent data on `delete agent`** *(2026-05-17)*
- Why deferred: v0.1 cells write no persistent state. `delete agent` only removes the manifest + persona.
- Trigger: the `memory` cell starts writing to `data/<namespace>/` (or a namespaced DB schema). Adds a `--purge-data` flag and a confirmation step.

**Hot-unregister an agent from a running kernel** *(2026-05-17)*
- Why deferred: `agentos run` is a foreground process; restart works fine for dev.
- Trigger: a production agent running as a daemon needs to be removed without a restart. Adds a kernel route like `DELETE /agents/<name>` or a SIGHUP handler.

**`agentos stop <name>` + daemon mode** *(2026-05-17)*
- Why deferred: foreground-only is the simplest UX for MVP. Use `Ctrl+C`.
- Trigger: running multiple agents on one host, or running unattended.

**Drop-folder auto-watch** *(2026-05-18)*
- Why deferred: foreground-only kernel; no daemon to host a file watcher. Manual `Ingest folder` button works fine for iterative editing.
- Trigger: someone runs a long-lived agentOS process in daemon mode and wants the corpus to track file changes automatically.

**Drop-folder "wipe and re-ingest" one-click** *(2026-05-18)*
- Why deferred: today the workflow is delete each source in the UI list, then Ingest folder. Two steps but explicit. A combined button would be one click.
- Trigger: Mario does this loop more than a couple of times a day.

**Shared corpus folder across agents** *(2026-05-18)*
- Why deferred: per-agent convention is simpler. Cross-agent shared content goes via copy or symlink.
- Trigger: multiple agents reliably need the same source corpus (e.g., a company knowledge base feeding both Maurice and Judy).

**Bulk delete / wildcard delete** *(2026-05-17)*
- Why deferred: not yet enough churn to warrant it. `delete agent stan && delete agent stan2` is fine for now.
- Trigger: Mario's build-and-destroy iteration speed needs `delete agent stan*` or `delete agent --all-prefix=test_`.

---

*Add new entries at the bottom of the current phase block. When an entry ships, delete it and note the commit in the changelog.*
