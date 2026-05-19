"""retrieval cell — v1.0.0.

Vector search over a per-namespace ChromaDB collection. Embeds the
current user message via LiteLLM (Ollama by default), queries the
collection, writes the top-k chunks into ``context.retrieved_chunks``
with source attribution and similarity scores.

Per SPEC §5 the retrieval cell is read-only on the turn path. Ingestion
(writing new documents into the corpus) lives in ``cells/retrieval/ingest.py``
and is invoked by the ``agentos ingest`` CLI — not by the cell itself.

v1.0.0 config (from manifest's ``cells[].config`` block):
    embedding_model:     LiteLLM model string (default: ollama/nomic-embed-text:latest)
    embedding_api_base:  provider URL (default: http://localhost:11434)
    top_k:               max chunks to return (default: 5)
    min_score:           drop chunks below this cosine similarity (default: 0.0)

Errors (Ollama unreachable, model not pulled, Chroma error) are caught
and recorded to ``context.cell_errors`` per SPEC §4. The cell never
crashes the pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentos.context import AgentContext

from cells.retrieval.embed import embed_one
from cells.retrieval.store import open_collection, query, count


DEFAULT_EMBEDDING_MODEL = "ollama/nomic-embed-text:latest"
DEFAULT_EMBEDDING_API_BASE = "http://localhost:11434"


class Cell:
    name = "retrieval"
    version = "1.0.0"

    def __init__(self, config: dict):
        self.config = config or {}
        self.embedding_model: str = self.config.get(
            "embedding_model", DEFAULT_EMBEDDING_MODEL
        )
        self.embedding_api_base: str | None = self.config.get(
            "embedding_api_base", DEFAULT_EMBEDDING_API_BASE
        )
        self.top_k: int = int(self.config.get("top_k", 5))
        self.min_score: float = float(self.config.get("min_score", 0.0))

        self._collection: Any | None = None
        self._inited_for_ns: str | None = None

    def init(self, config: dict) -> None:
        # Lazy: namespace isn't known at init() time.
        pass

    async def execute(self, context: AgentContext) -> AgentContext:
        # Skip silently if there's nothing to search against — empty
        # message OR empty corpus.
        if not context.user_message:
            return context

        try:
            if self._collection is None or self._inited_for_ns != context.namespace:
                self._collection = await open_collection(context.namespace)
                self._inited_for_ns = context.namespace

            # If the corpus is empty, no point embedding the query.
            if await count(self._collection) == 0:
                return context

            query_vec = await embed_one(
                context.user_message,
                model=self.embedding_model,
                api_base=self.embedding_api_base,
            )

            result = await query(
                self._collection,
                query_embedding=query_vec,
                top_k=self.top_k,
            )

            chunks: list[dict] = []
            docs = (result.get("documents") or [[]])[0]
            metas = (result.get("metadatas") or [[]])[0]
            dists = (result.get("distances") or [[]])[0]

            for doc, meta, dist in zip(docs, metas, dists):
                # Chroma returns cosine "distance" = 1 - similarity for
                # cosine space, so similarity = 1 - dist.
                similarity = 1.0 - float(dist)
                if similarity < self.min_score:
                    continue
                chunks.append({
                    "content": doc,
                    "source": (meta or {}).get("source", "unknown"),
                    "chunk_index": (meta or {}).get("chunk_index"),
                    "similarity": round(similarity, 4),
                })

            context.retrieved_chunks = chunks
        except Exception as e:
            # Graceful degrade — pipeline keeps running, chat still works,
            # but retrieved_chunks stays empty and the error is logged.
            context.cell_errors[self.name] = f"{type(e).__name__}: {e}"

        return context

    async def teardown(self) -> None:
        pass
