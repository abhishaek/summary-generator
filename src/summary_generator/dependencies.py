import logging
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError, ExpiredSignatureError
from sqlalchemy.ext.asyncio import AsyncSession

from summary_generator.config import SECRET_KEY, ALGORITHM
from summary_generator.database import get_db

logger = logging.getLogger(__name__)

oauth2_bearer = OAuth2PasswordBearer(tokenUrl="auth/v1/login")

DbDependency = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(token: str = Depends(oauth2_bearer)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: int = payload.get("id")
        role: str = payload.get("role")
        if username is None or user_id is None:
            logger.warning("Token missing required claims: sub or id absent")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials.")
        return {"username": username, "id": user_id, "role": role}
    except ExpiredSignatureError:
        logger.warning("Expired token used")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired. Please log in again.")
    except JWTError:
        logger.warning("Invalid token: signature or format error")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials.")


UserDependency = Annotated[dict, Depends(get_current_user)]
