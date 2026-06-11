from summary_generator.shared.parserHelper import normalize

def extract(file_bytes: bytes) -> str:
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    return normalize(text)
