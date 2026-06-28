# SKIPPER-DASH-SEED-001
## Skipper Dashboard Pack v1 — Tasks + Entities + Config Picker

**For:** CoWork  
**From:** Architecture  
**Status:** Ready to build  
**Scope:** MVP — Tasks view, Entities view, dashboard pack manifest spec, config screen Dashboard picker

---

## MANDATORY AUDIT PHASE

Before any build work, CoWork must answer the following and report back:

1. What is the current SQLite schema for Tasks? Paste the `CREATE TABLE` statement.
2. Is there an existing Entities table? If yes, paste the schema. If no, confirm there is none.
3. What port is the Skipper local Python API currently running on?
4. Does the config screen already have a picker component (used for DB and LLM)? If yes, paste the component signature or file path.
5. Where does Skipper currently store its data directory? (Path where SQLite file lives.)
6. Is there an existing `dashboards/` directory or equivalent? If not, confirm the working directory structure.

**Do not proceed past this section until all six answers are provided.**

---

## CONTEXT

AgentOS runs Skipper as a personal macOS agent with on-device Gemma 4 inference. Skipper identifies entities via NLP and manages Goals and Tasks in a local SQLite store. The dashboard is the user's primary non-chat interface to Skipper — a way to see, manage, and interact with what Skipper knows and is doing.

**Design constraint:** Everything built here must be iOS-friendly from day one. All UI is web-based (HTML/CSS/JS) delivered via WKWebView on macOS/iOS and WebView on Android. No platform-specific UI code in dashboard packs.

**Swap contract:** Dashboard packs are swappable by the user from the config screen, the same way DB backend and LLM provider are swapped today. This is not a future concern — the swap contract must be established in this build.

---

## ARCHITECTURE

```
Skipper Local API (Python, FastAPI)
    └── /api/tasks          → Tasks endpoint
    └── /api/entities       → Entities endpoint
    └── /api/manifest       → Returns active dashboard pack manifest

Dashboard Packs Directory
    └── /dashboards/
        └── skipper-default/
            ├── manifest.json
            ├── index.html
            └── assets/
                ├── style.css
                └── app.js

Native Shell (macOS: WKWebView, iOS: WKWebView, Android: WebView)
    └── Loads index.html from active dashboard pack
    └── Passes base API URL as query param or injected JS variable

Config Screen
    └── Dashboard Picker (new, matches DB/LLM picker pattern)
        └── Reads available packs from /dashboards/
        └── Reads manifest.json from each pack
        └── Filters by compatible_agents field
        └── Writes active pack selection to Skipper config
```

---

## PART 1 — SQLITE SCHEMA

### Tasks Table

```sql
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
        -- pending | active | complete | escalated | cancelled
    step_type TEXT NOT NULL DEFAULT 'autonomous',
        -- autonomous | breakpoint | handoff | conditional
    parent_task_id TEXT REFERENCES tasks(id),
    goal_id TEXT,
        -- references goals.id when Goals table exists; nullable for now
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    metadata TEXT
        -- JSON blob for extension without schema migration
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_goal ON tasks(goal_id);
```

**Notes:**
- Completed tasks are deleted, not archived. `completed_at` is a soft marker before deletion runs.
- `metadata` is a JSON string — use for anything not in the core schema without touching the table structure.
- `step_type` maps directly to AO-SPEC-004 typed execution model.

### Entities Table

```sql
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    surface_form TEXT NOT NULL,
        -- the raw text as extracted ("Dr. Angela Davis", "Baltimore", "USDA")
    entity_type TEXT NOT NULL,
        -- PERSON | ORG | PLACE | CONCEPT | EVENT | OTHER
    canonical_form TEXT,
        -- normalized/resolved form if known
    confidence REAL DEFAULT 1.0,
        -- 0.0–1.0, NLP extraction confidence
    source_type TEXT,
        -- task | goal | message | document
    source_id TEXT,
        -- id of the source record
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata TEXT
        -- JSON blob for tags, aliases, notes
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_source ON entities(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_entities_surface ON entities(surface_form);
```

---

## PART 2 — PYTHON LOCAL API

**Stack:** FastAPI + uvicorn. Runs as a local service on Skipper's data port.

### File: `skipper_api.py`

```python
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3, json, uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

app = FastAPI(title="Skipper Local API", version="1.0.0")

# Allow WKWebView and local file origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

DB_PATH = Path.home() / ".skipper" / "skipper.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def now():
    return datetime.utcnow().isoformat()


# ── TASKS ──────────────────────────────────────────────

@app.get("/api/tasks")
def list_tasks(status: Optional[str] = None):
    conn = get_db()
    if status:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC",
            (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return dict(row)

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    step_type: Optional[str] = None

@app.patch("/api/tasks/{task_id}")
def update_task(task_id: str, body: TaskUpdate):
    conn = get_db()
    existing = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Task not found")
    updates = {k: v for k, v in body.dict().items() if v is not None}
    updates["updated_at"] = now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE tasks SET {set_clause} WHERE id = ?",
        (*updates.values(), task_id)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row)

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    conn = get_db()
    existing = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Task not found")
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return {"deleted": task_id}


# ── ENTITIES ───────────────────────────────────────────

@app.get("/api/entities")
def list_entities(entity_type: Optional[str] = None):
    conn = get_db()
    if entity_type:
        rows = conn.execute(
            "SELECT * FROM entities WHERE entity_type = ? ORDER BY surface_form ASC",
            (entity_type,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM entities ORDER BY entity_type ASC, surface_form ASC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/entities/{entity_id}")
def get_entity(entity_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Entity not found")
    return dict(row)

@app.get("/api/entities/{entity_id}/linked")
def get_entity_linked(entity_id: str):
    """Return tasks linked to this entity via source_id."""
    conn = get_db()
    entity = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if not entity:
        conn.close()
        raise HTTPException(status_code=404, detail="Entity not found")
    entity_dict = dict(entity)
    tasks = []
    if entity_dict.get("source_type") == "task" and entity_dict.get("source_id"):
        task = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (entity_dict["source_id"],)
        ).fetchone()
        if task:
            tasks = [dict(task)]
    conn.close()
    return {"entity": entity_dict, "linked_tasks": tasks}

class EntityUpdate(BaseModel):
    surface_form: Optional[str] = None
    canonical_form: Optional[str] = None
    entity_type: Optional[str] = None

@app.patch("/api/entities/{entity_id}")
def update_entity(entity_id: str, body: EntityUpdate):
    conn = get_db()
    existing = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Entity not found")
    updates = {k: v for k, v in body.dict().items() if v is not None}
    updates["updated_at"] = now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE entities SET {set_clause} WHERE id = ?",
        (*updates.values(), entity_id)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    conn.close()
    return dict(row)

@app.delete("/api/entities/{entity_id}")
def delete_entity(entity_id: str):
    conn = get_db()
    existing = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Entity not found")
    conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
    conn.commit()
    conn.close()
    return {"deleted": entity_id}


# ── MANIFEST ───────────────────────────────────────────

@app.get("/api/manifest")
def get_active_manifest():
    """Return the manifest of the currently active dashboard pack."""
    config_path = Path.home() / ".skipper" / "config.json"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Config not found")
    config = json.loads(config_path.read_text())
    active_pack = config.get("active_dashboard_pack", "skipper-default")
    dashboards_dir = Path(__file__).parent / "dashboards"
    manifest_path = dashboards_dir / active_pack / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard pack manifest not found")
    return json.loads(manifest_path.read_text())

@app.get("/api/dashboards")
def list_dashboard_packs():
    """Return all available dashboard packs for the config picker."""
    dashboards_dir = Path(__file__).parent / "dashboards"
    packs = []
    if dashboards_dir.exists():
        for pack_dir in dashboards_dir.iterdir():
            if pack_dir.is_dir():
                manifest_path = pack_dir / "manifest.json"
                if manifest_path.exists():
                    manifest = json.loads(manifest_path.read_text())
                    packs.append(manifest)
    return packs
```

---

## PART 3 — DASHBOARD PACK MANIFEST SPEC

### File: `dashboards/skipper-default/manifest.json`

```json
{
  "id": "skipper-default",
  "name": "Skipper Default",
  "version": "1.0.0",
  "description": "Personal dashboard for Skipper. Tasks and entities, inline editing, direct interaction.",
  "author": "Blacksky Labs",
  "compatible_agents": ["skipper"],
  "entry_point": "index.html",
  "views": ["tasks", "entities"],
  "requires_api_version": "1.0.0",
  "preview_color": "#0A0F1E"
}
```

**Manifest fields — required for all packs:**

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique slug, matches directory name |
| `name` | string | Display name in config picker |
| `version` | string | Semver |
| `description` | string | Short description shown in picker |
| `author` | string | Pack author |
| `compatible_agents` | string[] | `["skipper"]`, `["maurice"]`, `["judy"]`, or `["*"]` |
| `entry_point` | string | HTML file to load, relative to pack root |
| `views` | string[] | Views this pack provides |
| `requires_api_version` | string | Minimum Skipper API version required |
| `preview_color` | string | Hex color for picker thumbnail background |

---

## PART 4 — DASHBOARD PACK v1 UI

### File: `dashboards/skipper-default/index.html`

The dashboard pack is a single self-contained HTML file. It receives the API base URL via a query parameter: `index.html?api=http://localhost:7432`

**Design system:** Blacksky Intelligence visual language
- Background: `#0A0F1E` (void)
- Surface: `#0D1421` (panel)
- Border: `rgba(255,255,255,0.06)` (hairline)
- Cyan accent: `#00D4FF` (tasks, primary actions)
- Violet accent: `#8B5CF6` (entities)
- Amber: `#F59E0B` (escalated/warning states)
- Green: `#10B981` (complete)
- Typography: Space Grotesk (display/UI), JetBrains Mono (IDs, metadata)

**Views:**
1. **Tasks** — filterable by status, grouped by parent/child, inline status update, delete
2. **Entities** — grouped by type (PERSON, ORG, PLACE, CONCEPT, EVENT, OTHER), click to see linked tasks, inline edit surface_form and canonical_form, delete

**Interaction patterns:**
- Tap/click a task → expand to show description, step_type, linked entities, inline edit controls
- Tap/click an entity → expand to show type, source, linked tasks, inline edit controls
- Status badge on tasks is tappable — cycles through pending → active → complete
- Delete requires a single confirmation tap (not a modal — an inline "confirm?" state)
- Empty states are actionable: "No tasks yet — Skipper is waiting for a goal."

**CoWork implementation note:** Build `index.html` as a single file with embedded CSS and JS. No external dependencies except Google Fonts (Space Grotesk, JetBrains Mono via CDN). The file must work when loaded from a `file://` URI via WKWebView as well as from a local HTTP server.

---

## PART 5 — CONFIG SCREEN DASHBOARD PICKER

This mirrors the existing DB picker and LLM picker exactly. CoWork should follow the same component pattern already in use.

**Data flow:**
1. Config screen loads → calls `GET /api/dashboards` → receives array of pack manifests
2. Renders picker list — each item shows `name`, `description`, `compatible_agents`, `version`
3. Active pack is highlighted (read from `config.json → active_dashboard_pack`)
4. User selects a pack → writes `active_dashboard_pack: pack.id` to `config.json`
5. Dashboard shell reloads with new pack's `entry_point`

**Config.json shape (add this key):**
```json
{
  "active_dashboard_pack": "skipper-default"
}
```

**Filter rule:** Only show packs where `compatible_agents` includes `"skipper"` or `"*"`. Maurice and Judy packs must not appear in Skipper's config.

---

## EXPLICIT OUT OF SCOPE — MVP

- Goals view (next milestone, schema placeholder in tasks via `goal_id` is sufficient)
- Activity/audit log view
- Drift indicators
- Pack installation from URL or zip (manual drop into `/dashboards/` directory only for now)
- Pack preview thumbnails beyond `preview_color`
- Multi-user anything
- Prism T2 belief state integration
- Push from dashboard back to Skipper's reasoning loop (read + direct edit only for MVP)

---

## SUCCESS CRITERIA

CoWork build is complete when:

- [ ] Tasks and Entities tables exist in SQLite with the schemas above
- [ ] `skipper_api.py` runs and all six endpoints respond correctly
- [ ] `dashboards/skipper-default/manifest.json` exists and is valid
- [ ] `dashboards/skipper-default/index.html` loads in WKWebView, renders Tasks and Entities views, all CRUD interactions work
- [ ] Config screen Dashboard picker lists available packs and persists selection
- [ ] Swapping to a different pack (even a placeholder second pack) loads the new pack's `index.html`
- [ ] No platform-specific UI code anywhere in the dashboard pack

---

*SKIPPER-DASH-SEED-001 — Blacksky Labs — Architecture seed, not a build artifact*
