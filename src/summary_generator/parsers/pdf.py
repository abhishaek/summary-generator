from summary_generator.shared.parserHelper import normalize
import io
from pypdf import PdfReader

def extract_pages(file_bytes: bytes) -> list[tuple[int, str]]:
    """Return (page_number, text) tuples, page numbers 1-indexed."""
    reader = PdfReader(io.BytesIO(file_bytes))
    return [(i, normalize(page.extract_text() or "")) for i, page in enumerate(reader.pages, start=1)]


def extract(file_bytes: bytes) -> str:
    return normalize("\n".join(text for _, text in extract_pages(file_bytes)))
