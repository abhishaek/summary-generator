from unittest.mock import AsyncMock

import pytest

from summary_generator.dependencies import get_current_user
from summary_generator.main import app
from summary_generator.models.document import Document, DocumentChunk, JobStatus
from summary_generator.models.user import User
from summary_generator.schemas.retrieval import RetrievedChunk
from summary_generator.services import gemini_service
from summary_generator.services.embedder import embed_chunks
from summary_generator.services.gemini_service import (
    NO_ANSWER,
    _build_rag_context,
    answer_from_chunks,
)
from tests.conftest import TestSessionLocal


def _chunk(document_id=12, chunk_index=3, page_number=4, content="refunds within 30 days", score=0.91):
    return RetrievedChunk(
        document_id=document_id,
        chunk_index=chunk_index,
        page_number=page_number,
        char_start=0,
        content=content,
        score=score,
    )


# --- Unit: context builder --------------------------------------------------

def test_build_rag_context_is_numbered_and_source_tagged():
    context = _build_rag_context([
        _chunk(document_id=12, chunk_index=3, page_number=4, content="alpha"),
        _chunk(document_id=12, chunk_index=7, page_number=5, content="beta"),
    ])
    # Numbered 1..N and each block carries traceable document/chunk/page tags.
    assert "[Source 1 | document=12 chunk=3 page=4]" in context
    assert "[Source 2 | document=12 chunk=7 page=5]" in context
    assert "alpha" in context and "beta" in context


# --- Unit: answer_from_chunks ----------------------------------------------

async def test_answer_from_chunks_empty_short_circuits(monkeypatch):
    """Empty retrieval must NOT reach Gemini — it returns the fixed no-answer
    reply directly (the main hallucination guard)."""
    spy = AsyncMock()
    monkeypatch.setattr(gemini_service, "_call_gemini", spy)

    result = await answer_from_chunks("anything", [])

    assert result == NO_ANSWER
    spy.assert_not_awaited()


async def test_answer_from_chunks_grounds_prompt_and_uses_temperature_zero(monkeypatch):
    spy = AsyncMock(return_value="Refunds are allowed within 30 days [Source 1].")
    monkeypatch.setattr(gemini_service, "_call_gemini", spy)

    chunks = [_chunk(content="Customers may request a refund within 30 days.")]
    result = await answer_from_chunks("what is the refund policy?", chunks)

    assert result == "Refunds are allowed within 30 days [Source 1]."
    spy.assert_awaited_once()
    prompt = spy.await_args.args[0]
    # The chunk content, a citable source tag, and the query are all in-prompt.
    assert "Customers may request a refund within 30 days." in prompt
    assert "[Source 1" in prompt
    assert "what is the refund policy?" in prompt
    # Deterministic, grounded generation.
    assert spy.await_args.kwargs["temperature"] == 0


async def test_answer_from_chunks_falls_back_to_no_answer_on_empty_model_output(monkeypatch):
    """If the model produced no usable text, _call_gemini raises EmptyModelOutput;
    the search path degrades to NO_ANSWER rather than surfacing a 500."""
    from summary_generator.services.gemini_service import EmptyModelOutput

    monkeypatch.setattr(
        gemini_service,
        "_call_gemini",
        AsyncMock(side_effect=EmptyModelOutput(status_code=500, detail="no usable output")),
    )

    result = await answer_from_chunks("anything", [_chunk()])

    assert result == NO_ANSWER


async def test_answer_from_chunks_propagates_rate_limit(monkeypatch):
    """A genuine API error (e.g. 429) must NOT be swallowed into NO_ANSWER — the
    caller needs to learn the real, retryable cause."""
    from fastapi import HTTPException

    monkeypatch.setattr(
        gemini_service,
        "_call_gemini",
        AsyncMock(side_effect=HTTPException(status_code=429, detail="Rate limit exceeded.")),
    )

    with pytest.raises(HTTPException) as exc:
        await answer_from_chunks("anything", [_chunk()])
    assert exc.value.status_code == 429


async def test_answer_from_chunks_passes_through_no_answer(monkeypatch):
    """Off-topic query: Gemini, told to refuse, returns the no-answer string and
    the service surfaces it unchanged."""
    monkeypatch.setattr(gemini_service, "_call_gemini", AsyncMock(return_value=NO_ANSWER))

    result = await answer_from_chunks("unrelated question", [_chunk(content="weather data")])

    assert result == NO_ANSWER


# --- Integration: the summarize flag is wired into /v1/search ---------------

@pytest.fixture
def fake_user():
    user_dict = {"id": 1, "username": "rag-user", "role": "user"}
    app.dependency_overrides[get_current_user] = lambda: user_dict
    yield user_dict
    app.dependency_overrides.pop(get_current_user, None)


async def test_search_with_summarize_false_returns_no_answer_and_skips_gemini(client, fake_user, monkeypatch):
    monkeypatch.setattr(
        "summary_generator.routers.retrieval.retrieve",
        AsyncMock(return_value=[_chunk()]),
    )
    gemini_spy = AsyncMock()
    monkeypatch.setattr("summary_generator.routers.retrieval.answer_from_chunks", gemini_spy)

    # Summary is on by default, so opting out must be explicit.
    response = await client.post(
        "/retrieval/v1/search",
        json={"query": "refund policy", "summarize": False},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] is None
    assert len(data["results"]) == 1
    gemini_spy.assert_not_awaited()


async def test_search_summarizes_by_default(client, fake_user, monkeypatch):
    monkeypatch.setattr(
        "summary_generator.routers.retrieval.retrieve",
        AsyncMock(return_value=[_chunk()]),
    )
    monkeypatch.setattr(
        "summary_generator.routers.retrieval.answer_from_chunks",
        AsyncMock(return_value="Refunds within 30 days [Source 1]."),
    )

    # No summarize flag sent -> defaults to true.
    response = await client.post("/retrieval/v1/search", json={"query": "refund policy"})

    assert response.status_code == 200
    assert response.json()["answer"] == "Refunds within 30 days [Source 1]."


async def test_search_with_summarize_returns_grounded_answer(client, fake_user, monkeypatch):
    monkeypatch.setattr(
        "summary_generator.routers.retrieval.retrieve",
        AsyncMock(return_value=[_chunk()]),
    )
    monkeypatch.setattr(
        "summary_generator.routers.retrieval.answer_from_chunks",
        AsyncMock(return_value="Refunds within 30 days [Source 1]."),
    )

    response = await client.post(
        "/retrieval/v1/search",
        json={"query": "refund policy", "summarize": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Refunds within 30 days [Source 1]."
    # Sources are still returned alongside the answer for verifiability.
    assert len(data["results"]) == 1


# --- End-to-end: real embedding + real vector search, only Gemini mocked -----

@pytest.fixture
async def seeded_corpus():
    """Insert a user + DONE document + one chunk embedded with the REAL model, so
    the retrieval path (query embedding -> pgvector cosine search) runs for real.
    Authorizes requests as that user."""
    content = "Customers may request a refund within 30 days of purchase."
    [vector] = await embed_chunks([content])

    async with TestSessionLocal() as session:
        user = User(
            email="ragowner@example.com",
            username="ragowner",
            hashed_password="x",
            role="user",
        )
        session.add(user)
        await session.commit()

        document = Document(
            user_id=user.id,
            filename="policy.pdf",
            content_hash="hash-rag-e2e",
            status=JobStatus.DONE.value,
            chunks_stored=1,
        )
        session.add(document)
        await session.commit()

        session.add(DocumentChunk(
            document_id=document.id,
            chunk_index=0,
            page_number=1,
            char_start=0,
            content=content,
            embedding=vector,
        ))
        await session.commit()

        user_dict = {"id": user.id, "username": user.username, "role": user.role}

    app.dependency_overrides[get_current_user] = lambda: user_dict
    yield {"content": content}
    app.dependency_overrides.pop(get_current_user, None)


async def test_end_to_end_search_summarize_grounds_on_real_retrieval(client, seeded_corpus, monkeypatch):
    # Only the Gemini network call is stubbed; retrieval and prompt-building are real.
    gemini_spy = AsyncMock(return_value="Refunds are allowed within 30 days [Source 1].")
    monkeypatch.setattr(gemini_service, "_call_gemini", gemini_spy)

    response = await client.post(
        "/retrieval/v1/search",
        json={"query": "what is the refund policy?", "summarize": True},
    )

    assert response.status_code == 200
    data = response.json()
    # Real vector search surfaced the seeded chunk...
    assert len(data["results"]) == 1
    assert data["results"][0]["content"] == seeded_corpus["content"]
    # ...and the grounded answer flowed back.
    assert data["answer"] == "Refunds are allowed within 30 days [Source 1]."

    # The actually-retrieved chunk reached Gemini's prompt at temperature 0 —
    # proving the answer is grounded in real retrieval, not invented.
    prompt = gemini_spy.await_args.args[0]
    assert seeded_corpus["content"] in prompt
    assert gemini_spy.await_args.kwargs["temperature"] == 0


async def test_search_unknown_document_id_404s_before_any_expensive_work(client, seeded_corpus, monkeypatch):
    """A document_id the user doesn't own must 404 fast — without embedding the
    query or calling Gemini."""
    embed_spy = AsyncMock()
    gemini_spy = AsyncMock()
    monkeypatch.setattr("summary_generator.services.retrieval_service.embed_query", embed_spy)
    monkeypatch.setattr(gemini_service, "_call_gemini", gemini_spy)

    response = await client.post(
        "/retrieval/v1/search",
        json={"query": "anything", "document_id": 999999},
    )

    assert response.status_code == 404
    # The whole point: neither the embedder nor Gemini ran.
    embed_spy.assert_not_awaited()
    gemini_spy.assert_not_awaited()
