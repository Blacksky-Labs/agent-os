"""The single model-call path for AgentOS — a thin OpenAI-compatible client.

Replaces LiteLLM. Almost every provider we use — Ollama (local), Together,
OpenAI, Groq, vLLM, LM Studio — speaks the OpenAI ``/v1/chat/completions`` shape,
so one small client covers them; the model config just changes the endpoint + key.
Native oddballs (Vertex/Gemini, Anthropic) can be added as small adapters here.

Keeps the SPEC principle: one inference path, no scattered provider calls. Used by
the llm-interface cell (responses) and the ingestion cell (signal extraction).

Request/response only (no streaming) — matches v0.1. Stdlib only, so it bundles
cleanly for the macOS app.
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request


# --- In-process inference backend (embedded hosts, e.g. iOS Swift+Gemma) ----------
# On iOS there's no model server to hit — Gemma runs in Swift on the Neural Engine. A
# host registers a callback here and chat_completion routes through it instead of HTTP,
# keeping Python the orchestrator and Swift the inference provider. See ios-build-plan §3b.
#     fn(request) -> response
#       request  = {"model", "messages", "temperature", "max_tokens"}
#       response = {"content": str, "usage": {...} | None}
_inference_backend = None


def set_inference_backend(fn) -> None:
    """Route all chat inference through ``fn`` (in-process) instead of HTTP."""
    global _inference_backend
    _inference_backend = fn


def clear_inference_backend() -> None:
    """Restore the HTTP path (Ollama / llama.cpp / OpenAI-compatible)."""
    global _inference_backend
    _inference_backend = None


def _resolve(model_cfg: dict) -> tuple[str, str, dict]:
    """Return (url, model, headers) for an OpenAI-compatible endpoint."""
    name = (model_cfg.get("name") or "").strip()
    provider = (model_cfg.get("provider") or "").strip().lower()
    if not provider and name.startswith("ollama/"):
        provider = "ollama"

    # Strip a leading "<provider>/" from the model name (LiteLLM-style tags).
    model = name
    if "/" in name and name.split("/", 1)[0].lower() == provider:
        model = name.split("/", 1)[1]

    # AGENTOS_LLM_API_BASE lets the host app point ALL inference at an embedded
    # runtime (e.g. a bundled llama.cpp server on a chosen port) regardless of what
    # the manifest says — the seam that drops the Ollama dependency. See ios-port-plan.md §3.
    api_base = os.getenv("AGENTOS_LLM_API_BASE") or model_cfg.get("api_base")
    if provider == "ollama" and not api_base:
        api_base = "http://127.0.0.1:11434"
    if not api_base:
        api_base = "https://api.openai.com"
    base = api_base.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    url = base + "/chat/completions"

    headers = {"Content-Type": "application/json"}
    key = model_cfg.get("api_key") or os.getenv("AGENTOS_LLM_API_KEY")
    if not key and provider:
        key = os.getenv(f"{provider.upper()}_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return url, model, headers


def _post_sync(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        raise RuntimeError(f"HTTP {e.code} from model endpoint: {detail}") from None


def _shape_out(content, usage) -> dict:
    out: dict = {"content": content, "usage": None}
    if isinstance(usage, dict):
        out["usage"] = {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
    return out


async def chat_completion(
    model_cfg: dict,
    messages: list[dict],
    *,
    timeout: float = 60.0,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict:
    """Run a chat completion via the registered in-process backend, else an
    OpenAI-compatible HTTP endpoint. Returns ``{"content", "usage"}``.

    Raises on connection/HTTP/backend errors — callers (cells) catch and degrade.
    """
    if not model_cfg.get("name"):
        raise ValueError("model.name missing")
    url, model, headers = _resolve(model_cfg)
    temp = temperature if temperature is not None else model_cfg.get("temperature")
    maxtok = max_tokens if max_tokens is not None else model_cfg.get("max_tokens")

    # In-process backend (iOS/Swift+Gemma) — no HTTP, no model server.
    if _inference_backend is not None:
        request = {"model": model, "messages": messages, "temperature": temp, "max_tokens": maxtok}
        result = await asyncio.to_thread(_inference_backend, request) or {}
        return _shape_out(result.get("content"), result.get("usage"))

    # HTTP path (Ollama / llama.cpp / OpenAI-compatible).
    payload: dict = {"model": model, "messages": messages}
    if temp is not None:
        payload["temperature"] = temp
    if maxtok is not None:
        payload["max_tokens"] = maxtok
    data = await asyncio.to_thread(_post_sync, url, payload, headers, timeout)
    choices = data.get("choices") or [{}]
    content = (choices[0].get("message") or {}).get("content")
    return _shape_out(content, data.get("usage"))


async def embeddings(model_cfg: dict, inputs: list[str], *, timeout: float = 60.0) -> list[list[float]]:
    """Embed texts via an OpenAI-compatible ``/v1/embeddings`` endpoint (Ollama, etc.).

    Returns one vector per input, in order. Raises on connection/HTTP errors.
    """
    if not inputs:
        return []
    if not model_cfg.get("name"):
        raise ValueError("model.name missing")
    url, model, headers = _resolve(model_cfg)
    url = url.rsplit("/chat/completions", 1)[0] + "/embeddings"
    data = await asyncio.to_thread(
        _post_sync, url, {"model": model, "input": inputs}, headers, timeout
    )
    items = sorted(data.get("data") or [], key=lambda d: d.get("index", 0))
    return [d["embedding"] for d in items]
