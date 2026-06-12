import hashlib
import secrets
import bcrypt
from datetime import datetime, timedelta, timezone
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from summary_generator.config import SECRET_KEY, ALGORITHM, TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS
from summary_generator.models import User, RefreshToken


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(username: str, user_id: int, role: str) -> str:
    payload = {
        "sub": username,
        "id": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def authenticate_user(username: str, password: str, db: AsyncSession):
    result = await db.execute(
        select(User).where(User.username == username, User.is_active)
    )
    user = result.scalar_one_or_none()
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


async def create_refresh_token(user_id: int, db: AsyncSession) -> str:
    raw = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    db.add(RefreshToken(user_id=user_id, token_hash=_hash_token(raw), expires_at=expires_at))
    await db.commit()
    return raw


async def verify_refresh_token(raw_token: str, db: AsyncSession):
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == _hash_token(raw_token),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    return result.scalar_one_or_none()


async def rotate_refresh_token(old_row: RefreshToken, db: AsyncSession) -> str:
    raw = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    await db.delete(old_row)
    db.add(RefreshToken(user_id=old_row.user_id, token_hash=_hash_token(raw), expires_at=expires_at))
    await db.commit()
    return raw
