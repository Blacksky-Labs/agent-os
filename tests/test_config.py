"""Manifest loader/validator tests (SPEC §8/§9)."""

from __future__ import annotations

import pytest

from agentos.config import ManifestError, load_manifest


def test_load_valid_manifest(repo_with_manifest):
    m = load_manifest("testbot", repo_root=repo_with_manifest)
    assert m["name"] == "testbot"
    assert m["namespace"] == "testns"
    assert m["version"] == "0.1.0"


def test_defaults_filled(repo_with_manifest):
    m = load_manifest("testbot", repo_root=repo_with_manifest)
    # tools/hooks default even though the manifest omits them
    assert m["tools"] == []
    assert m["hooks"] == {}
    assert isinstance(m["model"], dict)


def test_persona_resolved(repo_with_manifest):
    m = load_manifest("testbot", repo_root=repo_with_manifest)
    assert m["_persona_data"]["display_name"] == "TestBot"
    assert m["_persona_data"]["mission"] == "Help the tests pass."


def test_missing_manifest_raises(repo_with_manifest):
    with pytest.raises(ManifestError, match="not found"):
        load_manifest("ghost", repo_root=repo_with_manifest)


def test_missing_required_field_raises(tmp_path):
    (tmp_path / "manifests").mkdir()
    (tmp_path / "manifests" / "bad.yaml").write_text("name: bad\nversion: 0.1.0\n")
    with pytest.raises(ManifestError, match="namespace"):
        load_manifest("bad", repo_root=tmp_path)


def test_missing_persona_file_is_non_fatal(tmp_path):
    (tmp_path / "manifests").mkdir()
    (tmp_path / "manifests" / "x.yaml").write_text(
        "name: x\nversion: 0.1.0\nnamespace: xns\npersona: ./personas/missing.yaml\n"
    )
    m = load_manifest("x", repo_root=tmp_path)
    assert m["_persona_data"] == {}


def test_no_persona_reference_yields_empty(tmp_path):
    (tmp_path / "manifests").mkdir()
    (tmp_path / "manifests" / "x.yaml").write_text(
        "name: x\nversion: 0.1.0\nnamespace: xns\n"
    )
    m = load_manifest("x", repo_root=tmp_path)
    assert m["_persona_data"] == {}
