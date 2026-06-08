import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.getenv("DATABASE_URL")
SECRET_KEY: str = os.getenv("SECRET_KEY", "f6a2e789bbc5abdb027d6d4c7326975b75d153371a6933a89cf352537b1d7e63")
ALGORITHM: str = "HS256"
TOKEN_EXPIRE_MINUTES: int = 24 * 60
