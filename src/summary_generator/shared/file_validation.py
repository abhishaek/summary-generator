import logging
import magic

from fastapi import HTTPException, status

from summary_generator.parsers import extract_text, DOCX_MIME_TYPE

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
SUPPORTED_MIME_TYPES = {"text/plain", "text/html", "application/pdf", DOCX_MIME_TYPE}


def extract_document_text(contents: bytes, filename: str | None = None) -> tuple[str, str]:
    """Validate an uploaded file's size and type, then extract its text.

    Returns a (text, mime_type) tuple. Raises HTTPException (413/415/400) when
    the file is too large, an unsupported type, or contains no readable text.
    """
    if len(contents) > MAX_FILE_SIZE:
        logger.warning("Rejected file: too large bytes=%d filename=%s", len(contents), filename)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds the 5 MB limit.",
        )

    mime_type = magic.from_buffer(contents, mime=True)

    if mime_type not in SUPPORTED_MIME_TYPES:
        logger.warning("Rejected file: unsupported mime_type=%s filename=%s", mime_type, filename)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Supported types: .txt, .html, .pdf, .docx",
        )

    text = extract_text(contents, mime_type)

    if not text.strip():
        logger.warning("Rejected file: no readable text filename=%s mime_type=%s", filename, mime_type)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No readable text found in the uploaded file.",
        )

    return text, mime_type
