import logging

from fastapi import APIRouter, Depends, status

from summary_generator.config import RETRIEVAL_MIN_SIMILARITY
from summary_generator.dependencies import (
    get_current_user,
    DbDependency,
    UserDependency,
)
from summary_generator.schemas.common import new_request
from summary_generator.schemas.retrieval import (
    RetrievalMetadata,
    RetrievalRequest,
    RetrievalResponse,
)
from summary_generator.services.gemini_service import answer_from_chunks
from summary_generator.services.retrieval_service import retrieve

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/retrieval",
    tags=["Retrieval"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/v1/search", response_model=RetrievalResponse, status_code=status.HTTP_200_OK)
async def search(
    payload: RetrievalRequest,
    db: DbDependency,
    current_user: UserDependency,
):
    """Semantic search over the caller's own document chunks.

    An empty corpus or no matches above the similarity threshold returns an empty
    `results` list (200), not an error. Ownership is enforced inside the service,
    so a caller can never retrieve another user's chunks even by passing a
    document_id they don't own.
    """
    request_id, started = new_request()

    print(f"[RETRIEVAL 1/8] Search request received: request_id={request_id} user_id={current_user['id']} query={payload.query!r} top_k={payload.top_k} document_id={payload.document_id}")
    logger.info(
        "Retrieval requested: request_id=%s user=%d top_k=%d doc=%s",
        request_id,
        current_user["id"],
        payload.top_k,
        payload.document_id,
    )
    results = await retrieve(
        db,
        user_id=current_user["id"],
        query=payload.query,
        top_k=payload.top_k,
        document_id=payload.document_id,
    )

    answer = None
    if payload.summarize:
        print(f"[RETRIEVAL 7b/8] Summarize requested: grounding answer in {len(results)} retrieved chunk(s) via Gemini")
        answer = await answer_from_chunks(payload.query, results)

    metadata = RetrievalMetadata.build(
        request_id,
        started,
        total_results=len(results),
        top_k=payload.top_k,
        document_id=payload.document_id,
        min_similarity=RETRIEVAL_MIN_SIMILARITY,
    )
    print(f"[RETRIEVAL 8/8] Returning {len(results)} result(s) to client: request_id={request_id} latency_ms={metadata.latency_ms}")
    return RetrievalResponse(query=payload.query, results=results, answer=answer, metadata=metadata)
