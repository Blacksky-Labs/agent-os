"""Registry version-resolution tests (SPEC §5/§6)."""

from __future__ import annotations

import pytest

from agentos.registry import Registry


@pytest.fixture
def reg(cells_registry):
    return Registry(cells_registry, "cells")


def test_resolve_latest_returns_last_registered(reg):
    # echo has 1.0.0, 1.2.0, 2.0.0 — latest is the last in the list
    assert reg.resolve("echo", "latest") == "tests.fixtures_cells.echo"


def test_resolve_exact(reg):
    assert reg.resolve("echo", "1.2.0") == "tests.fixtures_cells.echo"


def test_resolve_exact_with_equals_prefix(reg):
    assert reg.resolve("echo", "=2.0.0") == "tests.fixtures_cells.echo"


def test_caret_picks_latest_within_major(reg):
    # ^1.0 should match 1.x only (1.0.0, 1.2.0), newest = 1.2.0, not 2.0.0
    assert reg.resolve("echo", "^1.0") == "tests.fixtures_cells.echo"


def test_tilde_picks_latest_within_minor(reg):
    assert reg.resolve("echo", "~1.0") == "tests.fixtures_cells.echo"


def test_unknown_name_raises(reg):
    with pytest.raises(ValueError, match="not found"):
        reg.resolve("nonexistent")


def test_unsatisfiable_constraint_raises_with_available(reg):
    with pytest.raises(ValueError, match="satisfies"):
        reg.resolve("echo", "^9.0")


def test_list_names(reg):
    names = reg.list_names()
    assert "echo" in names
    assert "boom" in names


def test_missing_registry_file_is_empty(tmp_path):
    r = Registry(tmp_path / "does-not-exist.yaml", "cells")
    assert r.list_names() == []


def test_caret_unsatisfiable_lists_available_versions(reg):
    with pytest.raises(ValueError) as exc:
        reg.resolve("echo", "^5.0")
    assert "1.0.0" in str(exc.value)
