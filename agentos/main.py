"""FastAPI entry point.

* ``POST /chat`` — load the named agent, run the cell pipeline, fire hooks,
  return the response.
* ``GET /health`` — liveness check and a list of currently-loaded agents.

See SPEC.md §2.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from agentos.config import ManifestError, load_manifest
from agentos.context import AgentContext
from agentos.hooks import HookDispatcher
from agentos.observability import log_event
from agentos.pipeline import Pipeline
from agentos.registry import Registry
from agentos.ui import INDEX_HTML


# --- Per-process caches (so we don't reload manifests / cells per request) ---
_pipelines: dict[str, Pipeline] = {}
_dispatchers: dict[str, HookDispatcher] = {}
_manifests: dict[str, dict] = {}
_cell_registry: Registry | None = None
_repo_root: Path | None = None


def _find_repo_root() -> Path:
    """Walk up from cwd until cells.registry.yaml is found."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "cells.registry.yaml").exists():
            return parent
    raise RuntimeError(
        "cells.registry.yaml not found in cwd or any parent. "
        "Run agentos from the repo root."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Set up the kernel at startup, tear down at shutdown."""
    global _cell_registry, _repo_root
    _repo_root = _find_repo_root()
    _cell_registry = Registry(_repo_root / "cells.registry.yaml", kind="cells")
    log_event(
        kind="kernel",
        namespace="*",
        turn_id="-",
        event="startup",
        repo_root=str(_repo_root),
        cells_available=_cell_registry.list_names(),
    )
    yield
    for pipeline in _pipelines.values():
        await pipeline.teardown()
    log_event(kind="kernel", namespace="*", turn_id="-", event="shutdown")


app = FastAPI(title="AgentOS", version="0.1.0", lifespan=lifespan)


# --- Request / response models ---

class ChatRequest(BaseModel):
    agent_name: str
    user_message: str
    session_id: str
    mode: str = "web"
    user_id: str | None = None


class ChatResponse(BaseModel):
    response: str | None
    turn_id: str
    namespace: str
    cell_timings: dict
    cell_errors: dict
    usage: dict | None = None       # populated by llm-interface (token counts)


# --- Helpers ---

def _get_pipeline(agent_name: str) -> tuple[Pipeline, HookDispatcher, dict]:
    """Lazily load (and cache) a pipeline + dispatcher for an agent."""
    if agent_name in _pipelines:
        return _pipelines[agent_name], _dispatchers[agent_name], _manifests[agent_name]

    if _cell_registry is None or _repo_root is None:
        raise RuntimeError("Kernel not initialized — call /health first.")

    try:
        manifest = load_manifest(agent_name, repo_root=_repo_root)
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e))

    pipeline = Pipeline(manifest, _cell_registry)
    dispatcher = HookDispatcher(manifest.get("hooks", {}))

    _pipelines[agent_name] = pipeline
    _dispatchers[agent_name] = dispatcher
    _manifests[agent_name] = manifest
    return pipeline, dispatcher, manifest


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the local testing UI."""
    return HTMLResponse(content=INDEX_HTML)


@app.get("/agents")
async def list_agents():
    """List scaffolded agents (everything in manifests/*.yaml).

    For each agent, returns name + display_name (from persona) + provider
    + model so the UI can render a useful picker.
    """
    if _repo_root is None:
        return {"agents": []}
    out: list[dict] = []
    manifests_dir = _repo_root / "manifests"
    if not manifests_dir.exists():
        return {"agents": []}
    for path in sorted(manifests_dir.glob("*.yaml")):
        name = path.stem
        entry: dict = {"name": name}
        try:
            m = load_manifest(name, repo_root=_repo_root)
            entry["display_name"] = (
                m.get("_persona_data", {}).get("display_name") or name
            )
            model = m.get("model", {}) or {}
            entry["provider"] = model.get("provider")
            entry["model"] = model.get("name")
        except ManifestError:
            # Broken manifest still shows up by name; user can fix it.
            entry["display_name"] = name
            entry["error"] = "manifest invalid"
        out.append(entry)
    return {"agents": out}


# ----------------------------------------------------------------------
# Corpus management — list, ingest, delete files in an agent's RAG store
# ----------------------------------------------------------------------

def _retrieval_config_for(manifest: dict) -> dict | None:
    """Pull the retrieval cell's config block from a manifest, if present."""
    for entry in (manifest.get("cells") or []):
        if entry.get("name") == "retrieval":
            return entry.get("config", {}) or {}
    return None


@app.get("/agents/{agent_name}/corpus")
async def corpus_list(agent_name: str):
    """List the sources in an agent's retrieval corpus, grouped by file."""
    if _repo_root is None:
        raise HTTPException(status_code=503, detail="Kernel not initialized")
    try:
        manifest = load_manifest(agent_name, repo_root=_repo_root)
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Import lazily so agents that don't use retrieval don't pay the cost
    from cells.retrieval.store import count, list_sources, open_collection

    namespace = manifest["namespace"]
    collection = await open_collection(namespace, repo_root=_repo_root)
    sources = await list_sources(collection)
    total = await count(collection)
    return {
        "agent_name": agent_name,
        "namespace": namespace,
        "total_chunks": total,
        "sources": sources,
    }


class IngestRequest(BaseModel):
    path: str


@app.post("/agents/{agent_name}/ingest")
async def corpus_ingest(agent_name: str, req: IngestRequest):
    """Ingest a file or folder into an agent's corpus.

    The path is interpreted on the *server* host (since agentOS runs
    locally for now). For folder paths, all supported files are walked
    recursively. Idempotent: re-ingesting the same content is a no-op.
    """
    if _repo_root is None:
        raise HTTPException(status_code=503, detail="Kernel not initialized")
    try:
        manifest = load_manifest(agent_name, repo_root=_repo_root)
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e))

    retrieval_cfg = _retrieval_config_for(manifest)
    if retrieval_cfg is None:
        raise HTTPException(
            status_code=400,
            detail=f"Agent '{agent_name}' has no retrieval cell in its manifest",
        )

    target = Path(req.path).expanduser()
    if not target.exists():
        raise HTTPException(
            status_code=400, detail=f"Path not found on server: {target}"
        )

    from cells.retrieval.ingest import ingest_path

    embedding_model = retrieval_cfg.get(
        "embedding_model", "ollama/nomic-embed-text:latest"
    )
    embedding_api_base = retrieval_cfg.get(
        "embedding_api_base", "http://localhost:11434"
    )

    try:
        stats = await ingest_path(
            namespace=manifest["namespace"],
            path=target,
            embedding_model=embedding_model,
            embedding_api_base=embedding_api_base,
            repo_root=_repo_root,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Ingest failed: {type(e).__name__}: {e}"
        )

    return stats


@app.delete("/agents/{agent_name}/corpus")
async def corpus_delete_source(agent_name: str, source: str):
    """Remove every chunk for a given source from an agent's corpus.

    The ``source`` query parameter must match the metadata.source field
    exactly (it's the full filesystem path used at ingest time).
    """
    if _repo_root is None:
        raise HTTPException(status_code=503, detail="Kernel not initialized")
    try:
        manifest = load_manifest(agent_name, repo_root=_repo_root)
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e))

    from cells.retrieval.store import delete_source, open_collection

    collection = await open_collection(manifest["namespace"], repo_root=_repo_root)
    deleted = await delete_source(collection, source)
    return {"source": source, "deleted_chunks": deleted}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "agents_loaded": list(_pipelines.keys()),
        "cells_available": _cell_registry.list_names() if _cell_registry else [],
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    pipeline, dispatcher, manifest = _get_pipeline(req.agent_name)

    context = AgentContext(
        agent_name=req.agent_name,
        namespace=pipeline.namespace,
        session_id=req.session_id,
        user_id=req.user_id,
        mode=req.mode,
        user_message=req.user_message,
        persona=manifest.get("_persona_data", {}),
        meta={"model": manifest.get("model", {})},
    )

    await dispatcher.fire("before_turn", context)
    context = await pipeline.run(context)
    await dispatcher.fire("after_turn", context)

    return ChatResponse(
        response=context.response,
        turn_id=context.turn_id,
        namespace=context.namespace,
        cell_timings=context.cell_timings,
        cell_errors=context.cell_errors,
        usage=context.meta.get("last_usage"),
    )
