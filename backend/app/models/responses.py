"""
ClauseWise — API Response Schemas

Pydantic models for all outgoing API response payloads. These are what
the client receives after a successful (or failed) analysis pipeline run.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.models.document_types import DocumentType


class ExtractionResult(BaseModel):
    """
    Container for the type-specific structured data extracted from a
    legal document by the Gemini API.

    Attributes:
        fields: A dictionary whose keys and structure depend on the
            detected ``DocumentType``. See ``models/schemas.py`` for the
            schema definition per type.
        risk_flags: Plain-language flags highlighting clauses that are
            unusually one-sided, ambiguous, or otherwise merit attention.
    """

    fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Type-specific structured extraction (keys vary by document type).",
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="Plain-language risk flags for clauses that deserve attention.",
    )


class AnalysisResult(BaseModel):
    """
    Combined output of the full analysis pipeline:
    classify → extract → summarize.

    Every response carries the legal disclaimer to satisfy responsible-AI
    requirements. The disclaimer is injected by the orchestration layer,
    not by any individual sub-step.

    The ``document_id`` is a session key that the frontend passes to the
    ``POST /chat`` endpoint for follow-up questions. It references the
    document text stored in the ephemeral in-memory session store.

    Attributes:
        document_id: Session key for chat Q&A (UUID, may be None for
            responses that predate the session-store feature).
        doc_type: The classified document type.
        extracted: Structured extraction output with risk flags.
        summary: Plain-English document summary (8th-grade reading level).
        disclaimer: Legal disclaimer text (always present).
    """

    document_id: str | None = Field(
        default=None,
        description="Session key for follow-up chat questions (UUID).",
    )
    doc_type: DocumentType
    extracted: ExtractionResult
    summary: str
    suggested_questions: list[str] = Field(
        default_factory=list,
        description=(
            "2–4 questions the user could bring to a licensed attorney, "
            "generated from the document's risk flags. Helps users prepare "
            "for a legal consultation (problem-statement use case)."
        ),
    )
    disclaimer: str


class ErrorResponse(BaseModel):
    """
    Standardized error payload returned when the analysis pipeline fails
    (e.g. Gemini API timeout, malformed response, parsing error).

    Attributes:
        error: Machine-readable error category.
        detail: Human-readable explanation of what went wrong.
        disclaimer: Legal disclaimer (included even in error responses).
    """

    error: str
    detail: str
    disclaimer: str
