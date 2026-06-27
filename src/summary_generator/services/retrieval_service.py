import logging

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
    query_vec = await embed_query(query)

    distance = DocumentChunk.embedding.cosine_distance(query_vec)
    # For normalized vectors similarity = 1 - distance, so the min-similarity
    # threshold becomes a max-distance bound the DB can filter on directly.
    max_distance = 1 - RETRIEVAL_MIN_SIMILARITY

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

    rows = (await db.execute(stmt)).all()
    logger.info(
        "Retrieval: user=%d doc=%s top_k=%d hits=%d",
        user_id,
        document_id,
        top_k,
        len(rows),
    )

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
