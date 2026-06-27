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
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    print(f"[HASH] Computed content hash over {len(pages)} page(s): sha256={digest[:12]}...")
    return digest


async def _find_duplicate(db: AsyncSession, user_id: int, content_hash: str) -> tuple[Document, int] | None:
    existing = (
        await db.execute(
            select(Document).where(
                Document.user_id == user_id, Document.content_hash == content_hash
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        print(f"[DEDUP] No existing document with this content hash for user_id={user_id}; this is new content")
        return None
    count = (
        await db.execute(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.document_id == existing.id
            )
        )
    ).scalar_one()
    print(f"[DEDUP] Found duplicate: existing document id={existing.id} with {count} stored chunk(s)")
    return existing, count


async def _embed_and_build_chunks(pages: list[tuple[int, str]]) -> list[DocumentChunk]:
    """Chunk each page, embed every chunk, and build the DocumentChunk rows.

    Shared by both ingest paths. Pages are chunked independently so each chunk
    keeps its source page number and char offset within that page.
    """
    print(f"[BUILD] Starting chunk + embed for {len(pages)} page(s)")
    page_chunks: list[tuple[int, int, str]] = [
        (page_number, char_start, chunk)
        for page_number, page_text in pages
        for chunk, char_start in chunk_for_embedding(page_text)
    ]
    print(f"[BUILD] All pages chunked: {len(page_chunks)} total chunk(s) across the document; now embedding")
    embeddings = await embed_chunks([chunk for _, _, chunk in page_chunks])
    print(f"[BUILD] Building {len(page_chunks)} DocumentChunk row(s) (chunk text + page + offset + embedding)")

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
    print(f"[TEXT-INGEST 1/5] Starting text ingest: user_id={user_id} title={filename} pages={len(pages)}")
    content_hash = _content_hash(pages)

    duplicate = await _find_duplicate(db, user_id, content_hash)
    if duplicate is not None:
        document, count = duplicate
        print(f"[TEXT-INGEST x/5] Duplicate; returning existing document id={document.id} (no re-ingest)")
        logger.info("Duplicate upload: returning existing document id=%d filename=%s", document.id, filename)
        return document, count, False

    print(f"[TEXT-INGEST 2/5] Content is new; chunking + embedding: user_id={user_id}")
    chunks = await _embed_and_build_chunks(pages)

    print(f"[TEXT-INGEST 3/5] Building document row with {len(chunks)} chunk(s)")
    document = Document(user_id=user_id, filename=filename, content_hash=content_hash)
    document.status = JobStatus.DONE.value
    document.chunks_stored = len(chunks)
    document.chunks = chunks

    db.add(document)
    try:
        print(f"[TEXT-INGEST 4/5] Committing document + chunks to DB")
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
    print(f"[TEXT-INGEST 5/5] Stored successfully: id={document.id} chunks_stored={len(chunks)} status=DONE")
    logger.info("Document stored: id=%d chunks=%d filename=%s", document.id, len(chunks), filename)
    return document, len(chunks), True


async def process_document(document_id: int, contents: bytes, filename: str | None) -> None:
    """Background task: parse, chunk, embed, and store a pending document,
    updating its status as it goes.

    Opens its own DB session because the request's session is already closed
    by the time this runs (it fires after the 202 response is sent). The raw
    file `contents` are passed in directly rather than re-read from the upload.
    """
    print(f"[INGEST 6/9] Background task started: id={document_id} filename={filename}")
    async with AsyncSessionLocal() as db:
        document = await db.get(Document, document_id)
        if document is None:
            logger.error("process_document: document id=%d not found", document_id)
            return

        document.status = JobStatus.PROCESSING.value
        await db.commit()
        print(f"[INGEST 6/9] Status set to PROCESSING: id={document_id}")

        try:
            # Parsing is CPU-bound and synchronous; run it off the event loop.
            print(f"[INGEST 7/9] Parsing file into pages: id={document_id}")
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
                print(f"[INGEST x/9] Stopping: id={document_id} is a DUPLICATE of id={existing.id}")
                logger.info("Document id=%d is duplicate of id=%d", document_id, existing.id)
                return

            print(f"[INGEST 8/9] Content is new; chunking + embedding: id={document_id}")
            chunks = await _embed_and_build_chunks(pages)

            document.content_hash = content_hash
            # Set the FK on each chunk and add them directly instead of assigning
            # document.chunks = chunks. The document is a persistent (already-loaded)
            # row here, so assigning the relationship would first lazy-load the
            # existing chunks collection to reconcile delete-orphan — and a lazy
            # load is async I/O that can't run in this synchronous assignment,
            # raising MissingGreenlet. Setting document_id + add_all avoids it.
            for chunk in chunks:
                chunk.document_id = document.id
            db.add_all(chunks)
            document.chunks_stored = len(chunks)
            document.status = JobStatus.DONE.value
            print(f"[INGEST 9/9] Committing {len(chunks)} chunk(s) to DB and setting status=DONE: id={document_id}")
            await db.commit()
            print(f"[INGEST 9/9] Stored successfully: id={document_id} chunks_stored={len(chunks)} status=DONE")
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
