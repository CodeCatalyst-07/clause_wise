"""
ClauseWise — Chat Router

Provides a conversational Q&A interface where users can ask follow-up
questions about their uploaded/analyzed legal documents.

  POST /chat — send a question with a document_id and chat history,
               receive a document-grounded answer from Gemini.

The chat is **stateless on the server** — the frontend sends the full
conversation history with each request. The only server-side state is the
document text in the ephemeral session store, which is referenced by
``document_id``.

Error handling:
  • Missing/expired document_id → 404 with a clear re-upload message.
  • Empty question              → 422 validation error (Pydantic).
  • Gemini API failure          → 502, same pattern as documents router.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.disclaimers import DISCLAIMER_TEXT
from app.core.error_sanitizer import sanitize_error
from app.core.rate_limiter import limiter
from app.core.session_store import get_session
from app.models.document_types import DocumentType
from app.models.responses import ErrorResponse
from app.services.gemini_service import GeminiServiceError, answer_question

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    """A single message in the conversation history."""

    role: str = Field(
        ..., description="Either 'user' or 'assistant'."
    )
    content: str = Field(
        ..., max_length=10_000,
        description="The message content. Maximum 10,000 characters.",
    )


class ChatRequest(BaseModel):
    """Request body for ``POST /chat``."""

    document_id: str = Field(
        ..., min_length=1, max_length=100,
        description="The document_id from a prior /documents/analyze or /documents/upload response.",
    )
    question: str = Field(
        ..., min_length=1, max_length=2_000,
        description="The user's follow-up question about the document. Maximum 2,000 characters.",
    )
    history: list[ChatMessage] = Field(
        default_factory=list, max_length=50,
        description="Prior conversation turns (max 50) for context continuity.",
    )


class ChatResponse(BaseModel):
    """Response body for ``POST /chat``."""

    answer: str = Field(
        description="The model's document-grounded answer."
    )
    disclaimer: str = Field(
        description="Legal disclaimer (always present in chat responses)."
    )


# ═══════════════════════════════════════════════════════════════════════════
# POST /chat
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "",
    response_model=ChatResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Document not found / expired"},
        502: {"model": ErrorResponse, "description": "Gemini API failure"},
    },
    summary="Ask a follow-up question about a document",
    description=(
        "Send a question about a previously analyzed document. The answer "
        "is grounded in the actual document text — the model will not "
        "fabricate clauses or provide legal advice."
    ),
)
@limiter.limit("30/minute")
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """
    Answer a follow-up question grounded in the analyzed document.

    Looks up the document text from the ephemeral session store using
    ``document_id``. If the session has expired or the ID is unknown,
    returns a clear 404 telling the user to re-upload.

    Args:
        request: Request body with ``document_id``, ``question``, and
            optional ``history``.

    Returns:
        ChatResponse with the answer and legal disclaimer.

    Raises:
        HTTPException 404: If the document session is missing or expired.
        HTTPException 502: If the Gemini API fails.
    """
    # ------------------------------------------------------------------
    # Look up the document in the session store.
    # ------------------------------------------------------------------
    session = get_session(body.document_id)
    if session is None:
        logger.warning(
            "Chat request with unknown/expired document_id: %s",
            body.document_id,
        )
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error="document_not_found",
                detail=(
                    "The document session has expired or was not found. "
                    "Please re-upload or re-analyze your document to start a new session."
                ),
                disclaimer=DISCLAIMER_TEXT,
            ).model_dump(),
        )

    # ------------------------------------------------------------------
    # Build the history list for the Gemini prompt.
    # ------------------------------------------------------------------
    history_dicts = [
        {"role": msg.role, "content": msg.content}
        for msg in body.history
    ]

    # ------------------------------------------------------------------
    # Get the answer from Gemini, grounded in the document text.
    # ------------------------------------------------------------------
    try:
        doc_type = DocumentType(session["doc_type"])
    except ValueError:
        doc_type = DocumentType.OTHER

    try:
        answer = answer_question(
            document_text=session["text"],
            doc_type=doc_type,
            question=body.question,
            chat_history=history_dicts,
        )
        return ChatResponse(answer=answer, disclaimer=DISCLAIMER_TEXT)
    except GeminiServiceError as exc:
        logger.error("Gemini service error during chat: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error="gemini_service_error",
                detail=sanitize_error(str(exc), service="gemini"),
                disclaimer=DISCLAIMER_TEXT,
            ).model_dump(),
        )
