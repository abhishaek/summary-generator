import logging

import anyio
from sentence_transformers import SentenceTransformer

from summary_generator.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Load the embedding model once, on first use (lazy singleton)."""
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def _encode(chunks: list[str]) -> list[list[float]]:
    model = _get_model()
    embeddings = model.encode(chunks, normalize_embeddings=True)
    return embeddings.tolist()


async def embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Embed each chunk into a vector. Runs the CPU-bound model in a worker
    thread so the async event loop is not blocked."""
    logger.debug("Embedding %d chunks", len(chunks))
    return await anyio.to_thread.run_sync(_encode, chunks)
