import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Response,
    UploadFile,
    status,
)

from summary_generator.dependencies import (
    get_current_user,
    DbDependency,
    UserDependency,
)
from summary_generator.models.document import Document
from summary_generator.schemas.document import DocumentResponse, DocumentTextRequest
from summary_generator.services.document_service import ingest_document, process_document
from summary_generator.shared.file_validation import validate_file

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
    dependencies=[Depends(get_current_user)],
)


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_document(
    file: UploadFile,
    db: DbDependency,
    current_user: UserDependency,
    background_tasks: BackgroundTasks,
):
    contents = await file.read()
    # Fast, cheap checks stay on the request path so bad uploads fail
    # immediately with 413/415 instead of being queued only to fail later.
    validate_file(contents, file.filename)

    document = Document(
        user_id=current_user["id"], filename=file.filename, status="pending"
    )
    db.add(document)
    await db.commit()

    # Hand the slow work (parse -> chunk -> embed -> store) to a background task
    # so this request returns now. The client polls GET /documents/{id} for status.
    background_tasks.add_task(process_document, document.id, contents, file.filename)

    logger.info("Document accepted: id=%d filename=%s", document.id, file.filename)
    return DocumentResponse(
        document_id=document.id,
        filename=document.filename,
        chunks_stored=0,
        status="pending",
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document_status(
    document_id: int,
    db: DbDependency,
    current_user: UserDependency,
):
    document = await db.get(Document, document_id)
    # 404 (not 403) when another user owns it, so we don't leak that it exists.
    if document is None or document.user_id != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found."
        )
    return DocumentResponse(
        document_id=document.id,
        filename=document.filename,
        chunks_stored=document.chunks_stored,
        status=document.status,
        error=document.error,
    )


@router.post(
    "/text", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED
)
async def create_document_from_text(
    payload: DocumentTextRequest,
    db: DbDependency,
    current_user: UserDependency,
    response: Response,
):
    if not payload.text.strip():
        logger.warning("Rejected /documents/text: empty text body")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Text cannot be empty."
        )

    # Raw text has no pages; treat the whole input as a single page.
    pages = [(1, payload.text)]

    logger.info(
        "Document ingest: source=text title=%s chars=%d",
        payload.title,
        len(payload.text),
    )
    document, chunks_stored, created = await ingest_document(
        db, current_user["id"], payload.title, pages
    )

    if not created:
        response.status_code = status.HTTP_200_OK

    return DocumentResponse(
        document_id=document.id, filename=document.filename, chunks_stored=chunks_stored
    )
