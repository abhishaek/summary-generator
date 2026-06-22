import logging

from sqlalchemy.ext.asyncio import AsyncSession

from summary_generator.models.document import Document, DocumentChunk
from summary_generator.services.chunker import chunk_for_embedding
from summary_generator.services.embedder import embed_chunks

logger = logging.getLogger(__name__)


async def ingest_document(
    db: AsyncSession,
    user_id: int,
    filename: str | None,
    pages: list[tuple[int, str]],
) -> tuple[Document, int]:
    """Chunk, embed, and persist a document from its per-page text.

    `pages` is a list of (page_number, text). Each page is chunked independently
    so every chunk keeps its source page number and char offset within that page.
    Returns (document, chunks_stored).
    """
    page_chunks: list[tuple[int, int, str]] = [
        (page_number, char_start, chunk)
        for page_number, page_text in pages
        for chunk, char_start in chunk_for_embedding(page_text)
    ]
    embeddings = await embed_chunks([chunk for _, _, chunk in page_chunks])

    document = Document(user_id=user_id, filename=filename)
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
    await db.commit()

    # expire_on_commit is False, so document.id stays available without a lazy
    # reload (accessing relationships post-commit would trigger async lazy-load).
    logger.info("Document stored: id=%d chunks=%d filename=%s", document.id, len(page_chunks), filename)
    return document, len(page_chunks)
