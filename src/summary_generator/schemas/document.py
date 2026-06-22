from pydantic import BaseModel


class DocumentResponse(BaseModel):
    document_id: int
    filename: str | None
    chunks_stored: int
