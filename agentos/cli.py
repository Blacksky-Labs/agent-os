"""AgentOS CLI — ``agentos`` command.

Subcommands:
    version            Print agentOS version
    list               List registered cells, tools, and scaffolded agents
    new agent [NAME]   Interactive scaffolder for a new agent
    run AGENT          Boot FastAPI with an agent's manifest loaded

See SPEC.md and future-needs.md for what's deferred (doctor, pull, etc.).
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel

from agentos.config import ManifestError, load_manifest
from agentos.registry import Registry


app = typer.Typer(
    help="AgentOS — agent fleet operating system.",
    add_completion=False,
)
new_app = typer.Typer(
    help="Scaffold new things (agent, cell, tool).",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(new_app, name="new")

delete_app = typer.Typer(
    help="Delete scaffolded things (agent, cell, tool).",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(delete_app, name="delete")

console = Console()


# ============================================================
# Command index — hand-curated flat list for `agentos commands`
# ============================================================
# Append new commands here as they ship. Coming-soon items show users
# what's on the roadmap inside the CLI itself.

COMMAND_INDEX_AVAILABLE: list[tuple[str, str]] = [
    ("version",              "Print agentOS version"),
    ("commands",             "Show this command index"),
    ("list",                 "List registered cells, tools, and scaffolded agents"),
    ("start AGENT",          "Boot FastAPI with an agent loaded"),
    ("stop AGENT",           "Stop a running agent (v0.1: Ctrl+C reminder)"),
    ("destroy AGENT",        "Wipe an agent's runtime data, keep config"),
    ("rebuild AGENT",        "destroy + start"),
    ("run AGENT",            "Alias of `start` (kept for back-compat)"),
    ("new agent [NAME]",     "Interactive scaffolder for a new agent"),
    ("delete agent [NAME]",  "Delete a scaffolded agent (manifest + persona)"),
]

COMMAND_INDEX_COMING: list[tuple[str, str]] = [
    ("new cell [NAME]",      "Scaffold a new cell"),
    ("new tool [NAME]",      "Scaffold a new tool"),
    ("delete cell [NAME]",   "Delete a scaffolded cell"),
    ("delete tool [NAME]",   "Delete a scaffolded tool"),
    ("doctor [AGENT]",       "Validate manifest, Ollama daemon, env keys"),
    ("pull MODEL",           "Pull an Ollama model"),
]


def _print_command_index() -> None:
    """Render the flat command tree."""
    from agentos import __version__
    console.print()
    console.print(f"[bold]agentos[/]  [dim]v{__version__}[/]  — agent fleet operating system")
    console.print()
    console.print("[bold cyan]Available commands[/]")
    width = max(len(c) for c, _ in COMMAND_INDEX_AVAILABLE + COMMAND_INDEX_COMING) + 2
    for cmd, desc in COMMAND_INDEX_AVAILABLE:
        console.print(f"  [bold]{cmd:<{width}}[/] {desc}")
    console.print()
    console.print("[bold cyan]Coming next[/]")
    for cmd, desc in COMMAND_INDEX_COMING:
        console.print(f"  [dim]{cmd:<{width}}[/] [dim]{desc}[/]")
    console.print()
    console.print(
        "[dim]Use `agentos <command> --help` to see flags for any command.[/]"
    )
    console.print()


# ============================================================
# Helpers
# ============================================================

def _find_repo_root() -> Path:
    """Walk up from cwd until cells.registry.yaml is found."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "cells.registry.yaml").exists():
            return parent
    console.print(
        "[red]Could not find cells.registry.yaml. "
        "Run agentos from the repo root.[/]"
    )
    raise typer.Exit(1)


def _choose_one(prompt: str, choices: list[str], default_idx: int = 0) -> str:
    """Render a numbered list and return the chosen item."""
    console.print(f"\n[bold cyan]◆ {prompt}[/]")
    for i, choice in enumerate(choices, start=1):
        marker = "●" if i - 1 == default_idx else "○"
        console.print(f"  {marker} [bold]{i})[/] {choice}")
    while True:
        raw = typer.prompt("  Select", default=str(default_idx + 1))
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        console.print(f"  [red]Pick 1–{len(choices)}[/]")


def _choose_many(
    prompt: str,
    choices: list[str],
    default_set: set[str],
) -> list[str]:
    """Numbered list; user types comma-separated indices, 'all', or 'none'."""
    console.print(f"\n[bold cyan]◆ {prompt}[/]")
    for i, choice in enumerate(choices, start=1):
        marker = "[×]" if choice in default_set else "[ ]"
        console.print(f"  {marker} [bold]{i})[/] {choice}")
    default_raw = ",".join(
        str(i + 1) for i, c in enumerate(choices) if c in default_set
    )
    raw = typer.prompt(
        "  Select (comma-separated, or 'all', or 'none')",
        default=default_raw or "none",
    )
    norm = raw.strip().lower()
    if norm == "all":
        return list(choices)
    if norm == "none":
        return []
    picked: list[str] = []
    for token in raw.split(","):
        try:
            idx = int(token.strip()) - 1
            if 0 <= idx < len(choices) and choices[idx] not in picked:
                picked.append(choices[idx])
        except ValueError:
            continue
    return picked


def _list_ollama_models(url: str = "http://localhost:11434") -> list[dict] | None:
    """Call Ollama's /api/tags. Returns None if the daemon is unreachable."""
    try:
        req = urllib.request.Request(f"{url}/api/tags")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read())
            return data.get("models", []) or []
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, ConnectionError):
        return None


def _format_size(bytes_: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if bytes_ < 1024:
            return f"{bytes_:.1f} {unit}"
        bytes_ /= 1024
    return f"{bytes_:.1f} PB"


# ============================================================
# Commands
# ============================================================

@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context):
    """AgentOS — agent fleet operating system."""
    if ctx.invoked_subcommand is None:
        _print_command_index()
        raise typer.Exit(0)


@app.command()
def commands():
    """Show the full list of commands (available + coming next)."""
    _print_command_index()


@app.command()
def version():
    """Print agentOS version."""
    from agentos import __version__
    console.print(f"[bold]agentos[/] {__version__}")


@app.command(name="list")
def list_things():
    """List registered cells, tools, and scaffolded agents."""
    repo_root = _find_repo_root()
    cell_reg = Registry(repo_root / "cells.registry.yaml", kind="cells")
    tool_reg = Registry(repo_root / "tools.registry.yaml", kind="tools")

    console.print("\n[bold cyan]Cells[/]")
    for name in cell_reg.list_names():
        console.print(f"  • {name}")

    console.print("\n[bold cyan]Tools[/]")
    tools = tool_reg.list_names()
    if not tools:
        console.print("  [dim](none registered)[/]")
    for name in tools:
        console.print(f"  • {name}")

    console.print("\n[bold cyan]Agents[/]")
    manifests_dir = repo_root / "manifests"
    found = sorted(manifests_dir.glob("*.yaml")) if manifests_dir.exists() else []
    if not found:
        console.print(
            "  [dim](no agents scaffolded — try `agentos new agent`)[/]"
        )
    for m in found:
        console.print(f"  • {m.stem}")


@app.command()
def start(
    agent_name: str = typer.Argument(..., help="Agent name to load"),
    host: str = typer.Option(
        os.getenv("AGENTOS_HOST", "127.0.0.1"), help="Bind host"
    ),
    port: int = typer.Option(
        int(os.getenv("AGENTOS_PORT", "7777")), help="Bind port"
    ),
    reload: bool = typer.Option(
        False, "--reload", help="Auto-reload on code changes (dev only)"
    ),
):
    """Boot FastAPI with an agent's manifest loaded (Lando-style)."""
    repo_root = _find_repo_root()
    os.chdir(repo_root)

    try:
        manifest = load_manifest(agent_name, repo_root=repo_root)
    except ManifestError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    model = manifest.get("model", {}) or {}
    console.print(
        Panel.fit(
            f"[bold]Booting {manifest['name']} v{manifest['version']}[/]\n"
            f"  namespace: {manifest['namespace']}\n"
            f"  cells:     {len(manifest.get('cells', []) or [])}\n"
            f"  tools:     {len(manifest.get('tools', []) or [])}\n"
            f"  provider:  {model.get('provider', '-')}\n"
            f"  model:     {model.get('name', '-')}\n\n"
            f"  POST http://{host}:{port}/chat",
            title="agentOS",
            border_style="cyan",
        )
    )

    import uvicorn
    uvicorn.run("agentos.main:app", host=host, port=port, reload=reload)


# ============================================================
# Lifecycle verbs — stop, destroy, rebuild
# (Lando-style. See SPEC.md for the parts-of-an-agent model.)
# ============================================================

@app.command()
def stop(
    agent_name: str = typer.Argument(..., help="Agent name to stop"),
):
    """Stop a running agent.

    v0.1 placeholder: ``agentos start`` runs foreground in this version,
    so 'stopping' is Ctrl+C in the terminal where it's running. Real
    daemon-mode stop is in future-needs.md.
    """
    console.print(
        Panel.fit(
            f"[bold]Stop {agent_name}[/]\n\n"
            f"[dim]`agentos start` is foreground in v0.1 — there's no\n"
            f"daemon to signal. Hit Ctrl+C in the terminal where\n"
            f"`agentos start {agent_name}` is running.[/]\n\n"
            f"[dim]Real daemon mode + a working `stop` are on the\n"
            f"roadmap — see future-needs.md.[/]",
            border_style="yellow",
        )
    )


@app.command()
def destroy(
    agent_name: str = typer.Argument(
        ..., help="Agent name to wipe runtime data for"
    ),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Skip the confirmation prompt"
    ),
):
    """Wipe an agent's runtime data; keep the config.

    Removes per-namespace data the agent has produced (memory, retrieval
    indexes, sessions, telemetry) but preserves the manifest + persona
    so you can rebuild the same agent fresh. The opposite end of
    ``delete agent``, which wipes config too.

    v0.1 note: stub cells write no persistent data, so this is mostly a
    placeholder. When ``memory`` and ``retrieval`` cells start writing
    real state to ``data/<namespace>/`` and namespaced Chroma collections,
    this command cleans those up with no API change.
    """
    repo_root = _find_repo_root()

    try:
        manifest = load_manifest(agent_name, repo_root=repo_root)
    except ManifestError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    namespace = manifest["namespace"]

    # Candidate runtime-data paths agentOS owns for an agent.
    # As cells start writing real state, add their paths here.
    candidates = [
        repo_root / "data" / namespace,
        repo_root / "chroma_db" / namespace,
    ]
    existing = [p for p in candidates if p.exists()]

    console.print()
    console.print(f"[bold]Destroy runtime data for {agent_name}[/]")
    console.print(f"  namespace: [cyan]{namespace}[/]")
    console.print()

    if existing:
        console.print("[bold]Would remove:[/]")
        for p in existing:
            console.print(f"  • {p.relative_to(repo_root)}")
    else:
        console.print(
            "[dim]No runtime data found yet "
            "(v0.1 stub cells don't write).[/]"
        )

    console.print()
    console.print(
        f"[dim]Preserved: manifests/{agent_name}.yaml, "
        f"personas/{agent_name}.yaml, .env keys, LLM model files.[/]"
    )
    console.print(
        f"[dim]If `agentos start {agent_name}` is currently running, "
        f"stop it first.[/]"
    )

    if not existing:
        console.print()
        console.print("[yellow]Nothing to destroy.[/]")
        return

    if not yes:
        console.print()
        if not typer.confirm("Proceed?", default=False):
            console.print("[yellow]Cancelled.[/]")
            raise typer.Exit(0)

    for p in existing:
        shutil.rmtree(p)
        console.print(f"[green]✓ Removed {p.relative_to(repo_root)}[/]")


@app.command()
def rebuild(
    agent_name: str = typer.Argument(..., help="Agent name to rebuild"),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Skip the confirmation prompt"
    ),
    host: str = typer.Option(
        os.getenv("AGENTOS_HOST", "127.0.0.1"), help="Bind host"
    ),
    port: int = typer.Option(
        int(os.getenv("AGENTOS_PORT", "7777")), help="Bind port"
    ),
    reload: bool = typer.Option(
        False, "--reload", help="Auto-reload on code changes (dev only)"
    ),
):
    """Rebuild an agent: destroy runtime data, then start.

    Equivalent to ``agentos destroy <name>`` followed by
    ``agentos start <name>`` (matches Lando's ``lando rebuild``). The
    agent's manifest + persona are preserved; only runtime data is wiped.
    """
    if not yes:
        console.print(
            f"\n[bold]Rebuild {agent_name}[/]: "
            f"wipe runtime data, then start.\n"
            f"[dim](Use -y to skip this confirmation.)[/]"
        )
        if not typer.confirm("Proceed?", default=False):
            console.print("[yellow]Cancelled.[/]")
            raise typer.Exit(0)

    # Run destroy unattended; if the manifest is missing or anything
    # else fails inside destroy, it raises typer.Exit and we propagate.
    destroy(agent_name=agent_name, yes=True)

    # Foreground-block on start (matches Lando rebuild behavior).
    start(agent_name=agent_name, host=host, port=port, reload=reload)


# ============================================================
# `new agent` — the interactive Lando-style flow
# ============================================================

@new_app.command("agent")
def new_agent(
    name: Optional[str] = typer.Argument(
        None, help="Agent name (prompted if omitted)"
    ),
):
    """Interactive scaffolder for a new agent."""
    repo_root = _find_repo_root()
    console.print(
        Panel.fit(
            "[bold]Scaffold a new agent[/]\n"
            "[dim]Each prompt has a default in brackets — "
            "hit enter to accept.[/]",
            border_style="cyan",
        )
    )

    # --- Identity ---
    if not name:
        name = typer.prompt("\n◆ Agent name (lowercase, no spaces)").strip().lower()
    name = name.lower().replace(" ", "-")

    manifest_path = repo_root / "manifests" / f"{name}.yaml"
    persona_path = repo_root / "personas" / f"{name}.yaml"
    if manifest_path.exists():
        console.print(
            f"[red]manifests/{name}.yaml already exists. "
            f"Pick another name.[/]"
        )
        raise typer.Exit(1)

    display_name = typer.prompt("\n◆ Display name", default=name.capitalize())
    namespace = typer.prompt("\n◆ Namespace", default=name)
    mission = typer.prompt(
        "\n◆ Mission (one paragraph)", default="(fill in later)"
    )

    # --- Persona starter ---
    persona_starter = _choose_one(
        "Persona starter",
        ["Blank", "Sales agent", "Research agent", "Customer support", "Code assistant"],
        default_idx=0,
    )

    # --- LLM provider + model ---
    provider_label = _choose_one(
        "LLM provider",
        ["Ollama (local)", "Together AI"],
        default_idx=0,
    )

    api_base: str | None = None

    if provider_label.startswith("Ollama"):
        model_provider = "ollama"
        ollama_url = "http://localhost:11434"
        local_models = _list_ollama_models(ollama_url)

        if local_models:
            console.print(
                f"\n[green]✓ Ollama daemon reachable at {ollama_url} — "
                f"{len(local_models)} model(s) pulled.[/]"
            )
            choices: list[str] = []
            for m in local_models:
                size = _format_size(float(m.get("size", 0)))
                choices.append(f"{m['name']}  ({size})")
            choices.append("(custom — paste a model string)")
            picked = _choose_one("Model", choices, default_idx=0)
            if picked.startswith("(custom"):
                model_name = typer.prompt("\n◆ Custom Ollama model string")
            else:
                model_name = picked.split("  ", 1)[0]
        else:
            if local_models is None:
                console.print(
                    f"\n[yellow]⚠ Ollama daemon not reachable at "
                    f"{ollama_url}.[/]\n"
                    "  Start it with `ollama serve` and re-run, OR pick from\n"
                    "  the preset list (you'll need to pull these yourself)."
                )
            else:
                console.print(
                    f"\n[yellow]⚠ No models pulled on Ollama yet.[/]\n"
                    f"  Run `ollama pull <model>` before `agentos run {name}`."
                )
            presets = [
                "llama3.1:8b",
                "llama3.1:70b",
                "qwen2.5:7b",
                "qwen2.5:72b",
                "mistral:7b",
                "(custom)",
            ]
            picked = _choose_one("Model", presets, default_idx=0)
            if picked == "(custom)":
                model_name = typer.prompt("\n◆ Custom Ollama model string")
            else:
                model_name = picked
        litellm_model = f"ollama/{model_name}"
        api_base = ollama_url

    else:
        # Together AI
        model_provider = "together_ai"
        presets = [
            "meta-llama/Llama-3.1-8B-Instruct-Turbo",
            "meta-llama/Llama-3.1-70B-Instruct-Turbo",
            "Qwen/Qwen2.5-7B-Instruct-Turbo",
            "Qwen/Qwen2.5-72B-Instruct-Turbo",
            "mistralai/Mistral-7B-Instruct-v0.3",
            "(custom)",
        ]
        picked = _choose_one("Model", presets, default_idx=0)
        if picked == "(custom)":
            model_name = typer.prompt("\n◆ Custom Together AI model string")
        else:
            model_name = picked
        litellm_model = f"together_ai/{model_name}"

    env_keys_needed = _env_keys_for_provider(model_provider)

    # --- Sampling defaults ---
    temperature = float(typer.prompt("\n◆ Default temperature", default="0.5"))
    max_tokens = int(typer.prompt("\n◆ Default max_tokens", default="1024"))

    # --- Modes ---
    mode_choices = ["web", "api", "phone", "embedded"]
    modes_selected = _choose_many(
        "Modes this agent serves",
        mode_choices,
        default_set={"web", "api"},
    )

    # --- Cells ---
    cell_choices = [
        "mode-control", "memory", "ingestion",
        "retrieval", "context-builder", "llm-interface",
    ]
    cells_selected = _choose_many(
        "Cells (default: all six)",
        cell_choices,
        default_set=set(cell_choices),
    )

    # --- Tools + hooks (deferred for MVP) ---
    console.print(
        "\n[dim]◆ Tools: register later with `agentos new tool`.[/]"
    )
    console.print(
        "[dim]◆ Hooks: subscribe later by editing the manifest.[/]"
    )

    # --- Write persona.yaml ---
    persona_data = _build_persona(
        name=name,
        display_name=display_name,
        mission=mission,
        starter=persona_starter,
        modes=modes_selected,
    )
    persona_path.parent.mkdir(parents=True, exist_ok=True)
    with persona_path.open("w") as f:
        yaml.safe_dump(persona_data, f, sort_keys=False, default_flow_style=False)

    # --- Write manifest.yaml ---
    manifest_data = _build_manifest(
        name=name,
        namespace=namespace,
        persona_ref=f"./personas/{name}.yaml",
        cells=cells_selected,
        provider=model_provider,
        litellm_model=litellm_model,
        temperature=temperature,
        max_tokens=max_tokens,
        api_base=api_base,
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w") as f:
        yaml.safe_dump(manifest_data, f, sort_keys=False, default_flow_style=False)

    # --- Update .env with any keys needed ---
    if env_keys_needed:
        env_path = repo_root / ".env"
        existing = env_path.read_text() if env_path.exists() else ""
        added: list[str] = []
        for key in env_keys_needed:
            if key not in existing:
                with env_path.open("a") as f:
                    if existing and not existing.endswith("\n"):
                        f.write("\n")
                    f.write(f"{key}=\n")
                    existing += f"{key}=\n"
                added.append(key)
        if added:
            console.print(
                f"\n[green]✓ Added to .env:[/] {', '.join(added)}"
            )
            console.print(
                "  [dim]Fill in the value(s) before running.[/]"
            )

    # --- Summary ---
    console.print(
        Panel.fit(
            f"[bold green]✓ Scaffolded[/]\n\n"
            f"  manifests/{name}.yaml\n"
            f"  personas/{name}.yaml\n\n"
            f"[bold]Next:[/]\n"
            f"  agentos start {name}\n\n"
            f"  curl -X POST http://127.0.0.1:7777/chat \\\n"
            f"    -H 'Content-Type: application/json' \\\n"
            f"    -d '{{\"agent_name\":\"{name}\","
            f"\"user_message\":\"ping\","
            f"\"session_id\":\"test-1\"}}'",
            border_style="green",
        )
    )


# ============================================================
# `delete agent` — symmetric counterpart to `new agent`
# ============================================================

@delete_app.command("agent")
def delete_agent(
    name: Optional[str] = typer.Argument(
        None, help="Agent name (prompted if omitted)"
    ),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Skip the confirmation prompt"
    ),
    force: bool = typer.Option(
        False, "--force", help="Don't error if files are already missing"
    ),
):
    """Delete a scaffolded agent's manifest and persona.

    Does NOT touch .env keys (might be shared with other agents) and does
    NOT remove any LLM model files (Ollama owns model storage). Will print
    which .env keys the manifest referenced so you can clean up manually.
    """
    repo_root = _find_repo_root()

    # If no name, list what's scaffolded and prompt
    if not name:
        manifests_dir = repo_root / "manifests"
        found = (
            sorted(m.stem for m in manifests_dir.glob("*.yaml"))
            if manifests_dir.exists() else []
        )
        if not found:
            console.print(
                "[yellow]No agents scaffolded — nothing to delete.[/]"
            )
            raise typer.Exit(0)
        name = _choose_one("Which agent?", found, default_idx=0)

    name = name.lower().replace(" ", "-")
    manifest_path = repo_root / "manifests" / f"{name}.yaml"
    persona_path = repo_root / "personas" / f"{name}.yaml"

    files_to_delete: list[Path] = []
    if manifest_path.exists():
        files_to_delete.append(manifest_path)
    elif not force:
        console.print(f"[red]Manifest not found: {manifest_path}[/]")
        console.print("[dim]Use --force to skip this check.[/]")
        raise typer.Exit(1)

    if persona_path.exists():
        files_to_delete.append(persona_path)

    # Figure out which .env keys the manifest referenced
    env_keys_referenced: list[str] = []
    if manifest_path.exists():
        try:
            with manifest_path.open() as f:
                manifest_data = yaml.safe_load(f) or {}
            provider = (manifest_data.get("model", {}) or {}).get("provider", "")
            env_keys_referenced = _env_keys_for_provider(provider)
        except Exception:
            pass

    # Show the plan
    console.print()
    console.print("[bold]About to delete:[/]")
    if files_to_delete:
        for f in files_to_delete:
            console.print(f"  • {f.relative_to(repo_root)}")
    else:
        console.print("  [dim](nothing — files already missing)[/]")

    if env_keys_referenced:
        console.print()
        console.print(
            f"[dim]This .env key was referenced by {name} but will NOT be removed[/]"
        )
        console.print("[dim](other agents may share it):[/]")
        for k in env_keys_referenced:
            console.print(f"  • {k}")

    console.print()
    console.print(
        f"[dim]Note: model files (Ollama, etc.) are not touched — agentOS doesn't own them.[/]"
    )
    console.print(
        f"[dim]If `agentos run {name}` is currently running, stop it before deleting.[/]"
    )

    if not files_to_delete:
        console.print("\n[yellow]Nothing to delete.[/]")
        raise typer.Exit(0)

    # Confirm
    if not yes:
        console.print()
        if not typer.confirm("Proceed?", default=False):
            console.print("[yellow]Cancelled.[/]")
            raise typer.Exit(0)

    # Delete
    for f in files_to_delete:
        f.unlink()
        console.print(f"[green]✓ Deleted {f.relative_to(repo_root)}[/]")


# ============================================================
# Provider knowledge (single source of truth)
# ============================================================

def _env_keys_for_provider(provider: str) -> list[str]:
    """Return .env keys this provider's models depend on.

    Used by `new agent` to know what to add to .env, and by `delete agent`
    to know what was referenced. New providers get added here.
    """
    return {
        "ollama": [],
        "together_ai": ["TOGETHER_API_KEY"],
    }.get(provider, [])


# ============================================================
# Builders
# ============================================================

def _build_persona(
    *,
    name: str,
    display_name: str,
    mission: str,
    starter: str,
    modes: list[str],
) -> dict:
    base_voice = {
        "Sales agent":      {"tone": "warm-professional",  "formality": "casual",  "emojis": "never"},
        "Research agent":   {"tone": "neutral-precise",    "formality": "formal",  "emojis": "never"},
        "Customer support": {"tone": "empathetic-helpful", "formality": "casual",  "emojis": "sparing"},
        "Code assistant":   {"tone": "concise-technical",  "formality": "casual",  "emojis": "never"},
        "Blank":            {"tone": "neutral",            "formality": "neutral", "emojis": "never"},
    }.get(starter, {"tone": "neutral", "formality": "neutral", "emojis": "never"})

    mode_defaults = {
        "web":      {"max_words": 250, "markdown": True},
        "api":      {"max_words": 500, "markdown": False},
        "phone":    {"max_words": 60,  "markdown": False, "no_lists": True},
        "embedded": {"max_words": 150, "markdown": False},
    }
    modes_block = {m: mode_defaults[m] for m in modes if m in mode_defaults}

    return {
        "name": name,
        "display_name": display_name,
        "mission": mission,
        "voice": base_voice,
        "modes": modes_block,
        "refusals": [],
        "escalations": [],
    }


def _build_manifest(
    *,
    name: str,
    namespace: str,
    persona_ref: str,
    cells: list[str],
    provider: str,
    litellm_model: str,
    temperature: float,
    max_tokens: int,
    api_base: str | None,
) -> dict:
    cells_block = [{"name": c, "version": "^1.0"} for c in cells]

    model_block: dict = {
        "provider": provider,
        "name": litellm_model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if api_base:
        model_block["api_base"] = api_base

    return {
        "name": name,
        "version": "0.1.0",
        "namespace": namespace,
        "persona": persona_ref,
        "cells": cells_block,
        "tools": [],
        "hooks": {},
        "model": model_block,
    }


@app.command()
def run(
    agent_name: str = typer.Argument(..., help="Agent name to load"),
    host: str = typer.Option(
        os.getenv("AGENTOS_HOST", "127.0.0.1"), help="Bind host"
    ),
    port: int = typer.Option(
        int(os.getenv("AGENTOS_PORT", "7777")), help="Bind port"
    ),
    reload: bool = typer.Option(
        False, "--reload", help="Auto-reload on code changes (dev only)"
    ),
):
    """Alias for ``start`` (kept for back-compat with the original README)."""
    start(agent_name=agent_name, host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
