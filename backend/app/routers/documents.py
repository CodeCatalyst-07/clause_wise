"""
ClauseWise — Documents Router

Handles document analysis requests via two pathways:

  POST /documents/analyze  — accept raw text and run the full classification
                             → extraction → summarization pipeline.
                             (Phase 2.1 — kept for testing/demo convenience.)

  POST /documents/upload   — accept a multipart file upload (PDF, JPEG, PNG),
                             validate it, extract text via Document AI, then
                             feed into the same analysis pipeline.
                             (Phase 2.2.)

Both endpoints return the same ``AnalysisResult`` shape (including a
``document_id`` for follow-up chat), so the frontend can treat their
responses identically.

Session store:
  On success, both endpoints store the document text in the ephemeral
  in-memory session store (``core/session_store.py``) and return a
  ``document_id`` that the ``POST /chat`` endpoint can use to reference
  the document for follow-up questions. The text is intentionally kept
  only in memory, never written to disk — legal documents are sensitive.

Error handling:
  • File validation failures → 413 / 415 / 422 (client errors).
  • Document AI failures     → 502 (upstream error).
  • Gemini pipeline failures → 502 (upstream error).
  Each returns a structured ``ErrorResponse`` with the legal disclaimer.
"""

import logging

from fastapi import APIRouter, HTTPException, Request, UploadFile, File

from app.core.disclaimers import DISCLAIMER_TEXT
from app.core.error_sanitizer import sanitize_error
from app.core.rate_limiter import limiter
from app.core.session_store import create_session
from app.core.validators import FileValidationError, validate_file
from app.models.requests import AnalyzeRequest
from app.models.responses import AnalysisResult, ErrorResponse
from app.services.docai_service import DocAIServiceError, extract_text_from_document
from app.services.gemini_service import (
    GeminiServiceError,
    analyze_document,
    extract_text_multimodal,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


# ---------------------------------------------------------------------------
# Helper: build a consistent HTTPException from our service errors
# ---------------------------------------------------------------------------

def _raise_error(status_code: int, error_key: str, detail: str) -> None:
    """
    Raise an HTTPException with a structured ErrorResponse body.

    Centralizes error formatting so every failure path returns the same
    shape (including the legal disclaimer) and we don't repeat boilerplate.
    """
    raise HTTPException(
        status_code=status_code,
        detail=ErrorResponse(
            error=error_key,
            detail=sanitize_error(detail, service=error_key.replace("_service_error", "").replace("_error", "")),
            disclaimer=DISCLAIMER_TEXT,
        ).model_dump(),
    )


def _store_and_attach_id(result: AnalysisResult, text: str) -> AnalysisResult:
    """
    Store the document text in the session store and attach the generated
    ``document_id`` to the ``AnalysisResult`` before returning it.

    This enables the chat endpoint to look up the document for follow-up
    questions. The text is kept only in memory — never written to disk.
    """
    document_id = create_session(text, result.doc_type.value)
    result.document_id = document_id
    return result


# ═══════════════════════════════════════════════════════════════════════════
# POST /documents/analyze — raw text input (Phase 2.1)
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/analyze",
    response_model=AnalysisResult,
    responses={
        502: {"model": ErrorResponse, "description": "Gemini API failure"},
    },
    summary="Analyze a legal document (raw text)",
    description=(
        "Accepts raw document text and runs the full ClauseWise pipeline: "
        "classify document type → extract structured fields → generate "
        "plain-English summary. Returns a combined result with risk flags, "
        "the legal disclaimer, and a document_id for follow-up chat."
    ),
)
@limiter.limit("30/minute")
async def analyze(request: Request, body: AnalyzeRequest) -> AnalysisResult:
    """
    Run the full analysis pipeline on the provided document text.

    On success, stores the text in the ephemeral session store so the
    chat endpoint can reference it for follow-up questions.

    Args:
        request: Request body containing the document ``text``.

    Returns:
        AnalysisResult with document_id, doc_type, extracted fields,
        risk_flags, summary, and disclaimer.

    Raises:
        HTTPException 502: If the Gemini service encounters an error.
    """
    try:
        result = analyze_document(body.text)
        return _store_and_attach_id(result, body.text)
    except GeminiServiceError as exc:
        logger.error("Gemini service error during analysis: %s", exc)
        _raise_error(502, "gemini_service_error", str(exc))


# ═══════════════════════════════════════════════════════════════════════════
# POST /documents/upload — file upload (Phase 2.2)
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/upload",
    response_model=AnalysisResult,
    responses={
        413: {"model": ErrorResponse, "description": "File too large"},
        415: {"model": ErrorResponse, "description": "Unsupported file type"},
        422: {"model": ErrorResponse, "description": "Empty or invalid file"},
        502: {"model": ErrorResponse, "description": "Document AI or Gemini failure"},
    },
    summary="Upload and analyze a legal document",
    description=(
        "Accepts a PDF, JPEG, or PNG file via multipart upload. "
        "Validates the file by magic bytes (not extension), extracts text "
        "via Google Document AI OCR, then runs the full ClauseWise analysis "
        "pipeline. Returns the same AnalysisResult as /documents/analyze."
    ),
)
@limiter.limit("30/minute")
async def upload(request: Request, file: UploadFile = File(...)) -> AnalysisResult:
    """
    Upload a file, extract text via Document AI, and run the analysis pipeline.

    The file is processed **entirely in memory** — never written to persistent
    disk — because legal documents contain sensitive information (PII,
    financial terms). This is an intentional security safeguard.

    On success, stores the extracted text in the ephemeral session store so
    the chat endpoint can reference it for follow-up questions.

    Args:
        file: The uploaded file (multipart/form-data).

    Returns:
        AnalysisResult with document_id, doc_type, extracted fields,
        risk_flags, summary, and disclaimer.

    Raises:
        HTTPException: 413, 415, or 422 for validation failures;
            502 for Document AI or Gemini upstream failures.
    """
    # ------------------------------------------------------------------
    # Step 1: Read file bytes into memory.
    # We intentionally do NOT write to disk — legal documents are sensitive.
    # ------------------------------------------------------------------
    try:
        file_bytes = await file.read()
    finally:
        # Always close the upload handle, even on read errors.
        await file.close()

    # ------------------------------------------------------------------
    # Step 2: Validate the file (empty, size, magic-byte type check).
    # ------------------------------------------------------------------
    try:
        detected_mime = validate_file(file_bytes, file.filename or "unknown")
    except FileValidationError as exc:
        _raise_error(exc.status_code, "file_validation_error", exc.detail)

    # ------------------------------------------------------------------
    # Step 3: Extract text via Document AI (OCR) with resilient fallbacks.
    # If Document AI encounters auth, billing, or network failures,
    # gracefully fallback to local PDF extraction (pypdf) or Gemini multimodal OCR.
    # ------------------------------------------------------------------
    extracted_text = ""
    try:
        extracted_text = extract_text_from_document(file_bytes, detected_mime)
    except DocAIServiceError as exc:
        err_msg = str(exc).lower()
        if "no extractable text" in err_msg:
            # Document AI processed the document and confirmed it has no readable text
            _raise_error(502, "docai_service_error", str(exc))

        logger.warning(
            "Document AI extraction unavailable or failed (%s). Falling back...",
            exc,
        )
        if detected_mime == "application/pdf":
            try:
                import io
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(file_bytes))
                pages_text = [(p.extract_text() or "").strip() for p in reader.pages]
                extracted_text = "\n\n".join(t for t in pages_text if t).strip()
                if extracted_text:
                    logger.info("Extracted %d characters via local pypdf extraction", len(extracted_text))
            except Exception as pdf_err:
                logger.debug("Local pypdf extraction failed: %s", pdf_err)

        if len(extracted_text) < 20:
            try:
                extracted_text = extract_text_multimodal(file_bytes, detected_mime)
            except Exception as gemini_exc:
                logger.error("Gemini fallback OCR failed: %s", gemini_exc)
                _raise_error(502, "docai_service_error", str(exc))
    except Exception as exc:
        logger.warning("Unexpected error during document extraction: %s. Attempting fallback...", exc)
        if detected_mime == "application/pdf":
            try:
                import io
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(file_bytes))
                pages_text = [(p.extract_text() or "").strip() for p in reader.pages]
                extracted_text = "\n\n".join(t for t in pages_text if t).strip()
            except Exception:
                pass

        if len(extracted_text) < 20:
            try:
                extracted_text = extract_text_multimodal(file_bytes, detected_mime)
            except Exception:
                _raise_error(502, "docai_service_error", str(exc))

    # ------------------------------------------------------------------
    # Step 4: Feed extracted text into the Phase 2.1 Gemini pipeline.
    # ------------------------------------------------------------------
    try:
        result = analyze_document(extracted_text)
        return _store_and_attach_id(result, extracted_text)
    except GeminiServiceError as exc:
        logger.error("Gemini service error during upload analysis: %s", exc)
        _raise_error(502, "gemini_service_error", str(exc))
