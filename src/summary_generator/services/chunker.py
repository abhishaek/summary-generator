import logging
from summary_generator.config import GEMINI_MODEL, MAX_TOKENS_PER_CHUNK
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
