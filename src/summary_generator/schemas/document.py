from pydantic import BaseModel

from summary_generator.schemas.common import ResponseMetadata


class DocumentTextRequest(BaseModel):
    text: str
    title: str | None = None


class DocumentResponse(BaseModel):
    document_id: int
    filename: str | None
    chunks_stored: int
    status: str = "pending"
    error: str | None = None
    metadata: ResponseMetadata
