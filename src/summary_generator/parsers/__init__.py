from summary_generator.parsers import text, html, pdf, docx

DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def extract_text(file_bytes: bytes, mime_type: str) -> str:
    if mime_type == "text/plain":
        return text.extract(file_bytes)
    elif mime_type == "text/html":
        return html.extract(file_bytes)
    elif mime_type == "application/pdf":
        return pdf.extract(file_bytes)
    elif mime_type == DOCX_MIME_TYPE:
        return docx.extract(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {mime_type}")
