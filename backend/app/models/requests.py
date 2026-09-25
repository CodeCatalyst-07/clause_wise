"""
ClauseWise — API Request Schemas

Pydantic models that validate incoming request payloads.

Input constraints:
  • ``text`` on /documents/analyze is capped at 500,000 characters (~500 KB).
    This prevents a user from sending a multi-megabyte text blob that would
    cost excessive Gemini tokens and slow the pipeline. File uploads already
    have a 10 MB size cap via validators.py — this is the text-input analog.
"""

from pydantic import BaseModel, Field


# 500,000 chars ≈ ~500 KB of UTF-8 text. Generous enough for a long legal
# document but prevents abuse from multi-megabyte payloads.
MAX_TEXT_LENGTH = 500_000


class AnalyzeRequest(BaseModel):
    """
    Request body for ``POST /documents/analyze``.

    Accepts raw document text. The ``text`` field must be non-empty and
    is capped at MAX_TEXT_LENGTH characters to prevent abuse.

    Attributes:
        text: The full plain-text content of the legal document to analyze.
    """

    text: str = Field(
        ...,
        min_length=1,
        max_length=MAX_TEXT_LENGTH,
        description=(
            "Full plain-text content of the legal document to analyze. "
            f"Maximum {MAX_TEXT_LENGTH:,} characters."
        ),
    )
