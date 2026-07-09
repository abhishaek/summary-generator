import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from summary_generator.config import RETRIEVAL_MIN_SIMILARITY
from summary_generator.models.document import Document, DocumentChunk, JobStatus
from summary_generator.schemas.retrieval import RetrievedChunk
from summary_generator.services.embedder import embed_query

logger = logging.getLogger(__name__)


async def retrieve(
    db: AsyncSession,
    user_id: int,
    query: str,
    top_k: int,
    document_id: int | None = None,
) -> list[RetrievedChunk]:
    """Semantic search over the requesting user's stored chunks.

    Embeds the query, then ranks DocumentChunk rows by cosine distance. Ownership
    is enforced unconditionally — only this user's DONE documents are searched —
    mirroring the 404-not-403 rule in the documents router. Ordering uses
    cosine_distance (<=>) so the HNSW index applies; this operator MUST stay
    cosine or Postgres silently falls back to a sequential scan.
    """
    print(f"[RETRIEVAL 2/8] Retrieve service started: user_id={user_id} query={query!r} top_k={top_k} document_id={document_id}")

    # Fail fast on a bad document filter BEFORE the expensive work. A caller can
    # pass any id (45, 12234, ...); without this check we would still embed the
    # query and run the vector search only to return nothing. One cheap indexed
    # lookup avoids the embedding cost (and, with summarize on, the Gemini call).
    # 404-not-403: an id owned by another user looks identical to a missing one,
    # so ownership never leaks — mirroring the documents router.
    if document_id is not None:
        owns = (
            await db.execute(
                select(Document.id)
                .where(Document.id == document_id)
                .where(Document.user_id == user_id)
                .where(Document.status == JobStatus.DONE.value)
            )
        ).scalar_one_or_none()
        if owns is None:
            print(f"[RETRIEVAL x/8] document_id={document_id} not found for user {user_id} (or not DONE); skipping embed + search")
            logger.info("Retrieval rejected: user=%d doc=%s not found/owned/DONE", user_id, document_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found.",
            )

    query_vec = await embed_query(query)

    distance = DocumentChunk.embedding.cosine_distance(query_vec)
    # For normalized vectors similarity = 1 - distance, so the min-similarity
    # threshold becomes a max-distance bound the DB can filter on directly.
    max_distance = 1 - RETRIEVAL_MIN_SIMILARITY
    print(f"[RETRIEVAL 5/8] Building cosine-similarity search: min_similarity>={RETRIEVAL_MIN_SIMILARITY} (max_distance<={max_distance:.4f}), filters: owner=user {user_id}, status=DONE" + (f", document_id={document_id}" if document_id is not None else "") + f", limit top {top_k}")

    stmt = (
        select(DocumentChunk, distance.label("distance"))
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(Document.user_id == user_id)
        .where(Document.status == JobStatus.DONE.value)
        .where(distance <= max_distance)
        .order_by(distance)
        .limit(top_k)
    )
    if document_id is not None:
        stmt = stmt.where(DocumentChunk.document_id == document_id)

    print(f"[RETRIEVAL 6/8] Executing vector search in DB (ranking chunks by cosine distance via <=> / HNSW index)")  # noqa: F541
    rows = (await db.execute(stmt)).all()
    print(f"[RETRIEVAL 7/8] Search returned {len(rows)} chunk(s) above the similarity threshold; mapping to scored results")
    logger.info(
        "Retrieval: user=%d doc=%s top_k=%d hits=%d",
        user_id,
        document_id,
        top_k,
        len(rows),
    )

    for rank, (chunk, dist) in enumerate(rows, start=1):
        print(f"[RETRIEVAL 7/8]   #{rank} score={round(1 - dist, 4)} document_id={chunk.document_id} chunk_index={chunk.chunk_index} page={chunk.page_number}")

    return [
        RetrievedChunk(
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            page_number=chunk.page_number,
            char_start=chunk.char_start,
            content=chunk.content,
            score=round(1 - dist, 4),
        )
        for chunk, dist in rows
    ]
