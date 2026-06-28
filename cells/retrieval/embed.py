"""Embedding helper for the retrieval cell + ingest CLI.

Uses the in-house OpenAI-compatible client (``agentos.llm.embeddings``) — the
same code path serves Ollama (local), Together, OpenAI, or any provider exposing
``/v1/embeddings``. For v1 we standardize on Ollama via ``nomic-embed-text``.

Model string follows the same convention as the chat path: ``ollama/<name>`` for
Ollama, ``together_ai/<name>`` for Together, etc.
"""

from __future__ import annotations

from agentos.llm import embeddings as _embeddings


# Reasonable batch size to avoid hammering the local model with one huge
# request. Smaller batches give cleaner progress reporting and recover better
# from interruption.
DEFAULT_BATCH_SIZE = 32


async def embed_texts(
    texts: list[str],
    model: str,
    api_base: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> list[list[float]]:
    """Embed a batch of texts. Returns one vector per input text, in order.

    Args:
        texts: list of strings to embed
        model: model string (e.g. ``ollama/nomic-embed-text:latest``)
        api_base: provider URL (e.g. the Ollama daemon address)
        batch_size: how many texts to send per request

    Raises:
        Exceptions propagate — callers catch and record to ``cell_errors`` (cells)
        or fail fast (CLI).
    """
    if not texts:
        return []

    model_cfg = {"name": model, "api_base": api_base}
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        vectors.extend(await _embeddings(model_cfg, texts[i : i + batch_size]))
    return vectors


async def embed_one(text: str, model: str, api_base: str | None = None) -> list[float]:
    """Convenience for single-text embedding (e.g. a query)."""
    result = await embed_texts([text], model=model, api_base=api_base)
    return result[0]
