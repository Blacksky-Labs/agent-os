"""Embedding helper for the retrieval cell + ingest CLI.

Uses LiteLLM's async embedding interface so the same code path serves
Ollama (local), Together AI, or any other LiteLLM-supported provider.
For v1.0.0 we standardize on Ollama via ``nomic-embed-text``.

Model string follows LiteLLM convention: ``ollama/<name>`` for Ollama,
``together_ai/<name>`` for Together, etc.
"""

from __future__ import annotations

import litellm


# Reasonable batch size to avoid hammering the local model with one huge
# request. Ollama handles batches fine, but smaller batches give cleaner
# progress reporting and recover better from interruption.
DEFAULT_BATCH_SIZE = 32


async def embed_texts(
    texts: list[str],
    model: str,
    api_base: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> list[list[float]]:
    """Embed a batch of texts. Returns one vector per input text.

    Args:
        texts: list of strings to embed
        model: LiteLLM model string (e.g. ``ollama/nomic-embed-text:latest``)
        api_base: provider-specific URL (e.g. Ollama daemon address)
        batch_size: how many texts to send per request

    Returns:
        list of embedding vectors, in the same order as `texts`.

    Raises:
        Exceptions from LiteLLM propagate — callers should catch and
        either record to ``cell_errors`` (in cells) or fail fast (in CLI).
    """
    if not texts:
        return []

    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        kwargs: dict = {"model": model, "input": batch}
        if api_base:
            kwargs["api_base"] = api_base
        response = await litellm.aembedding(**kwargs)
        # LiteLLM normalizes to OpenAI shape: response.data is a list of
        # {"embedding": [...], "index": int, "object": "embedding"}.
        # Sort by index to ensure order matches input.
        items = sorted(response.data, key=lambda d: d.get("index", 0))
        vectors.extend(d["embedding"] for d in items)

    return vectors


async def embed_one(text: str, model: str, api_base: str | None = None) -> list[float]:
    """Convenience for single-text embedding (e.g. a query)."""
    result = await embed_texts([text], model=model, api_base=api_base)
    return result[0]
