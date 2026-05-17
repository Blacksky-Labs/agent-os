"""Manifest loader and validator.

Reads ``<agent>.yaml`` from ``manifests/``, resolves the persona reference,
validates required fields. Returns a dict the kernel can hand to ``Pipeline``.

See SPEC.md §9 (manifest format) and §8 (persona format).
"""

from __future__ import annotations

from pathlib import Path

import yaml


REQUIRED_FIELDS: tuple[str, ...] = ("name", "version", "namespace")


class ManifestError(ValueError):
    """Raised when a manifest is missing, malformed, or invalid."""


def load_manifest(name: str, repo_root: Path | str = ".") -> dict:
    """Load and validate an agent manifest.

    Args:
        name: agent name (without ``.yaml`` extension)
        repo_root: repo root (where ``manifests/`` lives)

    Returns:
        ``dict`` — the parsed manifest with defaults filled in and the
        resolved persona data attached as ``_persona_data``.

    Raises:
        ManifestError if the file is missing or required fields are absent.
    """
    repo_root = Path(repo_root)
    manifest_path = repo_root / "manifests" / f"{name}.yaml"

    if not manifest_path.exists():
        raise ManifestError(f"Manifest not found: {manifest_path}")

    with manifest_path.open() as f:
        data = yaml.safe_load(f) or {}

    for required in REQUIRED_FIELDS:
        if required not in data:
            raise ManifestError(
                f"Missing required field '{required}' in {manifest_path}"
            )

    # Fill defaults
    data.setdefault("persona", None)
    data.setdefault("cells", [])
    data.setdefault("tools", [])
    data.setdefault("hooks", {})
    data.setdefault("model", {})

    # Resolve persona reference (relative to repo root)
    persona_ref = data.get("persona")
    if persona_ref:
        rel = persona_ref[2:] if persona_ref.startswith("./") else persona_ref
        persona_path = repo_root / rel
        if persona_path.exists():
            with persona_path.open() as f:
                data["_persona_data"] = yaml.safe_load(f) or {}
        else:
            # Persona file missing is non-fatal — agent runs with empty persona.
            data["_persona_data"] = {}
    else:
        data["_persona_data"] = {}

    return data
