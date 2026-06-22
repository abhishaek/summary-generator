from summary_generator.shared.parserHelper import normalize
import io
from docx import Document


def extract(file_bytes: bytes) -> str:
    document = Document(io.BytesIO(file_bytes))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    return normalize(text)
