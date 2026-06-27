import logging
import magic

from fastapi import HTTPException, status

from summary_generator.parsers import extract_text, extract_pages, DOCX_MIME_TYPE, MARKDOWN_MIME_TYPE

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB
SUPPORTED_MIME_TYPES = {"text/plain", "text/html", "application/pdf", DOCX_MIME_TYPE, MARKDOWN_MIME_TYPE}
MARKDOWN_EXTENSIONS = (".md", ".markdown")


def validate_file(contents: bytes, filename: str | None) -> str:
    """Check size and type of an uploaded file. Returns the detected mime_type,
    or raises HTTPException (413/415)."""
    if len(contents) > MAX_FILE_SIZE:
        logger.warning("Rejected file: too large bytes=%d filename=%s", len(contents), filename)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds the 15 MB limit.",
        )

    mime_type = magic.from_buffer(contents, mime=True)

    # Markdown sniffs as text/plain; route by extension so its markup is parsed.
    if filename and filename.lower().endswith(MARKDOWN_EXTENSIONS) and mime_type == "text/plain":
        mime_type = MARKDOWN_MIME_TYPE

    if mime_type not in SUPPORTED_MIME_TYPES:
        logger.warning("Rejected file: unsupported mime_type=%s filename=%s", mime_type, filename)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Supported types: .txt, .md, .html, .pdf, .docx",
        )

    return mime_type


def extract_document_text(contents: bytes, filename: str | None = None) -> tuple[str, str]:
    """Validate an uploaded file, then extract its text as a single string.

    Returns a (text, mime_type) tuple. Raises HTTPException (413/415/400).
    """
    mime_type = validate_file(contents, filename)
    text = extract_text(contents, mime_type)

    if not text.strip():
        logger.warning("Rejected file: no readable text filename=%s mime_type=%s", filename, mime_type)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No readable text found in the uploaded file.",
        )

    return text, mime_type


def extract_document_pages(contents: bytes, filename: str | None = None) -> tuple[list[tuple[int, str]], str]:
    """Validate an uploaded file, then extract its text per page.

    Returns a (pages, mime_type) tuple where pages is a list of
    (page_number, text); empty pages are dropped. Raises HTTPException (413/415/400).
    """
    mime_type = validate_file(contents, filename)
    print(f"[PARSE] Extracting pages from file: filename={filename} mime_type={mime_type}")
    pages = [(num, text) for num, text in extract_pages(contents, mime_type) if text.strip()]
    total_chars = sum(len(text) for _, text in pages)
    print(f"[PARSE] Extracted {len(pages)} non-empty page(s), total_chars={total_chars}, filename={filename}")

    if not pages:
        logger.warning("Rejected file: no readable text filename=%s mime_type=%s", filename, mime_type)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No readable text found in the uploaded file.",
        )

    return pages, mime_type
