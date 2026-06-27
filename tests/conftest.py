import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from summary_generator.main import app
from summary_generator.database import Base, get_db
from summary_generator.limiter import limiter

# Disable rate limiting in tests: the limiter keys on client IP and all tests
# share one, so its 3/minute cap would otherwise leak across tests and 429 the
# later ones depending on run order.
limiter.enabled = False

TEST_DATABASE_URL = "postgresql+asyncpg://summary_user:summary123@localhost:5432/summary_test_db"

test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
TestSessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True, scope="session")
async def setup_test_db():
    async with test_engine.begin() as conn:
        # DocumentChunk uses pgvector's VECTOR type, so the extension must exist
        # before create_all or table creation fails. Try to provision it; if the
        # test role lacks superuser (CREATE EXTENSION needs it), assume it was
        # pre-created out-of-band and continue. See README for the one-time setup.
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except ProgrammingError:
            pass
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
async def clean_tables():
    yield
    async with TestSessionLocal() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
