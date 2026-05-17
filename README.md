# AgentOS

*The foundation infrastructure for the Blacksky agent fleet.*

AgentOS is to agents what npm is to packages and Drupal is to modules: a kernel, a registry, and a manifest format that lets you compose a new agent without writing kernel code. Each agent is a `persona.yaml` and an `<agent>.yaml` manifest pointing at versioned cells, tools, and hooks. The kernel runs the pipeline; the agent declares the configuration.

See **[SPEC.md](./SPEC.md)** for the full v0.1 specification.

---

## Status

**v0.1 — Alpha.** The MVP scaffolding flow is being built. Public API is unstable.

---

## Quickstart

```bash
# 1. Clone
git clone <repo-url> agentOS
cd agentOS

# 2. Install (editable)
python -m venv venv
source venv/bin/activate
pip install -e .

# 3. Scaffold a new agent
agentos new agent hello

# 4. Start it (`run` is also accepted as an alias)
agentos start hello

# 5. In another terminal, chat with it
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "hello",
    "user_message": "ping",
    "session_id": "test-001",
    "mode": "web"
  }'
```

---

## Vocabulary

Six terms, defined once in [SPEC.md §1](./SPEC.md):

- **Cell** — a versioned module in the pipeline. Pure function of `AgentContext`.
- **Tool** — an LLM-callable function. Executed during tool-use loops.
- **Hook** — a named event. Owns side effects (email, audit logs, webhooks).
- **Persona** — the agent's voice, mission, refusal patterns. Data, not code.
- **Manifest** — the `<agent>.yaml` that ties everything together.
- **Namespace** — the isolation scope. Every agent has one; nothing crosses it.

---

## Directory Layout

```
agentOS/
├── SPEC.md                       # v0.1 specification
├── LESSONS.md                    # citations from Maurice & Judy that justify the spec
├── agentos/                      # kernel (Python package)
├── cells/                        # cell library v1
│   ├── mode_control/
│   ├── memory/
│   ├── ingestion/
│   ├── retrieval/
│   ├── context_builder/
│   └── llm_interface/
├── tools/                        # tool library
├── hooks/                        # hook handler library
├── personas/                     # shared persona components (optional)
├── manifests/                    # agent manifests
├── templates/                    # scaffolding templates for CLI
├── cells.registry.yaml
├── tools.registry.yaml
└── tests/
```

---

## Design Principles

1. **Cells are pure.** Side effects live in hooks.
2. **The kernel knows nothing about any specific agent.** Agent-specific behavior is fully specified by the manifest and persona.
3. **Namespace propagates everywhere.** No cross-namespace reads or writes, ever.

---

## License

Proprietary — Blacksky LLC.
