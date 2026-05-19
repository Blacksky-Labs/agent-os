"""Document ingestion for the retrieval cell.

Walks a file or folder, chunks text content, embeds each chunk via
LiteLLM, and upserts into the agent's per-namespace Chroma collection.

Called by the ``agentos ingest`` CLI command — not by any cell at chat
time. Chunks are id'd by hash of (source, chunk_index, text) so
re-ingesting the same file is idempotent.

v1.0.0 scope:
    - File types: ``.md``, ``.txt``, ``.markdown`` (PDF later)
    - Chunking: paragraph-based with sliding-window fallback for long paragraphs
    - Embeddings via ``cells.retrieval.embed.embed_texts``
    - Storage via ``cells.retrieval.store.add_chunks``
"""

from __future__ import annotations

from pathlib import Path

from cells.retrieval.embed import embed_texts
from cells.retrieval.store import add_chunks, chunk_id, count, open_collection, query


SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".md", ".txt", ".markdown"})

DEFAULT_TARGET_CHARS = 700      # roughly 150-200 tokens per chunk
DEFAULT_MAX_CHARS = 1200        # hard cap per chunk
DEFAULT_OVERLAP_CHARS = 80      # context bleed between sliding-window chunks


# ----------------------------------------------------------------------
# File walking
# ----------------------------------------------------------------------

def discover_files(path: Path) -> list[Path]:
    """Return the list of supported files at `path` (file or directory)."""
    path = Path(path).expanduser().resolve()
    if not path.exists():
        return []
    if path.is_file():
        return [path] if path.suffix.lower() in SUPPORTED_EXTENSIONS else []
    found: list[Path] = []
    for p in path.rglob("*"):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
            found.append(p)
    return sorted(found)


# ----------------------------------------------------------------------
# Chunking
# ----------------------------------------------------------------------

def chunk_text(
    text: str,
    target_chars: int = DEFAULT_TARGET_CHARS,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[str]:
    """Split a document into chunks.

    Strategy:
        1. Split by blank-line paragraphs.
        2. Merge consecutive short paragraphs until ~target_chars.
        3. Long paragraphs get sliding-window split at max_chars with
           overlap_chars of context bleed.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0

    def flush() -> None:
        nonlocal buf, buf_len
        if buf:
            chunks.append("\n\n".join(buf))
            buf = []
            buf_len = 0

    for para in paragraphs:
        if len(para) > max_chars:
            flush()
            # Sliding window for long paragraphs
            step = max_chars - overlap_chars
            for start in range(0, len(para), step):
                window = para[start : start + max_chars]
                if window:
                    chunks.append(window)
            continue
        if buf_len + len(para) > target_chars and buf:
            flush()
        buf.append(para)
        buf_len += len(para) + 2  # account for the join separator

    flush()
    return [c for c in chunks if c.strip()]


# ----------------------------------------------------------------------
# Top-level ingest
# ----------------------------------------------------------------------

async def ingest_path(
    namespace: str,
    path: Path,
    embedding_model: str,
    embedding_api_base: str | None = None,
    repo_root: Path | str = ".",
) -> dict:
    """Ingest a file or directory into a namespace's Chroma collection.

    Returns a stats dict for the CLI to print:
        {
            "files":   <int>,
            "chunks":  <int>,
            "skipped": <int>,
            "errors":  [...],
        }
    """
    files = discover_files(Path(path))
    if not files:
        return {"files": 0, "chunks": 0, "skipped": 0, "errors": [
            f"no supported files found at {path}"
        ]}

    collection = await open_collection(namespace, repo_root=repo_root)

    total_chunks = 0
    errors: list[str] = []

    for file_path in files:
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            errors.append(f"{file_path}: not utf-8 ({e})")
            continue
        except Exception as e:
            errors.append(f"{file_path}: read failed ({e})")
            continue

        chunks = chunk_text(text)
        if not chunks:
            continue

        try:
            embeddings = await embed_texts(
                chunks,
                model=embedding_model,
                api_base=embedding_api_base,
            )
        except Exception as e:
            errors.append(f"{file_path}: embedding failed ({type(e).__name__}: {e})")
            continue

        source = str(file_path)
        ids = [chunk_id(source, i, c) for i, c in enumerate(chunks)]
        metadatas = [
            {"source": source, "chunk_index": i, "namespace": namespace}
            for i in range(len(chunks))
        ]

        await add_chunks(
            collection,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids,
        )
        total_chunks += len(chunks)

    final_count = await count(collection)

    # Warm-up: force the HNSW index to materialize on disk before this
    # process exits. Without this, a separate reader process (the
    # FastAPI server) can hit "Error creating hnsw segment reader:
    # Nothing found on disk" on first query — especially when the
    # corpus has only a handful of chunks.
    if total_chunks > 0 and embeddings:
        try:
            await query(collection, query_embedding=embeddings[-1], top_k=1)
        except Exception:
            # Warm-up failure is non-fatal — the data is still in SQLite
            # and the next query attempt will trigger the build.
            pass

    return {
        "files": len(files),
        "chunks": total_chunks,
        "total_in_collection": final_count,
        "errors": errors,
    }
