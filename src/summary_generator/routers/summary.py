import mimetypes
import re

from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form, status

from summary_generator.dependencies import get_current_user
from summary_generator.parsers import extract_text
from summary_generator.schemas.summary import SummaryRequest, SummaryResponse
from summary_generator.services.gemini_service import summarize

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


@router.post("/text", response_model=SummaryResponse, status_code=status.HTTP_200_OK)
async def summarize_text(request: SummaryRequest):
    if not request.text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Text cannot be empty.")

    result = await summarize(request.text, request.summary_format)
    return SummaryResponse(summary=_parse_summary(result, request.summary_format), source_type="text")


@router.post("/file", response_model=SummaryResponse, status_code=status.HTTP_200_OK)
async def summarize_file(
    file: UploadFile,
    summary_format: str = Form(default="bullet"),
):
    if summary_format not in ("bullet", "paragraph"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="summary_format must be 'bullet' or 'paragraph'.")

    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File size exceeds the 5 MB limit.")

    mime_type, _ = mimetypes.guess_type(file.filename)

    if mime_type not in SUPPORTED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Supported types: .txt, .html, .pdf",
        )

    text = extract_text(contents, mime_type)

    if not text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No readable text found in the uploaded file.")

    result = await summarize(text, summary_format)
    return SummaryResponse(summary=_parse_summary(result, summary_format), source_type="file")
