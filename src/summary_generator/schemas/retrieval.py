from pydantic import BaseModel, Field
from summary_generator.config import RETRIEVAL_TOP_K, RETRIEVAL_MAX_TOP_K
from summary_generator.schemas.common import ResponseMetadata


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=RETRIEVAL_TOP_K, ge=1, le=RETRIEVAL_MAX_TOP_K)
    document_id: int | None = None
    summarize: bool = Field(
        default=True,
        description="When true (the default), also return a Gemini-generated "
        "`answer` grounded strictly in the retrieved chunks. Set to false for a "
        "plain, faster search with no LLM call.",
    )


class RetrievedChunk(BaseModel):
    document_id: int
    chunk_index: int
    page_number: int
    char_start: int
    content: str
    score: float  # cosine similarity in [-1, 1]; higher = closer


class RetrievalMetadata(ResponseMetadata):
    """Search envelope metadata: the standard fields plus search-specific ones so
    clients can trace, paginate, and reason about a result set without parsing
    the hits."""

    total_results: int = Field(description="Number of chunks returned in `results`.")
    top_k: int = Field(description="Max results requested by the caller.")
    document_id: int | None = Field(default=None, description="Document filter applied, if any.")
    min_similarity: float = Field(description="Similarity floor; hits below this were dropped.")


class RetrievalResponse(BaseModel):
    query: str
    results: list[RetrievedChunk]
    answer: str | None = Field(
        default=None,
        description="Grounded answer synthesized from `results`; populated only "
        "when the request set `summarize=true`.",
    )
    metadata: RetrievalMetadata
