from pydantic import BaseModel


class DocumentTextRequest(BaseModel):
    text: str
    title: str | None = None


class DocumentResponse(BaseModel):
    document_id: int
    filename: str | None
    chunks_stored: int
