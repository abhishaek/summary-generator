import re
import magic

from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form, status

from summary_generator.dependencies import get_current_user
from summary_generator.parsers import extract_text
from summary_generator.schemas.summary import SummaryRequest, SummaryResponse
from summary_generator.services.gemini_service import summarize
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/summary",
    tags=["summary"],
    dependencies=[Depends(get_current_user)],
)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
SUPPORTED_MIME_TYPES = {"text/plain", "text/html", "application/pdf"}


def _parse_summary(result: str, summary_format: str) -> list[str]:
    if summary_format == "paragraph":
        return [result.strip()]
    points = re.findall(r'[•\-\*]\s+([\s\S]+?)(?=\n[•\-\*]|\Z)', result)
    points = [f"• {p.strip()}" for p in points if p.strip()]
    return points if points else [result.strip()]


@router.post("/v1/text", response_model=SummaryResponse, status_code=status.HTTP_200_OK)
async def summarize_text(request: SummaryRequest):
    if not request.text.strip():
        logger.warning("Rejected /summary/text: empty text body")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Text cannot be empty.")

    logger.info("Summary requested: source=text format=%s chars=%d", request.summary_format, len(request.text))
    result = await summarize(request.text, request.summary_format)
    logger.info("Summary completed: source=text format=%s", request.summary_format)
    return SummaryResponse(summary=_parse_summary(result, request.summary_format), source_type="text")


@router.post("/v1/file", response_model=SummaryResponse, status_code=status.HTTP_200_OK)
async def summarize_file(
    file: UploadFile,
    summary_format: str = Form(default="bullet"),
):
    if summary_format not in ("bullet", "paragraph"):
        logger.warning("Rejected /summary/file: invalid format=%s", summary_format)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="summary_format must be 'bullet' or 'paragraph'.")

    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE:
        logger.warning("Rejected /summary/file: file too large bytes=%d filename=%s", len(contents), file.filename)
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File size exceeds the 5 MB limit.")

    mime_type = magic.from_buffer(contents, mime=True)

    if mime_type not in SUPPORTED_MIME_TYPES:
        logger.warning("Rejected /summary/file: unsupported mime_type=%s filename=%s", mime_type, file.filename)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Supported types: .txt, .html, .pdf",
        )

    text = extract_text(contents, mime_type)

    if not text.strip():
        logger.warning("Rejected /summary/file: no readable text extracted filename=%s mime_type=%s", file.filename, mime_type)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No readable text found in the uploaded file.")

    logger.info("Summary requested: source=file format=%s mime_type=%s bytes=%d", summary_format, mime_type, len(contents))
    result = await summarize(text, summary_format)
    logger.info("Summary completed: source=file format=%s filename=%s", summary_format, file.filename)
    return SummaryResponse(summary=_parse_summary(result, summary_format), source_type="file")
