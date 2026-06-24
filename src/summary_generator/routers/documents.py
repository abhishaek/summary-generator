import logging

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status

from summary_generator.dependencies import get_current_user, DbDependency, UserDependency
from summary_generator.schemas.document import DocumentResponse, DocumentTextRequest
from summary_generator.services.document_service import ingest_document
from summary_generator.shared.file_validation import extract_document_pages

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
    dependencies=[Depends(get_current_user)],
)


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    file: UploadFile,
    db: DbDependency,
    current_user: UserDependency,
    response: Response,
):
    contents = await file.read()
    pages, mime_type = extract_document_pages(contents, file.filename)

    logger.info("Document ingest: source=file filename=%s mime_type=%s pages=%d", file.filename, mime_type, len(pages))
    document, chunks_stored, created = await ingest_document(db, current_user["id"], file.filename, pages)

    if not created:
        response.status_code = status.HTTP_200_OK

    return DocumentResponse(
        document_id=document.id, filename=document.filename, chunks_stored=chunks_stored
    )


@router.post("/text", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document_from_text(
    payload: DocumentTextRequest,
    db: DbDependency,
    current_user: UserDependency,
    response: Response,
):
    if not payload.text.strip():
        logger.warning("Rejected /documents/text: empty text body")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Text cannot be empty.")

    # Raw text has no pages; treat the whole input as a single page.
    pages = [(1, payload.text)]

    logger.info("Document ingest: source=text title=%s chars=%d", payload.title, len(payload.text))
    document, chunks_stored, created = await ingest_document(db, current_user["id"], payload.title, pages)

    if not created:
        response.status_code = status.HTTP_200_OK

    return DocumentResponse(
        document_id=document.id, filename=document.filename, chunks_stored=chunks_stored
    )
