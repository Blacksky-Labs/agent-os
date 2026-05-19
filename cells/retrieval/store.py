"""ChromaDB persistence for the retrieval cell + ingest CLI.

One Chroma collection per namespace, persisted at
``data/<namespace>/chroma/``. The collection is created with
``embedding_function=None`` so it never tries to embed on its own —
all embeddings come from ``cells/retrieval/embed.py``, which keeps the
embedding model under the manifest's control.

Async surface wraps Chroma's sync API via ``asyncio.to_thread`` so the
cell's async contract holds.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings


COLLECTION_NAME = "documents"


def chroma_dir_for(namespace: str, repo_root: Path | str = ".") -> Path:
    """Canonical Chroma persist directory for a namespace."""
    return Path(repo_root) / "data" / namespace / "chroma"


def chunk_id(source: str, chunk_index: int, text: str) -> str:
    """Stable id so re-ingesting the same content is idempotent."""
    payload = f"{source}\x1f{chunk_index}\x1f{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


# ----------------------------------------------------------------------
# Sync core
# ----------------------------------------------------------------------

def _open_sync(namespace: str, repo_root: Path | str) -> Any:
    path = chroma_dir_for(namespace, repo_root)
    path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(path),
        settings=Settings(anonymized_telemetry=False),
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=None,    # we pass pre-computed embeddings only
        metadata={"hnsw:space": "cosine"},
    )


def _add_sync(
    collection: Any,
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
    ids: list[str],
) -> None:
    # upsert keeps re-ingestion idempotent (same id → replace)
    collection.upsert(
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids,
    )


def _query_sync(
    collection: Any,
    query_embedding: list[float],
    top_k: int,
) -> dict:
    n = collection.count()
    if n == 0:
        return {"documents": [[]], "metadatas": [[]], "distances": [[]], "ids": [[]]}
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, n),
    )


def _count_sync(collection: Any) -> int:
    return collection.count()


# ----------------------------------------------------------------------
# Async surface (cells + ingest call these)
# ----------------------------------------------------------------------

async def open_collection(namespace: str, repo_root: Path | str = ".") -> Any:
    """Open (or create) the namespace's Chroma collection."""
    return await asyncio.to_thread(_open_sync, namespace, repo_root)


async def add_chunks(
    collection: Any,
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
    ids: list[str],
) -> None:
    """Upsert a batch of chunks (idempotent by id)."""
    await asyncio.to_thread(
        _add_sync, collection, documents, embeddings, metadatas, ids
    )


async def query(
    collection: Any,
    query_embedding: list[float],
    top_k: int = 5,
) -> dict:
    """Vector-similarity query. Returns Chroma's raw result shape."""
    return await asyncio.to_thread(_query_sync, collection, query_embedding, top_k)


async def count(collection: Any) -> int:
    """How many chunks are currently in the collection."""
    return await asyncio.to_thread(_count_sync, collection)
