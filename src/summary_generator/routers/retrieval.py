import logging

from fastapi import APIRouter, Depends, status

from summary_generator.dependencies import (
    get_current_user,
    DbDependency,
    UserDependency,
)
from summary_generator.schemas.retrieval import RetrievalRequest, RetrievalResponse
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
    logger.info(
        "Retrieval requested: user=%d top_k=%d doc=%s",
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
    return RetrievalResponse(query=payload.query, results=results)
