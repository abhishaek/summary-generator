import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.getenv("DATABASE_URL")
SECRET_KEY: str = os.getenv(
    "SECRET_KEY", "f6a2e789bbc5abdb027d6d4c7326975b75d153371a6933a89cf352537b1d7e63"
)
ALGORITHM: str = "HS256"
TOKEN_EXPIRE_MINUTES: int = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

GEMINI_API_KEY: str = os.getenv("GOOGLE_GEMINI_API_KEY")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MAX_TOKENS_PER_CHUNK: int = 100_000
SUMMARY_MAX_TOKENS: int = 4_096

EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DIM: int = 384  # output dimension of all-MiniLM-L6-v2

# Retrieval chunks must stay well under the embedding model's 256-token input
# limit, otherwise text past the limit is truncated before it is embedded.
RETRIEVAL_CHUNK_TOKENS: int = 200
RETRIEVAL_CHUNK_OVERLAP_TOKENS: int = 40
RETRIEVAL_TOP_K: int = 5
RETRIEVAL_MAX_TOP_K: int = 40
# Cosine similarity is in [-1, 1] for normalized vectors; relevant MiniLM
# matches are typically ~0.3+. Drop anything below this as noise. Tune to taste.
RETRIEVAL_MIN_SIMILARITY: float = 0.2