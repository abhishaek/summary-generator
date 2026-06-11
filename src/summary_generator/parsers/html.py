from summary_generator.shared.parserHelper import normalize
from bs4 import BeautifulSoup


def extract(file_bytes: bytes) -> str:
    soup = BeautifulSoup(file_bytes, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()  # removes the tag and its content
    text = soup.get_text(separator=" ")
    return normalize(text)  # same normalize helper as text.py
