import hashlib
import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from summary_generator.models.document import Document, DocumentChunk
from summary_generator.services.chunker import chunk_for_embedding
from summary_generator.services.embedder import embed_chunks

logger = logging.getLogger(__name__)


def _content_hash(pages: list[tuple[int, str]]) -> str:
    """sha256 of the extracted text. Hashing the parsed text (not raw bytes)
    means renamed files and the same content in different formats both dedup."""
    joined = "\n".join(text for _, text in pages)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


async def _find_duplicate(db: AsyncSession, user_id: int, content_hash: str) -> tuple[Document, int] | None:
    existing = (
        await db.execute(
            select(Document).where(
                Document.user_id == user_id, Document.content_hash == content_hash
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        return None
    count = (
        await db.execute(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.document_id == existing.id
            )
        )
    ).scalar_one()
    return existing, count


async def ingest_document(
    db: AsyncSession,
    user_id: int,
    filename: str | None,
    pages: list[tuple[int, str]],
) -> tuple[Document, int, bool]:
    """Chunk, embed, and persist a document from its per-page text.

    `pages` is a list of (page_number, text). Each page is chunked independently
    so every chunk keeps its source page number and char offset within that page.
    If the same content was already ingested by this user, the existing document
    is returned instead of re-ingesting.

    Returns (document, chunks_stored, created) where `created` is False when an
    existing duplicate was returned.
    """
    content_hash = _content_hash(pages)

    duplicate = await _find_duplicate(db, user_id, content_hash)
    if duplicate is not None:
        document, count = duplicate
        logger.info("Duplicate upload: returning existing document id=%d filename=%s", document.id, filename)
        return document, count, False

    page_chunks: list[tuple[int, int, str]] = [
        (page_number, char_start, chunk)
        for page_number, page_text in pages
        for chunk, char_start in chunk_for_embedding(page_text)
    ]
    embeddings = await embed_chunks([chunk for _, _, chunk in page_chunks])

    document = Document(user_id=user_id, filename=filename, content_hash=content_hash)
    document.chunks = [
        DocumentChunk(
            chunk_index=i,
            page_number=page_number,
            char_start=char_start,
            content=chunk,
            embedding=embedding,
        )
        for i, ((page_number, char_start, chunk), embedding) in enumerate(zip(page_chunks, embeddings))
    ]

    db.add(document)
    try:
        await db.commit()
    except IntegrityError:
        # Concurrent upload of identical content won the race; return its row.
        await db.rollback()
        duplicate = await _find_duplicate(db, user_id, content_hash)
        if duplicate is not None:
            document, count = duplicate
            logger.info("Duplicate upload (race): returning existing document id=%d", document.id)
            return document, count, False
        raise

    # expire_on_commit is False, so document.id stays available without a lazy
    # reload (accessing relationships post-commit would trigger async lazy-load).
    logger.info("Document stored: id=%d chunks=%d filename=%s", document.id, len(page_chunks), filename)
    return document, len(page_chunks), True
