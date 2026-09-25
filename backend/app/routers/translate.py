"""
ClauseWise — Translation Router

Exposes endpoints for multilingual text translation:

  POST /translate           — translate text to a target language
  GET  /translate/languages — list all supported languages for the frontend dropdown

Both endpoints use the Cloud Translation API via ``translate_service.py``.

Security:
  • POST /translate is rate-limited (30 req/min per IP).
  • Text input is capped at 50,000 characters.
  • target_language is validated against the actual supported-languages list
    before being sent to the Translation API.
  • Error messages are sanitized before reaching the client.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.disclaimers import DISCLAIMER_TEXT
from app.core.error_sanitizer import sanitize_error
from app.core.rate_limiter import limiter
from app.models.responses import ErrorResponse
from app.services.translate_service import (
    TranslateServiceError,
    translate_text,
    list_supported_languages,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/translate", tags=["translate"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

# Max text length for translation — 50,000 chars is generous for a summary
# or risk-flag block but prevents abuse from multi-megabyte payloads.
MAX_TRANSLATE_TEXT_LENGTH = 50_000


class TranslateRequest(BaseModel):
    """Request body for ``POST /translate``."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=MAX_TRANSLATE_TEXT_LENGTH,
        description=f"The text to translate. Maximum {MAX_TRANSLATE_TEXT_LENGTH:,} characters.",
    )
    target_language: str = Field(
        ..., min_length=2, max_length=10,
        description="ISO 639-1 language code (e.g. 'es', 'fr', 'zh').",
    )


class TranslateResponse(BaseModel):
    """Response body for ``POST /translate``."""

    translated_text: str = Field(
        description="The translated text in the target language."
    )


class LanguageEntry(BaseModel):
    """A single supported language entry."""

    language: str = Field(description="ISO 639-1 language code.")
    name: str = Field(description="English display name of the language.")


# ---------------------------------------------------------------------------
# Language code validation cache
# ---------------------------------------------------------------------------
_supported_codes_cache: set[str] | None = None


def _get_supported_codes() -> set[str]:
    """
    Return the set of supported language codes, lazily cached.

    This ensures that ``target_language`` is validated against the actual
    Translation API's language list — not just a format check.
    """
    global _supported_codes_cache
    if _supported_codes_cache is None:
        try:
            languages = list_supported_languages()
            _supported_codes_cache = {lang["language"] for lang in languages}
        except TranslateServiceError:
            # If we can't fetch the list, skip client-side validation
            # and let the API reject bad codes directly.
            return set()
    return _supported_codes_cache


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "",
    response_model=TranslateResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Invalid input or unsupported language"},
        429: {"description": "Rate limit exceeded"},
        502: {"model": ErrorResponse, "description": "Translation API failure"},
    },
    summary="Translate text to a target language",
    description=(
        "Translates the provided text into the specified target language "
        "using the Google Cloud Translation API."
    ),
)
@limiter.limit("30/minute")
async def translate(request: Request, body: TranslateRequest) -> TranslateResponse:
    """
    Translate text to a target language.

    Validates the target_language against the supported-languages list
    before making an API call — rejects unsupported codes early with a
    clear error instead of letting them fail inside the Translation API.

    Args:
        request: FastAPI Request object (required by SlowAPI rate limiter).
        body: Request body with ``text`` and ``target_language``.

    Returns:
        TranslateResponse with the translated text.

    Raises:
        HTTPException 422: If the target language code is unsupported.
        HTTPException 502: If the Translation API fails.
    """
    # Validate target_language against the actual supported list.
    supported = _get_supported_codes()
    if supported and body.target_language not in supported:
        raise HTTPException(
            status_code=422,
            detail=ErrorResponse(
                error="unsupported_language",
                detail=(
                    f"Language code '{body.target_language}' is not supported. "
                    "Use GET /translate/languages for the full list."
                ),
                disclaimer=DISCLAIMER_TEXT,
            ).model_dump(),
        )

    try:
        translated = translate_text(body.text, body.target_language)
        return TranslateResponse(translated_text=translated)
    except TranslateServiceError as exc:
        logger.error("Translation service error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error="translate_service_error",
                detail=sanitize_error(str(exc), service="translate"),
                disclaimer=DISCLAIMER_TEXT,
            ).model_dump(),
        )


@router.get(
    "/languages",
    response_model=list[LanguageEntry],
    responses={
        502: {"model": ErrorResponse, "description": "Translation API failure"},
    },
    summary="List supported languages",
    description=(
        "Returns all languages supported by the Translation API, "
        "each with an ISO code and English display name."
    ),
)
async def get_languages() -> list[LanguageEntry]:
    """
    Return supported languages for the frontend dropdown.

    Not rate-limited — read-only, no external API cost per call (cached).

    Returns:
        A sorted list of ``LanguageEntry`` objects.

    Raises:
        HTTPException 502: If the Translation API fails.
    """
    try:
        languages = list_supported_languages()
        return [LanguageEntry(**lang) for lang in languages]
    except TranslateServiceError as exc:
        logger.error("Translation service error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error="translate_service_error",
                detail=sanitize_error(str(exc), service="translate"),
                disclaimer=DISCLAIMER_TEXT,
            ).model_dump(),
        )
