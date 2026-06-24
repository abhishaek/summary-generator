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


def _encode(chunks: list[str]) -> list[list[float]]:
    model = _get_model()
    embeddings = model.encode(chunks, normalize_embeddings=True, show_progress_bar=False)
    return embeddings.tolist()


async def embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Embed each chunk into a vector. Runs the CPU-bound model in a worker
    thread so the async event loop is not blocked."""
    logger.debug("Embedding %d chunks", len(chunks))
    return await anyio.to_thread.run_sync(_encode, chunks)
