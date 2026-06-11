from google.genai import errors as genai_errors
from fastapi import HTTPException

from summary_generator.config import GEMINI_MODEL, SUMMARY_MAX_TOKENS
from summary_generator.services.chunker import chunk_text
from summary_generator.shared.gemini_client import client


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


async def _call_gemini(prompt: str) -> str:
    try:
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={"max_output_tokens": SUMMARY_MAX_TOKENS},
        )
        return response.text
    except genai_errors.APIError as e:
        if hasattr(e, "code") and e.code == 429:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")
        if hasattr(e, "code") and e.code == 400:
            raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")
        raise HTTPException(status_code=500, detail="Gemini API error. Please try again.")
    except Exception:
        raise HTTPException(status_code=500, detail="Unexpected error while generating summary.")


async def summarize(text: str, summary_format: str) -> str:
    chunks = chunk_text(text)

    if len(chunks) == 1:
        prompt = _build_prompt(chunks[0], summary_format)
        return await _call_gemini(prompt)

    chunk_summaries = []
    for chunk in chunks:
        prompt = _build_prompt(chunk, summary_format)
        summary = await _call_gemini(prompt)
        chunk_summaries.append(summary)

    joined = "\n\n".join(chunk_summaries)
    reduce_prompt = _build_reduce_prompt(joined, summary_format)
    return await _call_gemini(reduce_prompt)
