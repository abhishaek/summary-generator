import logging
from google.genai import errors as genai_errors
from fastapi import HTTPException

from summary_generator.config import GEMINI_MODEL, SUMMARY_MAX_TOKENS
from summary_generator.schemas.retrieval import RetrievedChunk
from summary_generator.services.chunker import chunk_text
from summary_generator.shared.gemini_client import client

logger = logging.getLogger(__name__)


class EmptyModelOutput(HTTPException):
    """Raised when Gemini returns a response with no usable text — a safety
    block, a MAX_TOKENS finish that emitted nothing, or a recitation stop.

    It subclasses HTTPException so the summarize endpoints still render a proper
    HTTP error with no extra handling, while the search path can catch *this
    specific* case and degrade to a grounded "no information" reply — without
    also swallowing rate limits or genuine API errors into that fallback.
    """


def _format_instructions(summary_format: str) -> str:
    if summary_format == "bullet":
        return (
            "- Output exactly 5 bullet points.\n"
            "- Each bullet point must be between 100 and 150 words.\n"
            "- Each bullet point must cover a distinct key point from the text.\n"
            "- Start each bullet point with '• '.\n"
        )
    return (
        "- Output a single coherent paragraph.\n"
        "- The paragraph must not exceed 500 words.\n"
    )


def _build_prompt(text: str, summary_format: str) -> str:
    return (
        f"You are a summarization assistant.\n"
        f"Your task is to summarize ONLY the text provided below.\n"
        f"Strict rules:\n"
        f"- Use ONLY information explicitly stated in the provided text.\n"
        f"- Do NOT add facts, context, or knowledge from outside the text.\n"
        f"- Do NOT make assumptions or inferences beyond what is written.\n"
        f"- If something is not mentioned in the text, do not include it in the summary.\n"
        f"{_format_instructions(summary_format)}\n"
        f"Text:\n{text}"
    )


def _build_reduce_prompt(joined_summaries: str, summary_format: str) -> str:
    return (
        f"You are a summarization assistant.\n"
        f"Below are summaries of individual sections of a large document.\n"
        f"Your task is to combine them into one final coherent summary.\n"
        f"Strict rules:\n"
        f"- Use ONLY the information present in the section summaries below.\n"
        f"- Do NOT add facts, context, or knowledge from outside these summaries.\n"
        f"- Do NOT make assumptions or inferences beyond what is written.\n"
        f"- Do NOT repeat the same point multiple times across sections.\n"
        f"{_format_instructions(summary_format)}\n"
        f"Section summaries:\n{joined_summaries}"
    )


async def _call_gemini(prompt: str, temperature: float | None = None) -> str:
    logger.debug("Calling Gemini API: model=%s max_tokens=%d", GEMINI_MODEL, SUMMARY_MAX_TOKENS)
    config: dict = {"max_output_tokens": SUMMARY_MAX_TOKENS}
    if temperature is not None:
        config["temperature"] = temperature
    try:
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=config,
        )

        # response.text is None when the model emitted no text parts — e.g. a
        # safety block, a MAX_TOKENS finish with nothing emitted, or a recitation
        # stop. Returning that None upward would break callers that treat it as a
        # str far from the real cause, so surface it here where finish_reason is
        # still available. The check also catches "" (just as useless to callers).
        candidate = response.candidates[0] if response.candidates else None
        finish_reason = getattr(candidate, "finish_reason", None)

        if not response.text:
            logger.warning("Gemini returned no text (finish_reason=%s)", finish_reason)
            if str(finish_reason) == "FinishReason.MAX_TOKENS":
                raise EmptyModelOutput(
                    status_code=500,
                    detail="Summary was cut off (token limit). Try a shorter input.",
                )
            if str(finish_reason) == "FinishReason.SAFETY":
                raise EmptyModelOutput(
                    status_code=400,
                    detail="Content was blocked by the model's safety filters.",
                )
            raise EmptyModelOutput(
                status_code=500,
                detail="The model returned no usable output. Please try again.",
            )

        logger.debug("Gemini API call succeeded")
        return response.text
    except HTTPException:
        # Our own guard above (no-text/finish_reason) — let it pass through
        # untouched instead of being rewrapped into a generic 500 below.
        raise
    except genai_errors.APIError as e:
        if hasattr(e, "code") and e.code == 429:
            logger.warning("Gemini rate limit hit")
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")
        if hasattr(e, "code") and e.code == 400:
            logger.error("Gemini bad request: %s", str(e))
            raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")
        logger.error("Gemini API error: %s", str(e))
        raise HTTPException(status_code=500, detail="Gemini API error. Please try again.")
    except Exception as e:
        logger.error("Unexpected error calling Gemini: %s", str(e))
        raise HTTPException(status_code=500, detail="Unexpected error while generating summary.")


async def summarize(text: str, summary_format: str) -> str:
    chunks = chunk_text(text)

    if len(chunks) == 1:
        logger.debug("Single chunk: sending directly to Gemini")
        prompt = _build_prompt(chunks[0], summary_format)
        return await _call_gemini(prompt)

    logger.info("Large document: processing %d chunks then reducing", len(chunks))
    chunk_summaries = []
    for i, chunk in enumerate(chunks, 1):
        logger.debug("Summarizing chunk %d/%d", i, len(chunks))
        prompt = _build_prompt(chunk, summary_format)
        summary = await _call_gemini(prompt)
        chunk_summaries.append(summary)

    logger.debug("Reducing %d chunk summaries into final summary", len(chunk_summaries))
    joined = "\n\n".join(chunk_summaries)
    reduce_prompt = _build_reduce_prompt(joined, summary_format)
    return await _call_gemini(reduce_prompt)


# Exact reply when retrieval returns nothing or the chunks don't answer the
# query. Kept as a constant so the empty-retrieval short-circuit and the prompt
# instruction stay in sync.
NO_ANSWER = "The provided documents do not contain information to answer this."


def _build_rag_context(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into numbered, source-tagged blocks so the model
    can ground each claim and cite it as [Source N], and so a reader can trace a
    claim back to a specific document/chunk/page."""
    return "\n\n".join(
        f"[Source {i} | document={c.document_id} chunk={c.chunk_index} page={c.page_number}]\n{c.content}"
        for i, c in enumerate(chunks, start=1)
    )


def _build_rag_prompt(query: str, context: str) -> str:
    return (
        "You are a question-answering assistant working strictly from retrieved document excerpts.\n"
        "Strict rules:\n"
        "- Use ONLY information explicitly present in the numbered sources below.\n"
        "- Do NOT add facts, context, or knowledge from outside the sources.\n"
        "- Do NOT make assumptions or inferences beyond what is written.\n"
        "- Cite the sources you rely on inline as [Source N].\n"
        f'- If the sources do not contain the answer, reply EXACTLY: "{NO_ANSWER}"\n\n'
        f"Question:\n{query}\n\n"
        f"Sources:\n{context}"
    )


async def answer_from_chunks(query: str, chunks: list[RetrievedChunk]) -> str:
    """Produce a grounded answer to `query` using ONLY the retrieved `chunks`.

    Short-circuits when retrieval found nothing — sending Gemini an empty context
    is the main way it starts inventing answers — and uses temperature 0 to keep
    the output deterministic and tied to the provided text.
    """
    if not chunks:
        logger.info("RAG answer skipped: no chunks retrieved")
        return NO_ANSWER
    prompt = _build_rag_prompt(query, _build_rag_context(chunks))
    # For search, a model that produced no text should degrade to the same
    # "no information" reply rather than surface a 500 — gentler UX than the
    # summarize paths. Only the empty-output case falls back; rate limits and
    # genuine API errors (other HTTPExceptions) still propagate so the caller
    # learns the real, retryable cause instead of a misleading "no information".
    try:
        return await _call_gemini(prompt, temperature=0)
    except EmptyModelOutput:
        logger.info("RAG answer fell back to NO_ANSWER (model produced no text)")
        return NO_ANSWER
