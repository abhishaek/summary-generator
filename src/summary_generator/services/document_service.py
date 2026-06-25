import hashlib
import logging

import anyio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from summary_generator.database import AsyncSessionLocal
from summary_generator.models.document import Document, DocumentChunk, JobStatus
from summary_generator.services.chunker import chunk_for_embedding
from summary_generator.services.embedder import embed_chunks
from summary_generator.shared.file_validation import extract_document_pages

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


async def _embed_and_build_chunks(pages: list[tuple[int, str]]) -> list[DocumentChunk]:
    """Chunk each page, embed every chunk, and build the DocumentChunk rows.

    Shared by both ingest paths. Pages are chunked independently so each chunk
    keeps its source page number and char offset within that page.
    """
    page_chunks: list[tuple[int, int, str]] = [
        (page_number, char_start, chunk)
        for page_number, page_text in pages
        for chunk, char_start in chunk_for_embedding(page_text)
    ]
    embeddings = await embed_chunks([chunk for _, _, chunk in page_chunks])

    return [
        DocumentChunk(
            chunk_index=i,
            page_number=page_number,
            char_start=char_start,
            content=chunk,
            embedding=embedding,
        )
        for i, ((page_number, char_start, chunk), embedding) in enumerate(
            zip(page_chunks, embeddings)
        )
    ]


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

    chunks = await _embed_and_build_chunks(pages)

    document = Document(user_id=user_id, filename=filename, content_hash=content_hash)
    document.status = JobStatus.DONE.value
    document.chunks_stored = len(chunks)
    document.chunks = chunks

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
    logger.info("Document stored: id=%d chunks=%d filename=%s", document.id, len(chunks), filename)
    return document, len(chunks), True


async def process_document(document_id: int, contents: bytes, filename: str | None) -> None:
    """Background task: parse, chunk, embed, and store a pending document,
    updating its status as it goes.

    Opens its own DB session because the request's session is already closed
    by the time this runs (it fires after the 202 response is sent). The raw
    file `contents` are passed in directly rather than re-read from the upload.
    """
    async with AsyncSessionLocal() as db:
        document = await db.get(Document, document_id)
        if document is None:
            logger.error("process_document: document id=%d not found", document_id)
            return

        document.status = JobStatus.PROCESSING.value
        await db.commit()

        try:
            # Parsing is CPU-bound and synchronous; run it off the event loop.
            pages, _mime_type = await anyio.to_thread.run_sync(
                extract_document_pages, contents, filename
            )
            content_hash = _content_hash(pages)

            # The content hash needs the parsed text, so dedup can only happen
            # here (not at upload time). A matching stored doc means this upload
            # is a duplicate.
            duplicate = await _find_duplicate(db, document.user_id, content_hash)
            if duplicate is not None:
                existing, _count = duplicate
                document.status = JobStatus.DUPLICATE.value
                document.error = f"Duplicate of document {existing.id}"
                await db.commit()
                logger.info("Document id=%d is duplicate of id=%d", document_id, existing.id)
                return

            chunks = await _embed_and_build_chunks(pages)

            document.content_hash = content_hash
            document.chunks = chunks
            document.chunks_stored = len(chunks)
            document.status = JobStatus.DONE.value
            await db.commit()
            logger.info("Document stored: id=%d chunks=%d", document_id, len(chunks))

        except IntegrityError:
            # A concurrent upload of identical content won the unique-constraint
            # race. Re-fetch (rollback expired the row) and mark this one a dup.
            await db.rollback()
            document = await db.get(Document, document_id)
            if document is not None:
                document.status = JobStatus.DUPLICATE.value
                document.error = "Duplicate content (race)."
                await db.commit()
            logger.info("Document id=%d lost dedup race, marked duplicate", document_id)

        except Exception as exc:
            # Any parse/embed/storage failure: record it so the client polling
            # the status endpoint sees `failed` with a reason instead of hanging.
            await db.rollback()
            document = await db.get(Document, document_id)
            if document is not None:
                document.status = JobStatus.FAILED.value
                document.error = getattr(exc, "detail", str(exc))
                await db.commit()
            logger.exception("Ingest failed for document id=%d", document_id)
