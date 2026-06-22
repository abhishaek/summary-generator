from summary_generator.parsers import text, html, pdf, docx, markdown

DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MARKDOWN_MIME_TYPE = "text/markdown"


def extract_text(file_bytes: bytes, mime_type: str) -> str:
    if mime_type == "text/plain":
        return text.extract(file_bytes)
    elif mime_type == "text/html":
        return html.extract(file_bytes)
    elif mime_type == MARKDOWN_MIME_TYPE:
        return markdown.extract(file_bytes)
    elif mime_type == "application/pdf":
        return pdf.extract(file_bytes)
    elif mime_type == DOCX_MIME_TYPE:
        return docx.extract(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {mime_type}")


def extract_pages(file_bytes: bytes, mime_type: str) -> list[tuple[int, str]]:
    """Return (page_number, text) tuples. Only PDF has real pages; every other
    supported format is treated as a single page (page 1)."""
    if mime_type == "application/pdf":
        return pdf.extract_pages(file_bytes)
    return [(1, extract_text(file_bytes, mime_type))]
