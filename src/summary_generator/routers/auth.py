import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from summary_generator.dependencies import DbDependency, UserDependency
from summary_generator.limiter import limiter
from summary_generator.models import User
from summary_generator.schemas.auth import CreateUserRequest, RefreshRequest, UserResponse, Token
from summary_generator.services.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    hash_password,
    rotate_refresh_token,
    verify_refresh_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/v1/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit("3/minute")
async def register_user(request: Request, payload: CreateUserRequest, db: DbDependency):
    existing = await db.execute(
        select(User).where(
            (User.email == payload.email) | (User.username == payload.username)
        )
    )
    if existing.scalar_one_or_none():
        logger.warning("Duplicate registration attempt: email=%s username=%s", payload.email, payload.username)
        raise HTTPException(status_code=400, detail="Email or username already exists")

    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("User registered: username=%s role=%s", user.username, user.role)
    return user


@router.post("/v1/login", response_model=Token, status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def login(request: Request, db: DbDependency, form_data: OAuth2PasswordRequestForm = Depends()):
    user = await authenticate_user(form_data.username, form_data.password, db)
    if not user:
        logger.warning("Failed login attempt: username=%s", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    access_token = create_access_token(user.username, user.id, user.role)
    refresh_token = await create_refresh_token(user.id, db)
    logger.info("User logged in: username=%s", user.username)
    return {"access_token": access_token, "token_type": "bearer", "refresh_token": refresh_token}


@router.post("/v1/refresh", response_model=Token, status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def refresh(request: Request, payload: RefreshRequest, db: DbDependency):
    token_row = await verify_refresh_token(payload.refresh_token, db)
    if not token_row:
        logger.warning("Invalid or expired refresh token used")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )
    result = await db.execute(select(User).where(User.id == token_row.user_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("Refresh token references missing user_id=%s", token_row.user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )
    new_refresh = await rotate_refresh_token(token_row, db)
    new_access = create_access_token(user.username, user.id, user.role)
    logger.info("Token refreshed: username=%s", user.username)
    return {"access_token": new_access, "token_type": "bearer", "refresh_token": new_refresh}


@router.post("/v1/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, db: DbDependency, _: UserDependency):
    token_row = await verify_refresh_token(payload.refresh_token, db)
    if token_row:
        await db.delete(token_row)
        await db.commit()
    logger.info("User logged out")
