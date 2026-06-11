from summary_generator.shared.parserHelper import normalize
import io
from pypdf import PdfReader

def extract(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(pages)
    return normalize(text)
