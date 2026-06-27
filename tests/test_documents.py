import pytest

from summary_generator.dependencies import get_current_user
from summary_generator.main import app
from summary_generator.models.document import Document, JobStatus
from summary_generator.models.user import User
from summary_generator.schemas.common import ResponseMetadata, new_request
from summary_generator.schemas.retrieval import RetrievalMetadata
from tests.conftest import TestSessionLocal


# --- Unit tests: the shared metadata envelope -------------------------------

def test_new_request_returns_id_and_start():
    request_id, started = new_request()
    assert isinstance(request_id, str) and request_id
    assert isinstance(started, float)


def test_response_metadata_build_populates_required_fields():
    request_id, started = new_request()
    md = ResponseMetadata.build(request_id, started)
    assert md.request_id == request_id
    assert md.latency_ms >= 0
    # timestamp must be timezone-aware (UTC), not naive.
    assert md.timestamp.tzinfo is not None


def test_retrieval_metadata_build_includes_search_fields():
    request_id, started = new_request()
    md = RetrievalMetadata.build(
        request_id, started, total_results=3, top_k=5, document_id=7, min_similarity=0.2
    )
    # search-specific fields
    assert md.total_results == 3
    assert md.top_k == 5
    assert md.document_id == 7
    assert md.min_similarity == 0.2
    # inherited base fields still present
    assert md.request_id == request_id
    assert md.latency_ms >= 0
    assert md.timestamp.tzinfo is not None


# --- Integration test: the envelope is wired into a real response -----------

@pytest.fixture
async def owned_document():
    """Insert a user + their DONE document, and make get_current_user return
    that user so the documents router authorizes the request."""
    async with TestSessionLocal() as session:
        user = User(
            email="docowner@example.com",
            username="docowner",
            hashed_password="x",
            role="user",
        )
        session.add(user)
        await session.commit()

        document = Document(
            user_id=user.id,
            filename="report.pdf",
            content_hash="hash-doc-meta",
            status=JobStatus.DONE.value,
            chunks_stored=42,
        )
        session.add(document)
        await session.commit()

        user_dict = {"id": user.id, "username": user.username, "role": user.role}
        document_id = document.id

    app.dependency_overrides[get_current_user] = lambda: user_dict
    yield document_id
    app.dependency_overrides.pop(get_current_user, None)


async def test_get_document_status_includes_metadata_envelope(client, owned_document):
    response = await client.get(f"/documents/{owned_document}")

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == owned_document
    assert data["chunks_stored"] == 42
    assert data["status"] == "done"

    metadata = data["metadata"]
    assert {"request_id", "latency_ms", "timestamp"} <= metadata.keys()
    assert metadata["latency_ms"] >= 0
    assert metadata["request_id"]
