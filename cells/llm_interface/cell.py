"""llm-interface cell — v1.0.0.

Calls the configured LLM via LiteLLM. Reads ``context.assembled_prompt``
(the role-tagged message list ``context-builder`` produced) and the
manifest's ``model`` block (``context.meta["model"]``). Writes the
model's text response to ``context.response`` and token usage to
``context.meta["last_usage"]``.

v1.0.0 scope:
    - Plain (non-streaming, no tool-use) chat completion
    - Provider-agnostic via LiteLLM — Ollama, Together AI, and anything
      else LiteLLM supports follow the same code path
    - Errors recorded to ``context.cell_errors`` per SPEC §4; never raises

The tool-use loop is deliberately deferred to ``v1.1.0`` — it lands once
tools are registered in ``tools.registry.yaml`` and have a contract to
exercise against. The cell's interface doesn't change.

See SPEC.md §5 (llm-interface contract) and §6 (tool contract).
"""

from __future__ import annotations

import litellm

from agentos.context import AgentContext


# LiteLLM is chatty by default — quiet it down so our structured kernel
# logs stay clean.
litellm.suppress_debug_info = True


DEFAULT_TIMEOUT_S = 60.0


class Cell:
    name = "llm-interface"
    version = "1.0.0"

    def __init__(self, config: dict):
        self.config = config or {}

    def init(self, config: dict) -> None:
        pass

    async def execute(self, context: AgentContext) -> AgentContext:
        model_cfg = context.meta.get("model", {}) or {}

        # --- Sanity checks (record to cell_errors, never raise) ---
        model_name = model_cfg.get("name")
        if not model_name:
            context.cell_errors[self.name] = (
                "manifest.model.name missing — nothing to call"
            )
            return context

        if not context.assembled_prompt:
            context.cell_errors[self.name] = (
                "context.assembled_prompt empty — did context-builder run?"
            )
            return context

        # --- Build LiteLLM kwargs from the manifest's model block ---
        kwargs: dict = {
            "model": model_name,
            "messages": context.assembled_prompt,
            "timeout": model_cfg.get("timeout", DEFAULT_TIMEOUT_S),
        }
        if "temperature" in model_cfg:
            kwargs["temperature"] = model_cfg["temperature"]
        if "max_tokens" in model_cfg:
            kwargs["max_tokens"] = model_cfg["max_tokens"]
        if model_cfg.get("api_base"):
            # Ollama, vLLM, any OpenAI-compatible local server
            kwargs["api_base"] = model_cfg["api_base"]

        # --- Call the model ---
        try:
            response = await litellm.acompletion(**kwargs)
            context.response = response.choices[0].message.content

            usage = getattr(response, "usage", None)
            if usage is not None:
                context.meta["last_usage"] = {
                    "prompt_tokens":     getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "total_tokens":      getattr(usage, "total_tokens", None),
                }
        except Exception as e:
            context.cell_errors[self.name] = f"{type(e).__name__}: {e}"
            context.response = None

        return context

    async def teardown(self) -> None:
        pass
