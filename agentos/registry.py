"""Cell + Tool registry.

Reads ``cells.registry.yaml`` or ``tools.registry.yaml`` from the repo root
and resolves ``<name, version-constraint>`` to a Python module path.

See SPEC.md §5 (cells) and §6 (tools).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml


RegistryKind = Literal["cells", "tools"]


class Registry:
    """Loads and resolves cells or tools from a registry yaml."""

    def __init__(self, path: Path | str, kind: RegistryKind):
        self.path = Path(path)
        self.kind = kind
        self._entries: dict = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        with self.path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get(self.kind, {}) or {}

    def resolve(self, name: str, version: str = "latest") -> str:
        """Resolve ``<name, version-constraint>`` to a Python module path.

        Version constraint forms supported:
            ``"latest"``  — most recently registered version
            ``"=1.2.3"``  — exact pin
            ``"1.2.3"``   — exact pin
            ``"^1.2"``    — compatible: latest 1.x.y
            ``"~1.2"``    — patch-only: latest 1.2.x
        """
        if name not in self._entries:
            raise ValueError(
                f"{self._kind_singular()} '{name}' not found in {self.path.name}"
            )
        versions = self._entries[name].get("versions", [])
        if not versions:
            raise ValueError(
                f"{self._kind_singular()} '{name}' has no registered versions"
            )
        resolved = self._resolve_version(name, versions, version)
        return resolved["path"]

    def _resolve_version(self, name: str, versions: list[dict], constraint: str) -> dict:
        if constraint == "latest":
            return versions[-1]

        if constraint.startswith("^"):
            major = constraint[1:].split(".")[0]
            matches = [v for v in versions if v["version"].split(".")[0] == major]
        elif constraint.startswith("~"):
            parts = constraint[1:].split(".")
            major_minor = ".".join(parts[:2])
            matches = [v for v in versions if v["version"].startswith(major_minor + ".")]
        else:
            exact = constraint.lstrip("=")
            matches = [v for v in versions if v["version"] == exact]

        if not matches:
            available = [v["version"] for v in versions]
            raise ValueError(
                f"No version of '{name}' satisfies '{constraint}'. "
                f"Available: {available}"
            )
        return matches[-1]

    def list_names(self) -> list[str]:
        return list(self._entries.keys())

    def _kind_singular(self) -> str:
        return self.kind[:-1] if self.kind.endswith("s") else self.kind
