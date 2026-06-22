import logging

from fastapi import APIRouter, Depends, UploadFile, status

from summary_generator.dependencies import get_current_user, DbDependency, UserDependency
from summary_generator.models.document import Document, DocumentChunk
from summary_generator.schemas.document import DocumentResponse
from summary_generator.services.chunker import chunk_text
from summary_generator.services.embedder import embed_chunks
from summary_generator.shared.file_validation import extract_document_text

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    dependencies=[Depends(get_current_user)],
)


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    file: UploadFile,
    db: DbDependency,
    current_user: UserDependency,
):
    contents = await file.read()
    text, mime_type = extract_document_text(contents, file.filename)

    chunks = chunk_text(text)
    embeddings = await embed_chunks(chunks)

    logger.info(
        "Document ingest: filename=%s mime_type=%s chunks=%d",
        file.filename, mime_type, len(chunks),
    )

    document = Document(user_id=current_user["id"], filename=file.filename)
    document.chunks = [
        DocumentChunk(chunk_index=i, content=chunk, embedding=embedding)
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]

    db.add(document)
    await db.commit()
    await db.refresh(document)

    logger.info("Document stored: id=%d chunks=%d filename=%s", document.id, len(chunks), file.filename)
    return DocumentResponse(document_id=document.id, filename=document.filename, chunks_stored=len(chunks))
