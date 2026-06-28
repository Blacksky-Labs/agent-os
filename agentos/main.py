"""FastAPI entry point.

* ``POST /chat`` — load the named agent, run the cell pipeline, fire hooks,
  return the response.
* ``GET /health`` — liveness check and a list of currently-loaded agents.

See SPEC.md §2.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from agentos import skipper_store
from agentos.config import ManifestError, load_manifest
from agentos.context import AgentContext
from agentos.hooks import HookDispatcher
from agentos.observability import log_event
from agentos.pipeline import Pipeline
from agentos.registry import Registry
from agentos.ui import INDEX_HTML
from agentos.dashboard_ui import DASHBOARD_HTML
from agentos.config_ui import CONFIG_HTML
from agentos.dbexplorer_ui import DB_EXPLORER_HTML


# --- Per-process caches (so we don't reload manifests / cells per request) ---
_pipelines: dict[str, Pipeline] = {}
_dispatchers: dict[str, HookDispatcher] = {}
_manifests: dict[str, dict] = {}
_cell_registry: Registry | None = None
_repo_root: Path | None = None
_running_agent: str | None = None       # the entity this process was started for
_active_session: str | None = None       # session clients adopt (start=new, resume=last)
_session_mode: str = "new"


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


async def _resolve_active_session() -> str:
    """start → a fresh session; resume → the running agent's most recent session."""
    if _session_mode == "resume" and _running_agent and _repo_root is not None:
        try:
            from cells.memory.store import db_path_for, latest_session

            manifest = load_manifest(_running_agent, repo_root=_repo_root)
            sid = await latest_session(db_path_for(manifest["namespace"], _repo_root))
            if sid:
                return sid
        except Exception:
            pass
    return f"s_{uuid.uuid4().hex[:12]}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Set up the kernel at startup, tear down at shutdown."""
    global _cell_registry, _repo_root, _running_agent, _active_session, _session_mode
    _repo_root = _find_repo_root()
    _running_agent = os.getenv("AGENTOS_AGENT")
    _session_mode = os.getenv("AGENTOS_SESSION_MODE", "new")
    _active_session = await _resolve_active_session()
    _cell_registry = Registry(_repo_root / "cells.registry.yaml", kind="cells")
    log_event(
        kind="kernel",
        namespace="*",
        turn_id="-",
        event="startup",
        repo_root=str(_repo_root),
        running_agent=_running_agent,
        session_mode=_session_mode,
        active_session=_active_session,
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


class ModelPatch(BaseModel):
    name: str | None = None
    provider: str | None = None
    api_base: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class ReasoningPatch(BaseModel):
    disabled_cells: list[str] = []
    disabled_hooks: list[str] = []


class CellConfigPatch(BaseModel):
    cell: str
    config: dict


class ReasoningModePatch(BaseModel):
    mode: str | None = None          # "single" | "moe" — swaps the generation slot
    moe: dict | None = None          # roster: {router_model, default, experts: [...]}


# Dashboard data patches — read + direct edit only (no create-from-dashboard;
# tasks/entities are authored by Skipper's reasoning loop). Fields mirror
# SKIPPER-DASH-SEED-001 Part 2.

class TaskPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    step_type: str | None = None


class EntityPatch(BaseModel):
    surface_form: str | None = None
    canonical_form: str | None = None
    entity_type: str | None = None


class DashboardPatch(BaseModel):
    pack: str                         # dashboard pack id to make active


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

    # Apply reasoning toggles — skip cells/hooks the operator turned off live.
    disabled_cells = set(manifest.get("_disabled_cells") or [])
    disabled_hooks = set(manifest.get("_disabled_hooks") or [])
    pipeline_manifest = manifest
    if disabled_cells:
        pipeline_manifest = {
            **manifest,
            "cells": [c for c in manifest.get("cells", []) if c.get("name") not in disabled_cells],
        }
    hooks_cfg = manifest.get("hooks", {}) or {}
    if disabled_hooks:
        hooks_cfg = {
            evt: [h for h in handlers if h.get("handler") not in disabled_hooks]
            for evt, handlers in hooks_cfg.items()
        }

    pipeline = Pipeline(pipeline_manifest, _cell_registry)
    dispatcher = HookDispatcher(hooks_cfg)

    _pipelines[agent_name] = pipeline
    _dispatchers[agent_name] = dispatcher
    _manifests[agent_name] = manifest       # full manifest (persona/model for chat())
    return pipeline, dispatcher, manifest


# --- Skipper data / dashboard-pack helpers ---

def _resolve_agent() -> tuple[str, str]:
    """(agent_name, namespace) for the running entity.

    The Skipper API routes (``/api/tasks`` etc.) have no agent in the path —
    they target whichever entity this kernel was started for (``AGENTOS_AGENT``).
    Falls back to the first scaffolded manifest so the routes still work when the
    kernel is launched without an explicit agent (e.g. ``agentos serve``).
    """
    if _repo_root is None:
        raise HTTPException(status_code=503, detail="Kernel not initialized")
    name = _running_agent
    if not name:
        manifests = sorted((_repo_root / "manifests").glob("*.yaml"))
        if not manifests:
            raise HTTPException(status_code=404, detail="No agent configured")
        name = manifests[0].stem
    try:
        namespace = load_manifest(name, repo_root=_repo_root)["namespace"]
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return name, namespace


def _dashboards_dir() -> Path:
    return (_repo_root or Path(".")) / "dashboards"


def _load_pack_manifest(pack_id: str) -> dict | None:
    manifest_path = _dashboards_dir() / pack_id / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _list_pack_manifests() -> list[dict]:
    out: list[dict] = []
    directory = _dashboards_dir()
    if directory.exists():
        for pack_dir in sorted(directory.iterdir()):
            if pack_dir.is_dir():
                manifest = _load_pack_manifest(pack_dir.name)
                if manifest:
                    out.append(manifest)
    return out


def _pack_compatible(manifest: dict, agent_name: str) -> bool:
    """A pack is shown to an agent if it lists that agent or the wildcard ``*``."""
    compatible = manifest.get("compatible_agents") or []
    return agent_name in compatible or "*" in compatible


# --- On-device model cache + first-launch load screen ---

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".tiff", ".tif", ".gif", ".bmp", ".webp"}


def _llama_cache_dir() -> Path:
    """Where the native llama-server caches its ``-hf`` model download — what the
    'wipe model' action removes. Honors ``$LLAMA_CACHE``, else the platform default
    (``~/Library/Caches/llama.cpp`` on macOS, ``~/.cache/llama.cpp`` elsewhere)."""
    override = os.getenv("LLAMA_CACHE")
    if override:
        return Path(override).expanduser()
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Caches" / "llama.cpp"
    return home / ".cache" / "llama.cpp"


def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            pass
    return total


def _slides_dir() -> Path | None:
    """Locate the bundled first-launch slideshow images across dev + packaged layouts."""
    candidates: list[Path] = []
    env = os.getenv("AGENTOS_SLIDES_DIR")
    if env:
        candidates.append(Path(env).expanduser())
    if _repo_root is not None:
        candidates.append(_repo_root.parent / "Slides")                       # macOS bundle: Resources/Slides
        candidates.append(_repo_root / "clients" / "AgentOSMac" / "Slides")    # dev tree
    # Prefer a dir that actually holds images; else the first dir that exists.
    for c in candidates:
        if c.is_dir() and any(p.suffix.lower() in _IMAGE_EXTS for p in c.iterdir()):
            return c
    for c in candidates:
        if c.is_dir():
            return c
    return None


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the local testing UI."""
    return HTMLResponse(content=INDEX_HTML)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the **active dashboard pack** — the swappable, primary non-chat UI.

    The macOS shell already loads this route in a WKWebView, so swapping packs
    (from the config screen) needs no native change: the operator selects a pack,
    this route serves that pack's ``entry_point`` on the next load. Falls back to
    the built-in analytics view if no pack resolves, so the tab never hard-breaks.
    """
    try:
        _, namespace = _resolve_agent()
        from agentos.config import active_dashboard_pack

        pack_id = active_dashboard_pack(namespace, _repo_root)
        manifest = _load_pack_manifest(pack_id) or _load_pack_manifest("skipper-default")
        if manifest:
            pack_dir = _dashboards_dir() / manifest["id"]
            entry = pack_dir / manifest.get("entry_point", "index.html")
            if entry.is_file():
                return HTMLResponse(content=entry.read_text(encoding="utf-8"))
    except HTTPException:
        pass
    except Exception as e:  # never let the dashboard tab 500
        log_event(kind="dashboard", namespace="*", turn_id="-", event="pack_load_failed", error=str(e))
    return HTMLResponse(content=DASHBOARD_HTML)


@app.get("/overview", response_class=HTMLResponse)
async def overview():
    """The built-in activity + analytics view (shipped before dashboard packs).
    Preserved here and available as the ``skipper-analytics`` fallback."""
    return HTMLResponse(content=DASHBOARD_HTML)


@app.get("/dashboards/{pack_id}/{file_path:path}")
async def dashboard_pack_asset(pack_id: str, file_path: str):
    """Serve a static file from a dashboard pack (for multi-file packs/assets).

    Single-file packs don't need this, but the manifest spec permits an
    ``assets/`` folder, so the kernel serves the whole pack directory with a
    path-traversal guard.
    """
    base = (_dashboards_dir() / pack_id).resolve()
    target = (base / file_path).resolve()
    if base != target and not str(target).startswith(str(base) + os.sep):
        raise HTTPException(status_code=403, detail="Path outside pack")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target)


@app.get("/config", response_class=HTMLResponse)
async def config_page():
    """Serve the config page (running entity's manifest + reset)."""
    return HTMLResponse(content=CONFIG_HTML)


@app.get("/db", response_class=HTMLResponse)
async def db_page():
    """Serve the DB explorer (read-only window into the entity's memory.db)."""
    return HTMLResponse(content=DB_EXPLORER_HTML)


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


@app.get("/stats")
async def stats_all():
    """Fleet overview — headline numbers for every scaffolded entity."""
    if _repo_root is None:
        return {"agents": []}
    from agentos.analytics import fleet_summary

    pairs: list[tuple[str, str]] = []
    for path in sorted((_repo_root / "manifests").glob("*.yaml")):
        try:
            m = load_manifest(path.stem, repo_root=_repo_root)
            pairs.append((path.stem, m["namespace"]))
        except ManifestError:
            continue
    return {"agents": fleet_summary(pairs, repo_root=_repo_root)}


@app.get("/agents/{agent_name}/stats")
async def agent_stats(agent_name: str):
    """Per-entity analytics for the dashboard."""
    if _repo_root is None:
        raise HTTPException(status_code=503, detail="Kernel not initialized")
    try:
        manifest = load_manifest(agent_name, repo_root=_repo_root)
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e))
    from agentos.analytics import entity_stats

    return entity_stats(manifest["namespace"], repo_root=_repo_root)


@app.get("/agents/{agent_name}/config")
async def agent_config(agent_name: str):
    """The entity's configuration (manifest view) for the config page."""
    if _repo_root is None:
        raise HTTPException(status_code=503, detail="Kernel not initialized")
    try:
        manifest = load_manifest(agent_name, repo_root=_repo_root)
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e))
    persona = manifest.get("_persona_data", {}) or {}
    model = manifest.get("model", {}) or {}
    return {
        "name": manifest["name"],
        "version": manifest["version"],
        "namespace": manifest["namespace"],
        "display_name": persona.get("display_name") or manifest["name"],
        "model": {
            "provider": model.get("provider"),
            "name": model.get("name"),
            "api_base": model.get("api_base"),
            "temperature": model.get("temperature"),
            "max_tokens": model.get("max_tokens"),
        },
        "cells": [
            {"name": c.get("name"), "version": c.get("version"), "config": c.get("config", {})}
            for c in (manifest.get("cells") or [])
        ],
        "hooks": {
            evt: [h.get("handler") for h in handlers]
            for evt, handlers in (manifest.get("hooks") or {}).items()
        },
        "disabled_cells": manifest.get("_disabled_cells", []),
        "disabled_hooks": manifest.get("_disabled_hooks", []),
        "reasoning_mode": manifest.get("_reasoning_mode", "single"),
        "moe": next(
            (c.get("config", {}) for c in (manifest.get("cells") or []) if c.get("name") == "moe"),
            None,
        ),
        "modes": list((persona.get("modes") or {}).keys()),
    }


@app.delete("/agents/{agent_name}/history")
async def wipe_history(agent_name: str):
    """Reset an entity to newborn — delete its memory.db (turns, threads, metrics)."""
    if _repo_root is None:
        raise HTTPException(status_code=503, detail="Kernel not initialized")
    try:
        manifest = load_manifest(agent_name, repo_root=_repo_root)
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e))
    from cells.memory.store import db_path_for, init_store

    namespace = manifest["namespace"]
    db = db_path_for(namespace, _repo_root)
    existed = db.exists()
    if existed:
        db.unlink()
    # Drop cached pipeline so the next turn rebuilds fresh, then recreate the
    # empty schema so reads on the next turn don't hit a missing table.
    _pipelines.pop(agent_name, None)
    _dispatchers.pop(agent_name, None)
    _manifests.pop(agent_name, None)
    await init_store(namespace, repo_root=_repo_root)
    return {"wiped": existed, "namespace": namespace}


@app.get("/agents/{agent_name}/db")
async def agent_db(agent_name: str):
    """Read-only snapshot of the entity's memory.db for the DB explorer."""
    if _repo_root is None:
        raise HTTPException(status_code=503, detail="Kernel not initialized")
    try:
        manifest = load_manifest(agent_name, repo_root=_repo_root)
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e))
    from agentos.analytics import db_overview

    return db_overview(manifest["namespace"], repo_root=_repo_root)


@app.get("/models")
async def list_models():
    """Models available to swap to — locally installed Ollama models, queried live."""
    import json
    import urllib.request

    api_base = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")

    def _fetch() -> dict:
        req = urllib.request.Request(api_base.rstrip("/") + "/api/tags")
        with urllib.request.urlopen(req, timeout=2.5) as r:
            return json.loads(r.read())

    models: list[dict] = []
    try:
        data = await asyncio.to_thread(_fetch)
        for m in data.get("models", []):
            tag = m.get("name")
            if tag:
                models.append({
                    "name": f"ollama/{tag}",
                    "label": f"{tag} · local",
                    "provider": "ollama",
                    "api_base": api_base,
                })
    except Exception:
        pass  # Ollama unreachable — UI falls back to current model + custom entry
    return {"models": models, "source": "ollama"}


@app.patch("/agents/{agent_name}/model")
async def update_model(agent_name: str, patch: ModelPatch):
    """Live model swap — write the overlay, drop the cached pipeline so the next
    turn rebuilds with the new model/params."""
    if _repo_root is None:
        raise HTTPException(status_code=503, detail="Kernel not initialized")
    try:
        load_manifest(agent_name, repo_root=_repo_root)
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e))
    from agentos.config import save_model_override

    namespace = load_manifest(agent_name, repo_root=_repo_root)["namespace"]
    save_model_override(namespace, _repo_root, patch.model_dump())
    _pipelines.pop(agent_name, None)
    _dispatchers.pop(agent_name, None)
    _manifests.pop(agent_name, None)
    updated = load_manifest(agent_name, repo_root=_repo_root)
    return {"model": updated.get("model", {}), "overridden": updated.get("_overridden", False)}


@app.delete("/agents/{agent_name}/overrides")
async def reset_overrides(agent_name: str):
    """Reset live config to manifest defaults (delete the overlay)."""
    if _repo_root is None:
        raise HTTPException(status_code=503, detail="Kernel not initialized")
    try:
        namespace = load_manifest(agent_name, repo_root=_repo_root)["namespace"]
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e))
    from agentos.config import clear_overrides

    cleared = clear_overrides(namespace, _repo_root)
    _pipelines.pop(agent_name, None)
    _dispatchers.pop(agent_name, None)
    _manifests.pop(agent_name, None)
    return {"reset": cleared}


@app.patch("/agents/{agent_name}/reasoning")
async def update_reasoning(agent_name: str, patch: ReasoningPatch):
    """Live toggle of which cells/hooks run. Writes the overlay, drops the cache
    so the next turn rebuilds the pipeline without the disabled pieces."""
    if _repo_root is None:
        raise HTTPException(status_code=503, detail="Kernel not initialized")
    try:
        namespace = load_manifest(agent_name, repo_root=_repo_root)["namespace"]
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e))
    from agentos.config import save_toggles

    save_toggles(namespace, _repo_root, patch.disabled_cells, patch.disabled_hooks)
    _pipelines.pop(agent_name, None)
    _dispatchers.pop(agent_name, None)
    _manifests.pop(agent_name, None)
    return {"disabled_cells": patch.disabled_cells, "disabled_hooks": patch.disabled_hooks}


@app.patch("/agents/{agent_name}/reasoning-mode")
async def update_reasoning_mode(agent_name: str, patch: ReasoningModePatch):
    """Live swap of the reasoning slot: single-model (llm-interface) <-> MoE.
    The `moe` body carries the expert roster the config dashboard edits."""
    if _repo_root is None:
        raise HTTPException(status_code=503, detail="Kernel not initialized")
    try:
        namespace = load_manifest(agent_name, repo_root=_repo_root)["namespace"]
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e))
    from agentos.config import save_reasoning_mode

    save_reasoning_mode(namespace, _repo_root, mode=patch.mode, moe_config=patch.moe)
    _pipelines.pop(agent_name, None)
    _dispatchers.pop(agent_name, None)
    _manifests.pop(agent_name, None)
    updated = load_manifest(agent_name, repo_root=_repo_root)
    reasoning_cell = next(
        (c for c in updated.get("cells", []) if c.get("name") in ("llm-interface", "moe")),
        {},
    )
    return {
        "mode": updated.get("_reasoning_mode"),
        "roster": reasoning_cell.get("config", {}) if reasoning_cell.get("name") == "moe" else None,
    }


@app.patch("/agents/{agent_name}/cell-config")
async def update_cell_config(agent_name: str, patch: CellConfigPatch):
    """Live per-cell config (e.g. context-builder.surface_threads, memory.max_history)."""
    if _repo_root is None:
        raise HTTPException(status_code=503, detail="Kernel not initialized")
    try:
        namespace = load_manifest(agent_name, repo_root=_repo_root)["namespace"]
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e))
    from agentos.config import save_cell_config

    save_cell_config(namespace, _repo_root, patch.cell, patch.config)
    _pipelines.pop(agent_name, None)
    _dispatchers.pop(agent_name, None)
    _manifests.pop(agent_name, None)
    return {"cell": patch.cell, "config": patch.config}


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
    """Inventory of an agent's retrieval corpus.

    Includes:
    - ``sources``: every distinct file path the collection knows about
      and how many chunks it contributed
    - ``drop_folder_*``: state of the agent's default drop folder at
      ``corpus/<agent>/`` — what's there and whether each file is
      represented in the collection
    """
    if _repo_root is None:
        raise HTTPException(status_code=503, detail="Kernel not initialized")
    try:
        manifest = load_manifest(agent_name, repo_root=_repo_root)
    except ManifestError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Import lazily so agents that don't use retrieval don't pay the cost
    from cells.retrieval.ingest import discover_files
    from cells.retrieval.store import count, list_sources, open_collection

    namespace = manifest["namespace"]
    collection = await open_collection(namespace, repo_root=_repo_root)
    sources = await list_sources(collection)
    total = await count(collection)

    # Drop folder inventory
    drop_folder = _repo_root / "corpus" / agent_name
    drop_folder_exists = drop_folder.exists()
    chunks_by_source: dict[str, int] = {s["source"]: s["chunks"] for s in sources}
    drop_folder_files: list[dict] = []
    if drop_folder_exists:
        for f in discover_files(drop_folder):
            full_path = str(f.resolve())
            drop_folder_files.append({
                "path": full_path,
                "name": f.name,
                "in_corpus": full_path in chunks_by_source,
                "chunks": chunks_by_source.get(full_path, 0),
            })

    return {
        "agent_name": agent_name,
        "namespace": namespace,
        "total_chunks": total,
        "drop_folder": f"corpus/{agent_name}",
        "drop_folder_abs": str(drop_folder),
        "drop_folder_exists": drop_folder_exists,
        "drop_folder_files": drop_folder_files,
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


# ----------------------------------------------------------------------
# Skipper API — tasks, entities, and dashboard packs (SKIPPER-DASH-SEED-001).
# Routes target the running entity's per-namespace memory.db; no agent in the
# path. Dashboard is read + direct edit only for the MVP.
# ----------------------------------------------------------------------

@app.get("/api/tasks")
async def api_list_tasks(status: str | None = None):
    _, namespace = _resolve_agent()
    db = skipper_store.db_path_for(namespace, _repo_root)
    return await asyncio.to_thread(skipper_store.list_tasks, db, status)


@app.get("/api/tasks/{task_id}")
async def api_get_task(task_id: str):
    _, namespace = _resolve_agent()
    db = skipper_store.db_path_for(namespace, _repo_root)
    task = await asyncio.to_thread(skipper_store.get_task, db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.patch("/api/tasks/{task_id}")
async def api_update_task(task_id: str, patch: TaskPatch):
    _, namespace = _resolve_agent()
    db = skipper_store.db_path_for(namespace, _repo_root)
    task = await asyncio.to_thread(
        skipper_store.update_task, db, task_id, patch.model_dump()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.delete("/api/tasks/{task_id}")
async def api_delete_task(task_id: str):
    _, namespace = _resolve_agent()
    db = skipper_store.db_path_for(namespace, _repo_root)
    deleted = await asyncio.to_thread(skipper_store.delete_task, db, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": task_id}


@app.get("/api/entities")
async def api_list_entities(entity_type: str | None = None):
    _, namespace = _resolve_agent()
    db = skipper_store.db_path_for(namespace, _repo_root)
    return await asyncio.to_thread(skipper_store.list_entities, db, entity_type)


@app.get("/api/entities/{entity_id}")
async def api_get_entity(entity_id: str):
    _, namespace = _resolve_agent()
    db = skipper_store.db_path_for(namespace, _repo_root)
    entity = await asyncio.to_thread(skipper_store.get_entity, db, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@app.get("/api/entities/{entity_id}/linked")
async def api_entity_linked(entity_id: str):
    """The entity plus any tasks it links to via (source_type, source_id)."""
    _, namespace = _resolve_agent()
    db = skipper_store.db_path_for(namespace, _repo_root)
    result = await asyncio.to_thread(skipper_store.entity_linked, db, entity_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return result


@app.patch("/api/entities/{entity_id}")
async def api_update_entity(entity_id: str, patch: EntityPatch):
    _, namespace = _resolve_agent()
    db = skipper_store.db_path_for(namespace, _repo_root)
    entity = await asyncio.to_thread(
        skipper_store.update_entity, db, entity_id, patch.model_dump()
    )
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@app.delete("/api/entities/{entity_id}")
async def api_delete_entity(entity_id: str):
    _, namespace = _resolve_agent()
    db = skipper_store.db_path_for(namespace, _repo_root)
    deleted = await asyncio.to_thread(skipper_store.delete_entity, db, entity_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"deleted": entity_id}


@app.get("/api/manifest")
async def api_active_manifest():
    """Manifest of the currently-active dashboard pack for the running entity."""
    from agentos.config import active_dashboard_pack

    agent_name, namespace = _resolve_agent()
    pack_id = active_dashboard_pack(namespace, _repo_root)
    manifest = _load_pack_manifest(pack_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Active dashboard pack manifest not found")
    manifest = {**manifest, "_active": True, "_agent": agent_name}
    return manifest


@app.get("/api/dashboards")
async def api_list_dashboards():
    """Available dashboard packs for the config picker.

    Filtered by ``compatible_agents`` (Part 5 filter rule): only packs that list
    the running agent or ``*`` are returned. Each manifest is annotated with
    ``_active`` so the picker can preselect the current pack.
    """
    from agentos.config import active_dashboard_pack

    agent_name, namespace = _resolve_agent()
    active = active_dashboard_pack(namespace, _repo_root)
    packs = [m for m in _list_pack_manifests() if _pack_compatible(m, agent_name)]
    for m in packs:
        m["_active"] = m.get("id") == active
    return packs


@app.patch("/api/dashboard")
async def api_set_dashboard(patch: DashboardPatch):
    """Swap the active dashboard pack — the dashboard equivalent of a model swap.

    Validates the pack exists and is compatible with the running agent, then
    persists the selection to the per-namespace overlay. The dashboard surface
    (``/dashboard``) serves the new pack on its next load.
    """
    from agentos.config import save_dashboard_pack

    agent_name, namespace = _resolve_agent()
    manifest = _load_pack_manifest(patch.pack)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Dashboard pack '{patch.pack}' not found")
    if not _pack_compatible(manifest, agent_name):
        raise HTTPException(
            status_code=400,
            detail=f"Pack '{patch.pack}' is not compatible with agent '{agent_name}'",
        )
    save_dashboard_pack(namespace, _repo_root, patch.pack)
    return {"active_dashboard_pack": patch.pack, "name": manifest.get("name")}


# ----------------------------------------------------------------------
# On-device model wipe + first-launch load-screen preview.
# ----------------------------------------------------------------------

@app.delete("/system/model")
async def wipe_model():
    """Delete the downloaded on-device model so the next launch re-downloads it
    (and replays the first-launch load screen). The native llama-server owns this
    cache; the kernel just clears it from disk. Memory is untouched."""
    cache = _llama_cache_dir()
    home = Path.home()
    # Safety: never delete root, the home dir, or an ancestor of home.
    if not cache.is_absolute() or cache == Path(cache.anchor) or cache == home or cache in home.parents:
        raise HTTPException(status_code=400, detail=f"Refusing to delete unsafe path: {cache}")
    if not cache.exists():
        return {"wiped": False, "freed_bytes": 0, "path": str(cache)}
    freed = _dir_size(cache)
    await asyncio.to_thread(shutil.rmtree, cache, ignore_errors=True)
    return {"wiped": True, "freed_bytes": freed, "path": str(cache)}


@app.get("/loadscreen", response_class=HTMLResponse)
async def loadscreen():
    """Preview the first-launch slideshow (a web mirror of the native load screen)."""
    from agentos.loadscreen_ui import LOADSCREEN_HTML

    return HTMLResponse(content=LOADSCREEN_HTML)


@app.get("/loadscreen/images")
async def loadscreen_images():
    """Filenames of the bundled slideshow images, in display order."""
    directory = _slides_dir()
    if directory is None:
        return {"images": [], "count": 0}
    names = sorted(
        (p.name for p in directory.iterdir() if p.suffix.lower() in _IMAGE_EXTS),
        key=str.lower,
    )
    return {"images": names, "count": len(names)}


@app.get("/loadscreen/img/{name}")
async def loadscreen_img(name: str):
    """Serve one slideshow image (no subpaths, image extensions only)."""
    directory = _slides_dir()
    if directory is None:
        raise HTTPException(status_code=404, detail="No slides directory")
    base = directory.resolve()
    target = (base / name).resolve()
    if target.parent != base or not target.is_file() or target.suffix.lower() not in _IMAGE_EXTS:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "running_agent": _running_agent,
        "active_session": _active_session,
        "session_mode": _session_mode,
        "agents_loaded": list(_pipelines.keys()),
        "cells_available": _cell_registry.list_names() if _cell_registry else [],
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, background: BackgroundTasks):
    pipeline, dispatcher, manifest = _get_pipeline(req.agent_name)

    context = AgentContext(
        agent_name=req.agent_name,
        namespace=pipeline.namespace,
        session_id=req.session_id or _active_session or "default",
        user_id=req.user_id,
        mode=req.mode,
        user_message=req.user_message,
        persona=manifest.get("_persona_data", {}),
        meta={
            "model": manifest.get("model", {}),
            "owner": manifest.get("owner"),
            "multi_user": bool(manifest.get("multi_user", False)),
        },
    )

    await dispatcher.fire("before_turn", context)
    t0 = time.perf_counter()
    context = await pipeline.run(context)
    context.meta["turn_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    response = ChatResponse(
        response=context.response,
        turn_id=context.turn_id,
        namespace=context.namespace,
        cell_timings=context.cell_timings,
        cell_errors=context.cell_errors,
        usage=context.meta.get("last_usage"),
    )
    # after_turn (memory, threads, metrics, and the LLM signal pass) runs AFTER
    # the response is sent — none of it adds latency to the reply.
    background.add_task(dispatcher.fire, "after_turn", context)
    return response
