import re

from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form, status

from summary_generator.dependencies import get_current_user
from summary_generator.schemas.summary import SummaryRequest, SummaryResponse
from summary_generator.services.gemini_service import summarize
from summary_generator.shared.file_validation import extract_document_text
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/summary",
    tags=["summary"],
    dependencies=[Depends(get_current_user)],
)


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
    text, mime_type = extract_document_text(contents, file.filename)

    logger.info("Summary requested: source=file format=%s mime_type=%s bytes=%d", summary_format, mime_type, len(contents))
    result = await summarize(text, summary_format)
    logger.info("Summary completed: source=file format=%s filename=%s", summary_format, file.filename)
    return SummaryResponse(summary=_parse_summary(result, summary_format), source_type="file")
