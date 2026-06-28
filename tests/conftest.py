"""Shared fixtures for the AgentOS test suite.

These build throwaway registries, manifests, and personas on disk so the
kernel can be exercised end-to-end without touching the real repo files or
any network/LLM/vector backends.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from agentos.context import AgentContext


@pytest.fixture
def make_context():
    """Factory for a minimal valid AgentContext."""

    def _make(**overrides):
        base = dict(
            agent_name="testbot",
            namespace="testns",
            session_id="sess-1",
        )
        base.update(overrides)
        return AgentContext(**base)

    return _make


@pytest.fixture
def cells_registry(tmp_path: Path) -> Path:
    """Write a cells.registry.yaml that references the in-tree fake cells.

    The fake cell modules live in ``tests.fixtures_cells`` and are importable
    regardless of cwd, so the registry can point at them by dotted path.
    """
    content = textwrap.dedent(
        """
        cells:
          echo:
            versions:
              - version: "1.0.0"
                path: "tests.fixtures_cells.echo"
              - version: "1.2.0"
                path: "tests.fixtures_cells.echo"
              - version: "2.0.0"
                path: "tests.fixtures_cells.echo"
          boom:
            versions:
              - version: "1.0.0"
                path: "tests.fixtures_cells.boom"
          noclass:
            versions:
              - version: "1.0.0"
                path: "tests.fixtures_cells.noclass"
        """
    ).strip()
    path = tmp_path / "cells.registry.yaml"
    path.write_text(content)
    return path


@pytest.fixture
def repo_with_manifest(tmp_path: Path) -> Path:
    """Create a tmp repo root with manifests/ and a persona, return the root."""
    (tmp_path / "manifests").mkdir()
    (tmp_path / "personas").mkdir()

    (tmp_path / "personas" / "testbot.yaml").write_text(
        textwrap.dedent(
            """
            display_name: TestBot
            mission: Help the tests pass.
            voice:
              tone: dry
              emojis: never
            """
        ).strip()
    )

    (tmp_path / "manifests" / "testbot.yaml").write_text(
        textwrap.dedent(
            """
            name: testbot
            version: 0.1.0
            namespace: testns
            persona: ./personas/testbot.yaml
            cells:
              - name: echo
                version: "^1.0"
            model:
              provider: ollama
              name: ollama/llama3.1
            """
        ).strip()
    )
    return tmp_path
