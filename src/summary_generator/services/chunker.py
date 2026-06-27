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

# Table-of-contents / index lines render as "Heading .............. 42": a label,
# a long run of dot leaders, then a page number. They are keyword-dense but carry
# no real information, and in similarity search they crowd out the actual content
# (e.g. a query for "CloudFormation" matches a dozen TOC rows before the prose
# that explains it). Drop any chunk dominated by dot-leader filler. Require a real
# leader run (4+ dots) AND a high dot ratio so ordinary prose with ellipses or
# abbreviations is never discarded.
_DOT_LEADER_RE = re.compile(r"\.\s*\.\s*\.\s*\.+")
_DOT_RATIO_THRESHOLD = 0.15


def _is_toc_noise(line: str) -> bool:
    if not _DOT_LEADER_RE.search(line):
        return False
    return line.count(".") / max(len(line), 1) > _DOT_RATIO_THRESHOLD


def _strip_toc_lines(text: str) -> str:
    """Remove table-of-contents/index lines before chunking. Done per line (not
    per chunk) so a chunk that mixes a stray TOC row with real prose keeps the
    prose instead of being discarded whole."""
    return "\n".join(line for line in text.splitlines() if not _is_toc_noise(line))


def count_tokens(text: str) -> int:
    response = client.models.count_tokens(model=GEMINI_MODEL, contents=text)
    return response.total_tokens


def split_into_chunks(text: str) -> list[str]:
    words = text.split()

    # 0.75 is only a starting guess (≈1 token per 0.75 words) to avoid counting
    # tokens word-by-word. Each candidate chunk is then verified with the real
    # tokenizer and shrunk until it fits, so the limit is enforced exactly.
    est_chunk_words = max(int(MAX_TOKENS_PER_CHUNK * 0.75), 1)
    overlap_in_words = int(CHUNK_OVERLAP_TOKENS * 0.75)

    chunks = []
    pos = 0

    while pos < len(words):
        end = min(pos + est_chunk_words, len(words))
        chunk = " ".join(words[pos:end])

        # Shrink until the chunk's real token count is within the limit. Back off
        # proportionally so an overshoot resolves in a few counts, not word-by-word.
        while end - pos > 1 and count_tokens(chunk) > MAX_TOKENS_PER_CHUNK:
            end = max(pos + 1, end - max(1, (end - pos) // 10))
            chunk = " ".join(words[pos:end])

        chunks.append(chunk)
        if end >= len(words):
            break

        # Cap overlap to half the chunk's words so a chunk shrunk below the
        # overlap size can't make the window crawl forward one word at a time.
        pos = end - min(overlap_in_words, (end - pos) // 2)

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
    Word-windowed and verified against the embedding model's own tokenizer so no
    chunk exceeds RETRIEVAL_CHUNK_TOKENS (well under the 256-token input limit)
    and gets truncated at embed time. Unlike chunk_text(), this always splits and
    counts tokens locally (no Gemini API call).
    """
    # Local import: embedder pulls in sentence_transformers (heavy), so keep it
    # out of this module's import path. count_embedding_tokens uses the embedding
    # model's own tokenizer — Gemini's count_tokens does not apply here.
    from summary_generator.services.embedder import count_embedding_tokens

    # Drop table-of-contents/index lines before windowing so they neither become
    # chunks nor pollute neighbouring ones. char_start is then an offset into this
    # cleaned text rather than the raw page text.
    text = _strip_toc_lines(text)

    words = list(re.finditer(r"\S+", text))
    print(f"[CHUNK] Chunking page text: chars={len(text)} words={len(words)} target_tokens_per_chunk={RETRIEVAL_CHUNK_TOKENS} overlap_tokens={RETRIEVAL_CHUNK_OVERLAP_TOKENS}")
    if not words:
        print("[CHUNK] Page has no words; produced 0 chunks")
        return []

    # 0.75 is only the initial word estimate; each window is then verified with
    # the embedding model's real tokenizer and shrunk until it fits, so no chunk
    # exceeds the limit and gets silently truncated at embed time.
    size = max(int(RETRIEVAL_CHUNK_TOKENS * 0.75), 1)
    overlap = int(RETRIEVAL_CHUNK_OVERLAP_TOKENS * 0.75)

    chunks: list[tuple[str, int]] = []
    pos = 0
    while pos < len(words):
        end = min(pos + size, len(words))
        start = words[pos].start()
        chunk = text[start : words[end - 1].end()]

        while end - pos > 1 and count_embedding_tokens(chunk) > RETRIEVAL_CHUNK_TOKENS:
            end = max(pos + 1, end - max(1, (end - pos) // 10))
            chunk = text[start : words[end - 1].end()]

        chunks.append((chunk, start))
        if end >= len(words):
            break

        # Cap the overlap to half the words this chunk actually holds. On dense
        # pages the shrink loop above can collapse a chunk to fewer words than
        # `overlap`; without this cap `end - overlap` falls at/behind `pos`, the
        # window crawls forward one word at a time, and a page explodes into
        # hundreds of near-identical overlapping chunks. This keeps the intended
        # overlap for normal text while guaranteeing forward progress.
        pos = end - min(overlap, (end - pos) // 2)

    print(f"[CHUNK] Page split into {len(chunks)} embedding chunk(s)")
    logger.debug("Text split into %d embedding chunks", len(chunks))
    return chunks
