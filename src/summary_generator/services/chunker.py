import logging
import re

from summary_generator.config import (
    GEMINI_MODEL,
    MAX_TOKENS_PER_CHUNK,
    RETRIEVAL_CHUNK_TOKENS,
    RETRIEVAL_CHUNK_OVERLAP_TOKENS,
)
from summary_generator.shared.gemini_client import client

logger = logging.getLogger(__name__)

CHUNK_OVERLAP_TOKENS = 200


def count_tokens(text: str) -> int:
    response = client.models.count_tokens(model=GEMINI_MODEL, contents=text)
    return response.total_tokens


def split_into_chunks(text: str) -> list[str]:
    words = text.split()

    chunk_size_in_words = int(MAX_TOKENS_PER_CHUNK * 0.75)
    overlap_in_words = int(CHUNK_OVERLAP_TOKENS * 0.75)

    chunks = []
    pos = 0

    while pos < len(words):
        chunk_words = words[pos : pos + chunk_size_in_words]
        chunks.append(" ".join(chunk_words))
        pos += chunk_size_in_words - overlap_in_words

    return chunks


def chunk_text(text: str) -> list[str]:
    total_tokens = count_tokens(text)
    logger.debug("Token count: %d (limit=%d)", total_tokens, MAX_TOKENS_PER_CHUNK)

    if total_tokens <= MAX_TOKENS_PER_CHUNK:
        return [text]

    chunks = split_into_chunks(text)
    logger.info("Text split into %d chunks (total_tokens=%d)", len(chunks), total_tokens)
    return chunks


def chunk_for_embedding(text: str) -> list[tuple[str, int]]:
    """Split text into small, retrieval-sized chunks for embedding.

    Returns (chunk_text, char_start) tuples, where char_start is the chunk's
    offset in the input text (chunk_text == text[char_start:][:len(chunk_text)]).
    Word-windowed and sized well under the embedding model's 256-token limit so
    no chunk is truncated at embed time. Unlike chunk_text(), this always splits
    and needs no token-count API call.
    """
    words = list(re.finditer(r"\S+", text))
    if not words:
        return []

    size = int(RETRIEVAL_CHUNK_TOKENS * 0.75)
    overlap = int(RETRIEVAL_CHUNK_OVERLAP_TOKENS * 0.75)
    step = max(size - overlap, 1)

    chunks: list[tuple[str, int]] = []
    pos = 0
    while pos < len(words):
        window = words[pos : pos + size]
        start = window[0].start()
        end = window[-1].end()
        chunks.append((text[start:end], start))
        pos += step

    logger.debug("Text split into %d embedding chunks", len(chunks))
    return chunks
