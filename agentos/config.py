"""Manifest loader and validator.

Reads ``<agent>.yaml`` from ``manifests/``, resolves the persona reference,
validates required fields. Returns a dict the kernel can hand to ``Pipeline``.

See SPEC.md §9 (manifest format) and §8 (persona format).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from agentos.paths import namespace_dir


REQUIRED_FIELDS: tuple[str, ...] = ("name", "version", "namespace")

# The cells that occupy the generation slot. The reasoning-mode overlay swaps
# one for the other (single-model llm-interface <-> mixture-of-experts moe).
_REASONING_CELLS: frozenset[str] = frozenset({"llm-interface", "moe"})


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

    with manifest_path.open(encoding="utf-8") as f:
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
    data.setdefault("owner", None)          # the single owner/operator
    data.setdefault("multi_user", False)    # True only for agents serving external users

    # Resolve persona reference (relative to repo root)
    persona_ref = data.get("persona")
    if persona_ref:
        rel = persona_ref[2:] if persona_ref.startswith("./") else persona_ref
        persona_path = repo_root / rel
        if persona_path.exists():
            with persona_path.open(encoding="utf-8") as f:
                data["_persona_data"] = yaml.safe_load(f) or {}
        else:
            # Persona file missing is non-fatal — agent runs with empty persona.
            data["_persona_data"] = {}
    else:
        data["_persona_data"] = {}

    # Apply live config overrides (set from the dashboard), if any. These live
    # in a separate overlay file so the manifest stays the pristine source.
    overrides = load_overrides(data["namespace"], repo_root) or {}
    model_override = overrides.get("model")
    if model_override:
        merged = dict(data.get("model") or {})
        merged.update({k: v for k, v in model_override.items() if v is not None})
        data["model"] = merged
        data["_overridden"] = True
    # Reasoning toggles — cells/hooks the operator turned off live. The execution
    # path filters these out; the display path shows them as off.
    data["_disabled_cells"] = list(overrides.get("disabled_cells") or [])
    data["_disabled_hooks"] = list(overrides.get("disabled_hooks") or [])
    # Per-cell config overrides (e.g. memory.max_history, context-builder.surface_threads).
    cell_config_override = overrides.get("cell_config") or {}
    if cell_config_override:
        for cell in data.get("cells") or []:
            patch = cell_config_override.get(cell.get("name"))
            if patch:
                merged = dict(cell.get("config") or {})
                merged.update({k: v for k, v in patch.items() if v is not None})
                cell["config"] = merged

    # Reasoning mode — swap the generation slot (llm-interface <-> moe). The
    # manifest sets the baseline (default single-model); the overlay overrides it
    # live from the config dashboard. The overlay's `moe` block carries the roster.
    reasoning_mode = overrides.get("reasoning_mode") or data.get("reasoning_mode")
    cells = data.get("cells") or []
    idx = next((i for i, c in enumerate(cells) if c.get("name") in _REASONING_CELLS), None)
    if reasoning_mode in ("single", "moe") and idx is not None:
        if reasoning_mode == "moe":
            moe_cfg = overrides.get("moe")
            if moe_cfg is None and cells[idx].get("name") == "moe":
                moe_cfg = cells[idx].get("config")  # keep the manifest's roster
            cells[idx] = {"name": "moe", "version": "^1.0", "config": moe_cfg or {}}
        else:  # single
            cells[idx] = {"name": "llm-interface", "version": "^1.0"}
    # Effective mode (for the config page to display), derived from the final slot.
    rc = next((c.get("name") for c in cells if c.get("name") in _REASONING_CELLS), None)
    data["_reasoning_mode"] = "moe" if rc == "moe" else "single"

    return data


# ----------------------------------------------------------------------
# Live config overrides — set from the dashboard, merged over the manifest.
# Stored at data/<namespace>/config.overrides.yaml so the manifest is never
# mutated (comments and structure preserved). Survives a history wipe.
# ----------------------------------------------------------------------

def _overrides_path(namespace: str, repo_root: Path | str = ".") -> Path:
    return namespace_dir(namespace, repo_root) / "config.overrides.yaml"


def load_overrides(namespace: str, repo_root: Path | str = ".") -> dict:
    path = _overrides_path(namespace, repo_root)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_model_override(namespace: str, repo_root: Path | str, model_patch: dict) -> dict:
    """Merge a model patch into the overlay. None values are ignored."""
    path = _overrides_path(namespace, repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_overrides(namespace, repo_root)
    model = dict(data.get("model") or {})
    model.update({k: v for k, v in model_patch.items() if v is not None})
    data["model"] = model
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    return data


def save_toggles(
    namespace: str,
    repo_root: Path | str,
    disabled_cells: list[str],
    disabled_hooks: list[str],
) -> dict:
    """Persist which cells/hooks are turned off (the operator sends the full set)."""
    path = _overrides_path(namespace, repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_overrides(namespace, repo_root)
    data["disabled_cells"] = list(disabled_cells or [])
    data["disabled_hooks"] = list(disabled_hooks or [])
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    return data


def save_cell_config(
    namespace: str, repo_root: Path | str, cell_name: str, patch: dict
) -> dict:
    """Persist a per-cell config patch into the overlay (merged at load time)."""
    path = _overrides_path(namespace, repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_overrides(namespace, repo_root)
    cell_config = dict(data.get("cell_config") or {})
    existing = dict(cell_config.get(cell_name) or {})
    existing.update({k: v for k, v in patch.items() if v is not None})
    cell_config[cell_name] = existing
    data["cell_config"] = cell_config
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    return data


def save_reasoning_mode(
    namespace: str,
    repo_root: Path | str,
    mode: str | None = None,
    moe_config: dict | None = None,
) -> dict:
    """Persist the reasoning mode (``single`` | ``moe``) and/or the MoE roster.

    ``moe_config`` is ``{router_model, default, experts: [...]}`` — this is what the
    config dashboard edits when adding/removing expert mini-models. Saving a roster
    implies MoE mode unless ``mode`` says otherwise.
    """
    path = _overrides_path(namespace, repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_overrides(namespace, repo_root)
    if moe_config is not None:
        data["moe"] = moe_config
        data.setdefault("reasoning_mode", "moe")
    if mode in ("single", "moe"):
        data["reasoning_mode"] = mode
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    return data


def active_dashboard_pack(
    namespace: str, repo_root: Path | str = ".", default: str = "skipper-default"
) -> str:
    """The dashboard pack the operator selected, or ``default`` if unset.

    Mirrors the model/reasoning swap: the choice lives in the per-namespace
    overlay (``active_dashboard_pack``), not a global config file, so each entity
    keeps its own dashboard and a history wipe doesn't reset the UI.
    """
    return load_overrides(namespace, repo_root).get("active_dashboard_pack") or default


def save_dashboard_pack(namespace: str, repo_root: Path | str, pack_id: str) -> dict:
    """Persist the selected dashboard pack id into the overlay."""
    path = _overrides_path(namespace, repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_overrides(namespace, repo_root)
    data["active_dashboard_pack"] = pack_id
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    return data


def clear_overrides(namespace: str, repo_root: Path | str = ".") -> bool:
    """Remove the overlay entirely (reset to manifest defaults)."""
    path = _overrides_path(namespace, repo_root)
    if path.exists():
        path.unlink()
        return True
    return False
