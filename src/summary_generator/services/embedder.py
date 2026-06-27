import logging
import os

# Skip the HuggingFace Hub network round-trip when loading the model: it is
# already cached locally, and the online revision check adds ~10s per process
# start. Set these before importing sentence_transformers. To download the
# model the first time on a fresh machine, export HF_HUB_OFFLINE=0.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import anyio  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

from summary_generator.config import EMBEDDING_MODEL  # noqa: E402

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Load the embedding model once (lazy singleton)."""
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def warmup_model() -> None:
    """Load the model ahead of time (called at app startup) so no request pays
    the one-time load cost."""
    _get_model()


def count_embedding_tokens(text: str) -> int:
    """Count tokens using the embedding model's *own* WordPiece tokenizer.

    Gemini's count_tokens is the wrong source of truth here: the embedding model
    (all-MiniLM-L6-v2) uses a different tokenizer and a hard 256-token input
    limit. Special tokens ([CLS]/[SEP]) are included because they count toward
    that limit.
    """
    tokenizer = _get_model().tokenizer
    return len(tokenizer(text, add_special_tokens=True)["input_ids"])


def _encode(chunks: list[str]) -> list[list[float]]:
    model = _get_model()
    embeddings = model.encode(chunks, normalize_embeddings=True, show_progress_bar=False)
    return embeddings.tolist()


async def embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Embed each chunk into a vector. Runs the CPU-bound model in a worker
    thread so the async event loop is not blocked."""
    print(f"[EMBED] Embedding {len(chunks)} chunk(s) with model={EMBEDDING_MODEL} (running in worker thread)")
    logger.debug("Embedding %d chunks", len(chunks))
    vectors = await anyio.to_thread.run_sync(_encode, chunks)
    dim = len(vectors[0]) if vectors else 0
    print(f"[EMBED] Produced {len(vectors)} embedding vector(s), dimension={dim}")
    return vectors


async def embed_query(text: str) -> list[float]:
    """Embed a single query string into a vector, produced the same way as the
    stored chunk vectors (same model, normalized) so cosine search is valid.
    Runs the CPU-bound model in a worker thread so the event loop is not blocked."""
    print(f"[RETRIEVAL 3/8] Embedding query into a vector with model={EMBEDDING_MODEL}: chars={len(text)} (same model/normalization as stored chunks)")
    logger.debug("Embedding query (%d chars)", len(text))
    vectors = await anyio.to_thread.run_sync(_encode, [text])
    print(f"[RETRIEVAL 4/8] Query embedded: vector dimension={len(vectors[0])}")
    return vectors[0]