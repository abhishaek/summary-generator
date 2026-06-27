from pydantic import BaseModel, Field
from summary_generator.config import RETRIEVAL_TOP_K, RETRIEVAL_MAX_TOP_K


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=RETRIEVAL_TOP_K, ge=1, le=RETRIEVAL_MAX_TOP_K)
    document_id: int | None = None


class RetrievedChunk(BaseModel):
    document_id: int
    chunk_index: int
    page_number: int
    char_start: int
    content: str
    score: float  # cosine similarity in [-1, 1]; higher = closer


class RetrievalResponse(BaseModel):
    query: str
    results: list[RetrievedChunk]
