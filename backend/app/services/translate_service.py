"""
ClauseWise — Translation Service

Wraps the Google Cloud Translation API. Provides two functions:

  1. ``translate_text``           — translate a string to a target language
  2. ``list_supported_languages`` — return all supported language code/name pairs

Uses the lazy-client-singleton pattern from ``gemini_service.py`` /
``docai_service.py`` for consistency and testability.

Error Handling Contract:
  • Every Translation API call is wrapped in try/except.
  • On failure the function raises ``TranslateServiceError``.
  • The router catches this and returns a clean 502 error response.
"""

from __future__ import annotations

import logging

from google.cloud import translate_v2 as translate

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class TranslateServiceError(Exception):
    """Raised when the Cloud Translation API call fails."""


# ---------------------------------------------------------------------------
# Lazy client singleton
# ---------------------------------------------------------------------------

_client: translate.Client | None = None


def _get_client() -> translate.Client:
    """
    Return a lazily-initialized Translation API client.

    Uses an API key from the ``TRANSLATE_API_KEY`` environment variable.
    The client is created on first call and reused thereafter.

    Raises:
        TranslateServiceError: If the API key is not configured.
    """
    global _client
    if _client is None:
        if not settings.translate_api_key:
            raise TranslateServiceError(
                "TRANSLATE_API_KEY is not set. Add it to your .env file."
            )
        import google.auth.api_key
        creds = google.auth.api_key.Credentials(settings.translate_api_key)
        _client = translate.Client(credentials=creds)
    return _client


def reset_client() -> None:
    """Reset the cached client (useful in tests to inject a mock)."""
    global _client
    _client = None


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def translate_text(text: str, target_language: str) -> str:
    """
    Translate a string into the specified target language.

    Args:
        text: The source text to translate.
        target_language: An ISO 639-1 language code (e.g. ``"es"``, ``"fr"``).

    Returns:
        The translated text string.

    Raises:
        TranslateServiceError: On API failure or empty result.
    """
    client = _get_client()

    try:
        result = client.translate(text, target_language=target_language)
    except Exception as exc:
        raise TranslateServiceError(
            f"Translation API call failed: {exc}"
        ) from exc

    translated = result.get("translatedText", "")
    if not translated:
        raise TranslateServiceError(
            "Translation API returned an empty result."
        )

    logger.info(
        "Translation complete: target=%s, source_chars=%d, translated_chars=%d",
        target_language,
        len(text),
        len(translated),
    )

    return translated


def list_supported_languages() -> list[dict[str, str]]:
    """
    Return the list of languages supported by the Translation API.

    Each entry is a dict with ``language`` (ISO code) and ``name``
    (English display name), e.g. ``{"language": "es", "name": "Spanish"}``.

    Returns:
        A list of language dicts sorted by display name.

    Raises:
        TranslateServiceError: On API failure.
    """
    client = _get_client()

    try:
        languages = client.get_languages(target_language="en")
    except Exception as exc:
        raise TranslateServiceError(
            f"Failed to fetch supported languages: {exc}"
        ) from exc

    # Normalize to a consistent shape: {"language": code, "name": display_name}
    result = [
        {"language": lang["language"], "name": lang.get("name", lang["language"])}
        for lang in languages
    ]
    result.sort(key=lambda x: x["name"])

    logger.info("Fetched %d supported languages.", len(result))
    return result
