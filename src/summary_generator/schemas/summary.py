from typing import Literal
from pydantic import BaseModel


class SummaryRequest(BaseModel):
    text: str
    summary_format: Literal["bullet", "paragraph"] = "bullet"


class SummaryResponse(BaseModel):
    summary: list[str]
    source_type: str
