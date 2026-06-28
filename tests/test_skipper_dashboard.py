"""Skipper dashboard pack — store + API + swap tests (SKIPPER-DASH-SEED-001).

Covers the build's success criteria:
  - tasks + entities tables exist with the seed's schema
  - the kernel's /api/* endpoints respond and CRUD works
  - /api/dashboards filters by compatible_agents (Maurice's pack is hidden)
  - swapping the active pack persists and /dashboard serves the new pack

The store tests are pure (a tmp sqlite file). The API tests drive the real
FastAPI app via TestClient with AGENTOS_DATA_DIR pointed at a tmp dir, so they
never touch the developer's ./data — but they DO read the real dashboards/ dir
so the compatibility filter is exercised against the shipped packs.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentos import skipper_store

_IMG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64   # enough bytes to be a non-empty "image" file


# ── Store unit tests ───────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    return tmp_path / "memory.db"


def test_schema_creates_both_tables(db):
    skipper_store.ensure_schema(db)
    import sqlite3

    with sqlite3.connect(db) as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"tasks", "entities"} <= names


def test_task_crud_and_complete_stamp(db):
    t = skipper_store.create_task(db, "Write the report", description="for Q3")
    assert t["id"] and t["status"] == "pending" and t["step_type"] == "autonomous"

    assert skipper_store.get_task(db, t["id"])["title"] == "Write the report"
    assert len(skipper_store.list_tasks(db)) == 1

    updated = skipper_store.update_task(db, t["id"], {"status": "complete"})
    assert updated["status"] == "complete"
    assert updated["completed_at"], "completing a task should stamp completed_at"

    assert skipper_store.list_tasks(db, status="complete")
    assert skipper_store.list_tasks(db, status="pending") == []

    assert skipper_store.delete_task(db, t["id"]) is True
    assert skipper_store.get_task(db, t["id"]) is None
    assert skipper_store.delete_task(db, t["id"]) is False


def test_update_ignores_unknown_and_none_fields(db):
    t = skipper_store.create_task(db, "Original")
    # 'id' and 'bogus' are not updatable; title=None is a no-op.
    updated = skipper_store.update_task(db, t["id"], {"id": "hacked", "bogus": 1, "title": None})
    assert updated["id"] == t["id"]
    assert updated["title"] == "Original"


def test_entity_crud_and_linked(db):
    task = skipper_store.create_task(db, "Call the supplier")
    e = skipper_store.create_entity(
        db, "Acme Co", "ORG", source_type="task", source_id=task["id"]
    )
    assert e["entity_type"] == "ORG" and e["confidence"] == 1.0

    linked = skipper_store.entity_linked(db, e["id"])
    assert linked["entity"]["id"] == e["id"]
    assert [t["id"] for t in linked["linked_tasks"]] == [task["id"]]

    upd = skipper_store.update_entity(db, e["id"], {"canonical_form": "Acme Corporation"})
    assert upd["canonical_form"] == "Acme Corporation"

    assert skipper_store.delete_entity(db, e["id"]) is True
    assert skipper_store.entity_linked(db, e["id"]) is None


# ── API integration tests ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("skipper_data")
    saved = {k: os.environ.get(k) for k in ("AGENTOS_DATA_DIR", "AGENTOS_AGENT", "AGENTOS_SESSION_MODE")}
    os.environ["AGENTOS_DATA_DIR"] = str(data_dir)
    os.environ["AGENTOS_AGENT"] = "skipper"
    os.environ["AGENTOS_SESSION_MODE"] = "new"
    from agentos.main import app

    with TestClient(app) as c:
        # start from a known pack so tests are order-independent
        c.patch("/api/dashboard", json={"pack": "skipper-default"})
        yield c

    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _skipper_db():
    """The DB the app is reading (AGENTOS_DATA_DIR is set by the client fixture)."""
    return skipper_store.db_path_for("skipper")


def test_tasks_api_roundtrip(client):
    db = _skipper_db()
    task = skipper_store.create_task(db, "API task", description="seeded by test", status="active")

    listed = client.get("/api/tasks").json()
    assert any(t["id"] == task["id"] for t in listed)

    assert client.get(f"/api/tasks/{task['id']}").json()["title"] == "API task"
    assert client.get("/api/tasks/does-not-exist").status_code == 404

    # PATCH status, then filter by it
    r = client.patch(f"/api/tasks/{task['id']}", json={"status": "complete"})
    assert r.status_code == 200 and r.json()["status"] == "complete"
    assert any(t["id"] == task["id"] for t in client.get("/api/tasks", params={"status": "complete"}).json())

    assert client.delete(f"/api/tasks/{task['id']}").status_code == 200
    assert client.get(f"/api/tasks/{task['id']}").status_code == 404


def test_entities_api_and_linked(client):
    db = _skipper_db()
    task = skipper_store.create_task(db, "Linked task")
    ent = skipper_store.create_entity(db, "Baltimore", "PLACE", source_type="task", source_id=task["id"])

    assert any(e["id"] == ent["id"] for e in client.get("/api/entities").json())
    assert any(e["id"] == ent["id"] for e in client.get("/api/entities", params={"entity_type": "PLACE"}).json())

    linked = client.get(f"/api/entities/{ent['id']}/linked").json()
    assert linked["entity"]["id"] == ent["id"]
    assert [t["id"] for t in linked["linked_tasks"]] == [task["id"]]

    r = client.patch(f"/api/entities/{ent['id']}", json={"canonical_form": "Baltimore, MD"})
    assert r.json()["canonical_form"] == "Baltimore, MD"
    assert client.delete(f"/api/entities/{ent['id']}").status_code == 200


def test_dashboards_filter_hides_incompatible(client):
    packs = client.get("/api/dashboards").json()
    ids = {p["id"] for p in packs}
    assert "skipper-default" in ids
    assert "skipper-mono" in ids
    assert "maurice-crm" not in ids, "Maurice's pack must not appear in Skipper's picker"
    assert sum(1 for p in packs if p.get("_active")) == 1


def test_active_manifest_default(client):
    client.patch("/api/dashboard", json={"pack": "skipper-default"})
    m = client.get("/api/manifest").json()
    assert m["id"] == "skipper-default" and m["_active"] is True


def test_swap_pack_persists_and_serves(client):
    # default serves the Tasks/Entities pack
    client.patch("/api/dashboard", json={"pack": "skipper-default"})
    assert "SKIPPER" in client.get("/dashboard").text

    # swap to the mono pack
    r = client.patch("/api/dashboard", json={"pack": "skipper-mono"})
    assert r.status_code == 200 and r.json()["active_dashboard_pack"] == "skipper-mono"
    assert client.get("/api/manifest").json()["id"] == "skipper-mono"
    assert "skipper@local" in client.get("/dashboard").text  # mono pack's terminal prompt

    # restore default for any later tests
    client.patch("/api/dashboard", json={"pack": "skipper-default"})


def test_swap_rejects_incompatible_and_missing(client):
    assert client.patch("/api/dashboard", json={"pack": "maurice-crm"}).status_code == 400
    assert client.patch("/api/dashboard", json={"pack": "ghost-pack"}).status_code == 404


def test_overview_and_pack_asset_routes(client):
    assert client.get("/overview").status_code == 200          # analytics preserved
    assert client.get("/dashboards/skipper-default/manifest.json").status_code == 200
    assert client.get("/dashboards/skipper-default/nope.css").status_code == 404


# ── Wipe model + load-screen preview ───────────────────────────────────

def test_wipe_model_honors_llama_cache(client, monkeypatch, tmp_path):
    cache = tmp_path / "llama.cpp"
    cache.mkdir()
    (cache / "model.gguf").write_bytes(b"x" * 2048)
    monkeypatch.setenv("LLAMA_CACHE", str(cache))

    body = client.delete("/system/model").json()
    assert body["wiped"] is True and body["freed_bytes"] >= 2048
    assert not cache.exists()

    # nothing left to wipe the second time
    assert client.delete("/system/model").json()["wiped"] is False


def test_wipe_model_refuses_unsafe_path(client, monkeypatch):
    monkeypatch.setenv("LLAMA_CACHE", str(Path.home()))
    assert client.delete("/system/model").status_code == 400


def test_loadscreen_images_and_serving(client, monkeypatch, tmp_path):
    slides = tmp_path / "Slides"
    slides.mkdir()
    (slides / "a.png").write_bytes(_IMG)
    (slides / "b.jpg").write_bytes(_IMG)
    (slides / "notes.txt").write_text("ignore me")
    monkeypatch.setenv("AGENTOS_SLIDES_DIR", str(slides))

    listed = client.get("/loadscreen/images").json()
    assert listed["images"] == ["a.png", "b.jpg"]   # sorted, non-images excluded
    assert listed["count"] == 2

    assert client.get("/loadscreen/img/a.png").status_code == 200
    assert client.get("/loadscreen/img/missing.png").status_code == 404
    assert client.get("/loadscreen/img/notes.txt").status_code == 404      # not an image
    assert client.get("/loadscreen/img/..%2f..%2fsecret").status_code == 404  # traversal guard


def test_loadscreen_page_served(client):
    r = client.get("/loadscreen")
    assert r.status_code == 200 and "SKIPPER" in r.text
