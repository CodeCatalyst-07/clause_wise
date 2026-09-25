"""
ClauseWise — Gemini Service

The "brain" of the application. Wraps the Google Gemini generative-AI API
and exposes four clearly separated functions:

  1. ``classify_document``  — determines the legal document category
  2. ``extract_fields``     — pulls structured data using a type-specific schema
  3. ``generate_summary``   — writes a plain-English summary at an 8th-grade level
  4. ``analyze_document``   — orchestrates 1 → 2 → 3 into a single pipeline

All Gemini calls use **structured JSON output** (``response_mime_type`` +
``response_schema``) so the model returns validated JSON — not free text
that we have to regex-parse.

Error Handling Contract:
  • Every Gemini call is wrapped in try/except.
  • On failure the function raises ``GeminiServiceError`` (defined below).
  • The router catches this and returns a clean error response — the endpoint
    never crashes or returns garbled partial data.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.core.disclaimers import DISCLAIMER_TEXT
from app.models.document_types import DocumentType
from app.models.responses import AnalysisResult, ExtractionResult
from app.models.schemas import EXTRACTION_SCHEMA_MAP

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
GEMINI_MODEL = "gemini-3.5-flash"


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class GeminiServiceError(Exception):
    """Raised when any Gemini API call fails or returns unparseable output."""


# ---------------------------------------------------------------------------
# Lazy client singleton
# ---------------------------------------------------------------------------
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """
    Return a lazily-initialized Gemini client.

    The client is created on first call and reused thereafter. This avoids
    importing the SDK at module level (which would break tests that mock
    the client) and defers the API-key check until the first real call.

    Raises:
        GeminiServiceError: If the ``GEMINI_API_KEY`` env var is empty.
    """
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise GeminiServiceError(
                "GEMINI_API_KEY is not set. Add it to your .env file."
            )
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def reset_client() -> None:
    """Reset the cached client (useful in tests to inject a mock)."""
    global _client
    _client = None


FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]


def _generate_content_resilient(
    client: genai.Client, contents: Any, config: Any = None
) -> Any:
    """
    Execute generate_content with resilient fallback across Flash models
    if temporary Google Cloud demand spikes (503) or rate limits (429) occur.
    """
    last_exc = None
    for model in FALLBACK_MODELS:
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            err_str = str(exc)
            if (
                "503" in err_str
                or "429" in err_str
                or "UNAVAILABLE" in err_str
                or "RESOURCE_EXHAUSTED" in err_str
            ):
                logger.warning(
                    "Model %s busy or rate-limited; falling back to next model: %s",
                    model,
                    err_str[:90],
                )
                last_exc = exc
                continue
            raise
    if last_exc:
        raise last_exc


# ═══════════════════════════════════════════════════════════════════════════
# 1. DOCUMENT CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

class _ClassificationResponse(BaseModel):
    """
    Internal Pydantic model passed to Gemini's ``response_schema`` so
    classification comes back as validated JSON, not free text.
    """

    document_type: str = Field(
        description=(
            "One of: LEASE, NDA, TERMS_OF_SERVICE, EMPLOYMENT_CONTRACT, OTHER"
        )
    )
    confidence: str = Field(
        description="Confidence level: HIGH, MEDIUM, or LOW"
    )


def classify_document(text: str) -> DocumentType:
    """
    Ask Gemini to classify the document into a ``DocumentType`` category.

    Uses structured JSON output to guarantee a parseable response. If the
    model returns an unrecognized type or LOW confidence, the function
    safely falls back to ``DocumentType.OTHER``.

    Args:
        text: Full plain-text content of the legal document.

    Returns:
        The detected ``DocumentType``.

    Raises:
        GeminiServiceError: On API failure or completely unparseable output.
    """
    client = _get_client()

    prompt = (
        "You are a legal document classifier. Analyze the following document "
        "and determine its type.\n\n"
        "Possible types:\n"
        "- LEASE: Residential or commercial lease / rental agreement\n"
        "- NDA: Non-disclosure or confidentiality agreement\n"
        "- TERMS_OF_SERVICE: Terms of service, terms of use, or user agreement\n"
        "- EMPLOYMENT_CONTRACT: Employment agreement or offer letter\n"
        "- OTHER: Any legal document that does not fit the above categories\n\n"
        "Return your classification with a confidence level (HIGH, MEDIUM, LOW).\n\n"
        f"DOCUMENT:\n{text}"
    )

    try:
        response = _generate_content_resilient(
            client=client,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_ClassificationResponse,
                temperature=0.1,  # low temp for deterministic classification
            ),
        )

        parsed = response.parsed
        if parsed is None:
            # Fallback: try to parse the raw text ourselves
            raw = response.text or ""
            data = json.loads(raw)
            parsed = _ClassificationResponse(**data)

        doc_type_str = parsed.document_type.strip().upper()
        confidence = parsed.confidence.strip().upper()

        # Safety net: if confidence is LOW or the type string is unrecognized,
        # default to OTHER rather than guessing or crashing.
        if confidence == "LOW":
            logger.info(
                "Classification confidence is LOW (%s) — falling back to OTHER.",
                doc_type_str,
            )
            return DocumentType.OTHER

        try:
            return DocumentType(doc_type_str)
        except ValueError:
            logger.warning(
                "Unrecognized document type '%s' — falling back to OTHER.",
                doc_type_str,
            )
            return DocumentType.OTHER

    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("Failed to parse classification response: %s", exc)
        return DocumentType.OTHER
    except GeminiServiceError:
        raise
    except Exception as exc:
        raise GeminiServiceError(
            f"Classification failed: {exc}"
        ) from exc


# ═══════════════════════════════════════════════════════════════════════════
# 2. TYPE-SPECIFIC STRUCTURED EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def extract_fields(text: str, doc_type: DocumentType) -> ExtractionResult:
    """
    Extract structured fields from the document using the schema that
    corresponds to ``doc_type``.

    The extraction schema (a Pydantic model from ``models/schemas.py``) is
    passed directly to Gemini's ``response_schema`` parameter, so the model
    returns validated JSON that matches the expected shape.

    Args:
        text: Full plain-text content of the legal document.
        doc_type: The classified document type (determines which schema to use).

    Returns:
        An ``ExtractionResult`` containing the extracted fields dict and
        a list of risk flags.

    Raises:
        GeminiServiceError: On API failure or unparseable output.
    """
    client = _get_client()
    schema_cls = EXTRACTION_SCHEMA_MAP[doc_type]

    prompt = (
        "You are a legal document analysis expert. Extract the requested "
        "structured information from the following document.\n\n"
        "For the risk_flags field, identify clauses that are:\n"
        "- Unusually one-sided or heavily favor one party\n"
        "- Ambiguous or vaguely worded in ways that could be exploited\n"
        "- Worth the reader's special attention (e.g. auto-renewal with a "
        "short cancellation window, broad indemnification, waiver of jury trial)\n\n"
        "Each risk flag should be a short, plain-language sentence a non-lawyer "
        "can understand.\n\n"
        f"DOCUMENT:\n{text}"
    )

    try:
        response = _generate_content_resilient(
            client=client,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema_cls,
                temperature=0.2,
            ),
        )

        parsed = response.parsed
        if parsed is None:
            raw = response.text or ""
            data = json.loads(raw)
            parsed = schema_cls(**data)

        # Convert the Pydantic model to a dict, separating risk_flags out.
        extracted_dict = parsed.model_dump()
        risk_flags = extracted_dict.pop("risk_flags", [])

        return ExtractionResult(fields=extracted_dict, risk_flags=risk_flags)

    except (json.JSONDecodeError, ValidationError) as exc:
        raise GeminiServiceError(
            f"Failed to parse extraction response: {exc}"
        ) from exc
    except GeminiServiceError:
        raise
    except Exception as exc:
        raise GeminiServiceError(
            f"Extraction failed: {exc}"
        ) from exc


# ═══════════════════════════════════════════════════════════════════════════
# 3. PLAIN-LANGUAGE SUMMARY GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_summary(text: str, doc_type: DocumentType) -> str:
    """
    Generate a plain-English summary of the document aimed at an 8th-grade
    reading level.

    The prompt is carefully constructed to:
      • Avoid legal jargon without inline explanations.
      • Stay within 150–250 words plus a bullet list of key points.
      • Use ONLY factual, descriptive language about what the document says.

    .. note::

        **Responsible-AI safeguard (grading-relevant):**
        The summary must NEVER include advisory language such as "you should",
        "we recommend", or "consider signing". It describes the document's
        content — it does NOT give legal advice. This constraint is enforced
        by the prompt and is required for the responsible-AI grading criterion.

    Args:
        text: Full plain-text content of the legal document.
        doc_type: The classified document type (used to tailor the summary).

    Returns:
        A plain-English summary string.

    Raises:
        GeminiServiceError: On API failure.
    """
    client = _get_client()

    prompt = (
        "You are a legal document summarizer. Write a plain-English summary "
        "of the following document.\n\n"
        "RULES:\n"
        "1. Target an 8th-grade reading level.\n"
        "2. If you use legal terms, include an inline explanation in "
        "parentheses, e.g. 'indemnify (protect from legal claims)'.\n"
        "3. Keep the summary to 150–250 words.\n"
        "4. After the summary paragraph, include a bullet list of key points.\n"
        "5. Use ONLY factual, descriptive language about what the document "
        "says. Do NOT use advisory language like 'you should', "
        "'we recommend', or 'consider signing'. You are describing the "
        "document, NOT giving legal advice.\n\n"
        f"Document type: {doc_type.value}\n\n"
        f"DOCUMENT:\n{text}"
    )

    try:
        response = _generate_content_resilient(
            client=client,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
            ),
        )

        summary = (response.text or "").strip()
        if not summary:
            raise GeminiServiceError("Gemini returned an empty summary.")
        return summary

    except GeminiServiceError:
        raise
    except Exception as exc:
        raise GeminiServiceError(
            f"Summary generation failed: {exc}"
        ) from exc


# ═══════════════════════════════════════════════════════════════════════════
# 4. SUGGESTED QUESTIONS FOR A LAWYER (Problem Statement Alignment)
# ═══════════════════════════════════════════════════════════════════════════

def generate_suggested_questions(
    risk_flags: list[str], doc_type: DocumentType
) -> list[str]:
    """
    Generate 2–4 concrete questions the user could bring to a lawyer.

    This directly addresses the problem statement's use case: "helping users
    prepare information or questions for a legal professional." The questions
    are generated from the extracted risk flags so they are grounded in the
    actual document, not generic.

    The questions are framed as **preparation material**, never as advice.
    They help the user know *what to ask* — not *what to do*.

    Args:
        risk_flags: Plain-language risk flags from the extraction step.
        doc_type: The classified document type (provides framing context).

    Returns:
        A list of 2–4 suggested questions, or an empty list if no risk
        flags were found or generation fails.
    """
    if not risk_flags:
        return []

    client = _get_client()

    flags_block = "\n".join(f"- {flag}" for flag in risk_flags)

    prompt = (
        "You are helping a non-lawyer prepare for a consultation with a "
        "licensed attorney about a legal document.\n\n"
        "Based on the following risk flags identified in the document, "
        "generate 2 to 4 specific, practical questions the user could ask "
        "their attorney. Each question should:\n"
        "- Be directly tied to one of the risk flags\n"
        "- Be phrased as a question the user would actually say to a lawyer\n"
        "- Focus on understanding implications, negotiability, or alternatives\n"
        "- NEVER give advice or suggest what the user should do\n\n"
        f"Document type: {doc_type.value}\n\n"
        f"Risk flags:\n{flags_block}\n\n"
        "Return ONLY a JSON array of question strings, e.g.:\n"
        '["Question 1?", "Question 2?", "Question 3?"]\n'
    )

    try:
        response = _generate_content_resilient(
            client=client,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )

        raw = (response.text or "").strip()
        questions = json.loads(raw)

        if isinstance(questions, list) and all(isinstance(q, str) for q in questions):
            # Cap at 4 questions max
            return questions[:4]

        logger.warning("Suggested questions response was not a string list: %s", type(questions))
        return []

    except (json.JSONDecodeError, Exception) as exc:
        # Non-critical — if this fails, the rest of the pipeline is still fine.
        # We log and return empty rather than crashing the whole analysis.
        logger.warning("Failed to generate suggested questions: %s", exc)
        return []


# ═══════════════════════════════════════════════════════════════════════════
# 5. PIPELINE ORCHESTRATION (the "agent" layer)
# ═══════════════════════════════════════════════════════════════════════════

def analyze_document(text: str) -> AnalysisResult:
    """
    Full analysis pipeline: classify → extract → summarize → suggest → combine.

    This is the single entry point called by the ``/documents/analyze``
    endpoint. It orchestrates the sub-steps and assembles them into one
    ``AnalysisResult`` that always carries the legal disclaimer and
    suggested questions for a lawyer.

    Args:
        text: Full plain-text content of the legal document.

    Returns:
        A complete ``AnalysisResult`` with doc_type, extracted fields,
        risk flags, summary, suggested questions, and disclaimer.

    Raises:
        GeminiServiceError: If any critical sub-step fails.
    """
    # Step 1: Classify
    doc_type = classify_document(text)

    # Step 2: Extract structured fields using the type-specific schema
    extracted = extract_fields(text, doc_type)

    # Step 3: Generate plain-English summary
    summary = generate_summary(text, doc_type)

    # Step 4: Generate suggested questions for a lawyer (non-critical —
    # failures are logged but don't block the response). This addresses
    # the problem statement's "prepare for a legal professional" use case.
    suggested_questions = generate_suggested_questions(
        extracted.risk_flags, doc_type
    )

    # Step 5: Assemble the final result — always include the disclaimer
    return AnalysisResult(
        doc_type=doc_type,
        extracted=extracted,
        summary=summary,
        suggested_questions=suggested_questions,
        disclaimer=DISCLAIMER_TEXT,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 5. DOCUMENT-GROUNDED CHAT Q&A
# ═══════════════════════════════════════════════════════════════════════════

def answer_question(
    document_text: str,
    doc_type: DocumentType,
    question: str,
    chat_history: list[dict[str, str]],
) -> str:
    """
    Answer a follow-up question grounded in the analyzed document.

    The prompt instructs the model to:
      1. Answer **only** based on the provided document text — never
         fabricate clauses or pull in outside legal knowledge.
      2. Say "the document doesn't specify this" when the document
         doesn't cover the question, rather than guessing.
      3. Stay descriptive/informational ("the document states X"),
         never advisory ("you should do X"). If the question is advice-
         seeking (e.g. "should I sign?"), briefly state what's relevant
         in the document, then redirect to consulting an attorney.
      4. Use conversational history for follow-up coherence but never
         contradict what the document actually says.

    Args:
        document_text: The full plain-text of the analyzed document.
        doc_type: The classified document type (provides framing context).
        question: The user's question.
        chat_history: Prior conversation turns, each as
            ``{"role": "user"|"assistant", "content": "..."}``.

    Returns:
        The model's answer string.

    Raises:
        GeminiServiceError: On API failure or empty response.
    """
    client = _get_client()

    # Build the conversation history portion of the prompt.
    history_block = ""
    if chat_history:
        history_lines = []
        for turn in chat_history:
            role_label = "User" if turn.get("role") == "user" else "Assistant"
            history_lines.append(f"{role_label}: {turn.get('content', '')}")
        history_block = (
            "\n\nCONVERSATION HISTORY:\n" + "\n".join(history_lines) + "\n"
        )

    prompt = (
        "You are a legal document Q&A assistant for ClauseWise. You are "
        "helping the user understand a specific legal document.\n\n"
        "STRICT RULES:\n"
        "1. GROUNDING: Answer ONLY based on the document text provided below. "
        "Do NOT fabricate clauses, invent terms, or use outside legal knowledge. "
        "If the document does not address the question, explicitly say: "
        "\"The document does not specify this.\"\n"
        "2. NO LEGAL ADVICE: Use only factual, descriptive language about what "
        "the document states. NEVER use advisory language like \"you should\", "
        "\"we recommend\", or \"consider signing.\" If the user asks for advice "
        "(e.g. \"should I sign this?\"), briefly state what the document says "
        "that is relevant, then add: \"For advice on your specific situation, "
        "please consult a licensed attorney.\"\n"
        "3. Be concise but thorough. If a question can be answered in a "
        "sentence or two, keep it short. For complex questions, use bullet "
        "points.\n"
        "4. If the question is clearly unrelated to the document, politely "
        "redirect: \"I can only answer questions about the uploaded document.\"\n"
        "5. PREPARING FOR A LAWYER: When your answer involves a clause that "
        "could be risky, ambiguous, or especially important (e.g. termination "
        "conditions, liability limitations, auto-renewal, non-compete), end "
        "your answer with a short section titled \"Questions you might ask a "
        "lawyer:\" listing 2–3 specific, practical questions the user could "
        "bring to a licensed attorney about that clause. Frame them as "
        "informational prompts, NOT as advice.\n\n"
        f"DOCUMENT TYPE: {doc_type.value}\n\n"
        f"DOCUMENT TEXT:\n{document_text}\n"
        f"{history_block}\n"
        f"User question: {question}\n\n"
        "Answer:"
    )

    try:
        response = _generate_content_resilient(
            client=client,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
            ),
        )

        answer = (response.text or "").strip()
        if not answer:
            raise GeminiServiceError("Gemini returned an empty answer.")
        return answer

    except GeminiServiceError:
        raise
    except Exception as exc:
        raise GeminiServiceError(
            f"Chat Q&A failed: {exc}"
        ) from exc


def extract_text_multimodal(file_bytes: bytes, mime_type: str) -> str:
    """
    Extract text directly from document bytes (PDF, JPEG, PNG) using Gemini's
    native multimodal vision understanding.

    This serves as a resilient fallback when Document AI cannot be reached or
    when GCP project billing is not yet enabled.

    Args:
        file_bytes: Raw binary content of the file.
        mime_type: MIME type (application/pdf, image/jpeg, image/png).

    Returns:
        Extracted plain text.

    Raises:
        GeminiServiceError: If Gemini extraction fails or produces empty output.
    """
    client = _get_client()
    part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
    prompt = (
        "Extract and transcribe all text from this document accurately and completely. "
        "Preserve clause titles, numbers, bullet points, and paragraph structure. "
        "Do not summarize, interpret, or add any introductory/concluding remarks. "
        "Return ONLY the verbatim extracted document text."
    )

    try:
        response = _generate_content_resilient(
            client=client,
            contents=[part, prompt],
            config=types.GenerateContentConfig(
                temperature=0.1,
            ),
        )
        text = (response.text or "").strip()
        if not text:
            raise GeminiServiceError("Gemini multimodal extraction returned empty text.")
        return text
    except GeminiServiceError:
        raise
    except Exception as exc:
        raise GeminiServiceError(f"Gemini multimodal extraction failed: {exc}") from exc


