from summary_generator.shared.parserHelper import normalize
from markdown import markdown as md_to_html
from bs4 import BeautifulSoup


def extract(file_bytes: bytes) -> str:
    text = file_bytes.decode("utf-8", errors="replace")
    # Render markdown to HTML, then strip tags so only the prose is embedded
    # (headings, emphasis, link syntax, code fences, etc. are removed).
    soup = BeautifulSoup(md_to_html(text), "html.parser")
    return normalize(soup.get_text(separator=" "))
