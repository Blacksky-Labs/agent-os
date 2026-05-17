# AgentOS — Build Handoff
*Blacksky LLC | Mario Moorhead, Founder & CEO*
*Prepared for Claude Code / CoWork*

---

## Context

AgentOS is the core infrastructure layer that powers all Blacksky agents. It is not agent-specific — it knows nothing about politics, sales, or any agent's domain. It handles only what every agent needs regardless of what it does.

**Mario Moorhead is the only human operator.** Agents and automated processes handle what a developer team would otherwise own.

**Stan** is the guinea pig agent — an economics/financial intelligence agent anchored to the BTC Clock timeline. If it breaks we fix it. Once proven, Maurice and Judy integrate.

---

## Repo Structure

```
blacksky/
  ├── agentOS/
  │     ├── core/
  │     │     ├── context.py         ✓ written
  │     │     ├── pipeline.py        ✓ written
  │     │     ├── registry.py        ✓ written
  │     │     ├── config.py          ← needs building
  │     │     └── main.py            ← needs building (FastAPI entry)
  │     │
  │     ├── cells/
  │     │     ├── mode_control/
  │     │     │     └── cell.py      ← needs building (real)
  │     │     ├── memory/
  │     │     │     └── cell.py      ← stub ok for now
  │     │     ├── ingestion/
  │     │     │     └── cell.py      ← stub ok for now
  │     │     ├── retrieval/
  │     │     │     └── cell.py      ← stub ok for now
  │     │     ├── context_builder/
  │     │     │     └── cell.py      ← stub ok for now
  │     │     └── llm_interface/
  │     │           └── cell.py      ← needs building (real)
  │     │
  │     └── cells.registry.yaml      ✓ written
  │
  └── agents/
        └── stan.yaml                ← needs building
```

---

## Minimum Viable Spinup

Two cells need to be real for Stan to respond:
- `llm_interface` — LiteLLM wired for real
- `mode_control` — sets response constraints correctly

Four cells can be stubs that pass context through unchanged:
- `memory`, `ingestion`, `retrieval`, `context_builder`

---

## The 6 Layers (AgentOS Architecture)

```
1. Memory          ← Prism-tiered (Mongo → Postgres → Qdrant) + async background processor
2. Ingestion       ← Prism (agent declares sources in yaml, OS routes)
3. Context Builder ← LangGraph parallel channels (intent, entity, memory, retrieval, sentiment, assembly)
4. Retrieval       ← Prism (Qdrant vector search, namespaced per agent)
5. LLM Interface   ← LiteLLM (model-agnostic, provider-agnostic)
6. Mode Control    ← web | phone | embedded | api
```

---

## The Cell Interface Contract

Every cell must implement this interface:

```python
class AgentOSCell:
    name: str
    version: str
    
    def init(self, config: dict) -> None
    async def execute(self, context: AgentContext) -> AgentContext
    async def teardown(self) -> None
```

AgentOS passes AgentContext through each cell in sequence. Each cell reads what it needs, adds what it produces, passes it forward. No cell knows what comes before or after it.

---

## Code Written So Far

### `core/context.py`

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class AgentContext:
    
    # Identity
    agent_name: str
    workspace_id: str
    session_id: str
    user_id: str | None = None
    
    # Mode
    mode: str = "web"              # web | phone | embedded | api
    
    # Incoming
    user_message: str = ""
    
    # Memory channels
    conversation_history: list[dict] = field(default_factory=list)
    user_profile: dict = field(default_factory=dict)
    semantic_history: list[dict] = field(default_factory=list)
    
    # NLP channels (LangGraph fills these)
    intent: str | None = None
    entities: list[str] = field(default_factory=list)
    sentiment: str | None = None
    
    # Retrieval
    retrieved_chunks: list[dict] = field(default_factory=list)
    live_data: dict = field(default_factory=dict)
    
    # Assembly
    assembled_prompt: list[dict] = field(default_factory=list)
    
    # Output
    response: str | None = None
    
    # Metadata
    meta: dict = field(default_factory=dict)
```

---

### `core/pipeline.py`

```python
import importlib
import logging
from core.context import AgentContext
from core.registry import Registry

logger = logging.getLogger(__name__)

class Pipeline:

    def __init__(self, agent_config: dict, registry: Registry):
        self.agent_name = agent_config["name"]
        self.cell_configs = agent_config["cells"]
        self.registry = registry
        self.cells = self._load_cells()

    def _load_cells(self):
        cells = []
        for cell_config in self.cell_configs:
            name = cell_config["name"]
            version = cell_config.get("version", "latest")
            config = cell_config.get("config", {})

            cell_path = self.registry.resolve(name, version)
            module = importlib.import_module(cell_path)
            cell = module.Cell(config)
            cell.init(config)
            cells.append(cell)

            logger.info(f"Loaded cell: {name} v{version}")

        return cells

    async def run(self, context: AgentContext) -> AgentContext:
        for cell in self.cells:
            try:
                logger.debug(f"Executing cell: {cell.name}")
                context = await cell.execute(context)
            except Exception as e:
                logger.error(f"Cell {cell.name} failed: {e}")
                context.meta[f"{cell.name}_error"] = str(e)
                continue

        return context

    async def teardown(self):
        for cell in self.cells:
            await cell.teardown()
```

---

### `core/registry.py`

```python
import yaml
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class Registry:

    def __init__(self, registry_path: str = "cells.registry.yaml"):
        self.registry_path = Path(registry_path)
        self.cells = self._load()

    def _load(self) -> dict:
        with open(self.registry_path) as f:
            data = yaml.safe_load(f)
        logger.info(f"Registry loaded: {len(data['cells'])} cells available")
        return data["cells"]

    def resolve(self, name: str, version: str = "latest") -> str:
        if name not in self.cells:
            raise ValueError(f"Cell '{name}' not found in registry")

        versions = self.cells[name]["versions"]

        if version == "latest":
            resolved = versions[-1]
        elif version.startswith("^"):
            major = int(version[1:].split(".")[0])
            matching = [
                v for v in versions
                if int(v["version"].split(".")[0]) == major
            ]
            if not matching:
                raise ValueError(f"No compatible version found for {name} {version}")
            resolved = matching[-1]
        else:
            matching = [v for v in versions if v["version"] == version]
            if not matching:
                raise ValueError(f"Version {version} not found for cell {name}")
            resolved = matching[0]

        logger.debug(f"Resolved {name} {version} → {resolved['path']}")
        return resolved["path"]

    def list_cells(self) -> list[str]:
        return list(self.cells.keys())

    def cell_versions(self, name: str) -> list[str]:
        return [v["version"] for v in self.cells[name]["versions"]]
```

---

### `cells.registry.yaml`

```yaml
cells:
  mode-control:
    versions:
      - version: "1.0.0"
        path: "cells.mode_control.cell"

  memory:
    versions:
      - version: "1.0.0"
        path: "cells.memory.cell"
      - version: "2.0.0"
        path: "cells.memory.cell_v2"

  ingestion:
    versions:
      - version: "1.0.0"
        path: "cells.ingestion.cell"

  retrieval:
    versions:
      - version: "1.0.0"
        path: "cells.retrieval.cell"

  context-builder:
    versions:
      - version: "1.0.0"
        path: "cells.context_builder.cell"

  llm-interface:
    versions:
      - version: "1.0.0"
        path: "cells.llm_interface.cell"
```

---

## Files to Build Next

### `core/config.py`
Loads agent yaml, validates it, returns dict for pipeline.

```python
# Build this — loads agents/stan.yaml
# Validates required fields: name, version, cells
# Returns dict handed to Pipeline.__init__
```

---

### `core/main.py`
FastAPI entry point. One POST endpoint to start.

```python
# Build this — FastAPI app
# POST /chat — accepts agent_name, user_message, session_id, mode
# Loads agent config via config.py
# Instantiates Registry and Pipeline
# Runs context through pipeline
# Returns response
```

---

### `agents/stan.yaml`

```yaml
name: stan
version: 0.1.0

cells:
  - name: mode-control
    version: "^1.0"
  - name: memory
    version: "^1.0"
    config:
      namespace: stan
  - name: ingestion
    version: "^1.0"
    config:
      sources:
        - type: prism
          namespace: stan
        - type: btc-clock
          feeds: [blocks, halving, mempool]
        - type: market
          feeds: [equities, indicators]
  - name: retrieval
    version: "^1.0"
    config:
      namespace: stan
  - name: context-builder
    version: "^1.0"
  - name: llm-interface
    version: "^1.0"
    config:
      model: llama-3.1-70b
      provider: together
      temperature: 0.5
```

---

### `cells/mode_control/cell.py` (real)

```python
# Build this — sets mode constraints on context
# web:      full responses, markdown ok, full history
# phone:    short answers, no markdown, tight history window
# embedded: scoped system prompt, rate check
# api:      raw output, no formatting
# Reads context.mode, writes constraints to context.meta
```

---

### `cells/llm_interface/cell.py` (real)

```python
# Build this — LiteLLM call
# Reads context.assembled_prompt
# Reads config: model, provider, temperature
# Calls litellm.acompletion()
# Writes response to context.response
# Streams if mode != "api"
```

---

### Stub Template (use for memory, ingestion, retrieval, context_builder)

```python
# cells/{name}/cell.py

from core.context import AgentContext

class Cell:
    name = "{name}"
    version = "1.0.0"

    def __init__(self, config: dict):
        self.config = config

    def init(self, config: dict) -> None:
        pass

    async def execute(self, context: AgentContext) -> AgentContext:
        # TODO: implement
        return context

    async def teardown(self) -> None:
        pass
```

Use this stub for:
- `cells/memory/cell.py`
- `cells/ingestion/cell.py`
- `cells/retrieval/cell.py`
- `cells/context_builder/cell.py`

---

## Dependencies

```
# requirements.txt
fastapi
uvicorn
pyyaml
litellm
langgraph
pinecone-client
asyncpg
pydantic
python-dotenv
```

---

## Environment Variables Needed

```
# .env
TOGETHER_API_KEY=
ANTHROPIC_API_KEY=
PINECONE_API_KEY=
PINECONE_ENV=
DATABASE_URL=
```

---

## First Spinup Test

Once all files are in place:

```bash
uvicorn core.main:app --reload
```

Then hit:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "stan",
    "user_message": "What is the current halving cycle telling us about the market?",
    "session_id": "test-001",
    "mode": "web"
  }'
```

Stan should respond. Pipeline should log each cell executing in sequence. If a cell fails the pipeline degrades gracefully and logs the error — it does not hard crash.

---

## Key Design Decisions (Do Not Change)

- Every cell implements the same interface — no exceptions
- AgentContext is the only thing that moves between cells
- No cell knows what other cells exist
- Pipeline degrades gracefully on cell failure — never hard crashes
- All cells are async
- Agent config lives in yaml — agents require zero Python code
- LiteLLM is the only LLM interface — no direct provider calls anywhere
- Prism handles all ingestion and retrieval — no custom data pipelines in cells

---

## Related Seed Docs

- `agentOS-architecture-seed.md` — full architecture spec and 6 layers
- `maurice-middleware-seed.md` — middleware pipeline between Maurice Railway and Maurice SaaS
- `blacksky-funding-landscape.md` — funding strategy

---

*End of handoff. Stan is the guinea pig. Break it, fix it, then integrate Maurice and Judy.*
