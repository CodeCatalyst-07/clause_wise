"""
ClauseWise — Security Hardening Tests (Phase 2.5)

Tests specifically for the security hardening pass:

  (a) Rate limiter returns 429 when limit is exceeded
  (b) Oversized /documents/analyze text payload is rejected with 422
  (c) Unsupported target_language code is rejected before reaching the API
  (d) Error sanitizer strips internal details from error messages
  (e) Session store uses UUID4 (non-sequential, non-guessable)
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.error_sanitizer import sanitize_error
from app.core import session_store
from app.main import app
from app.models.requests import MAX_TEXT_LENGTH
from app.services import gemini_service

client = TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# (a) Rate limiter returns 429
# ═══════════════════════════════════════════════════════════════════════════

class TestRateLimiting:
    """Rate limiting on paid-API endpoints."""

    @patch("app.routers.documents.analyze_document")
    def test_rate_limit_returns_429_on_analyze(self, mock_analyze):
        """
        Exceeding the per-IP rate limit on /documents/analyze should
        return 429 with a structured error message.

        We fire requests in a tight loop. The limiter is set to 30/min
        so we send 35 requests — at least one should trigger 429.
        """
        from app.models.responses import AnalysisResult, ExtractionResult
        from app.models.document_types import DocumentType
        mock_analyze.return_value = AnalysisResult(
            doc_type=DocumentType.OTHER,
            confidence="LOW",
            summary="mock summary",
            extracted=ExtractionResult(fields={}, risk_flags=[]),
            suggested_questions=[],
            disclaimer="disclaimer",
        )

        got_429 = False
        for _ in range(35):
            response = client.post(
                "/documents/analyze",
                json={"text": "x"},  # min_length=1 is satisfied
            )
            if response.status_code == 429:
                got_429 = True
                data = response.json()
                assert data["error"] == "rate_limit_exceeded"
                assert "too many requests" in data["detail"].lower()
                break

        assert got_429, "Expected a 429 response after exceeding rate limit"

    @patch("app.routers.chat.answer_question")
    def test_rate_limit_returns_429_on_chat(self, mock_answer):
        """Rate limiting also applies to /chat."""
        mock_answer.return_value = "mock answer"
        session_store.clear_all()
        doc_id = session_store.create_session("Some text", "LEASE")

        got_429 = False
        for _ in range(35):
            response = client.post(
                "/chat",
                json={
                    "document_id": doc_id,
                    "question": "test",
                    "history": [],
                },
            )
            if response.status_code == 429:
                got_429 = True
                break

        assert got_429, "Expected a 429 response after exceeding rate limit"


# ═══════════════════════════════════════════════════════════════════════════
# (b) Oversized /documents/analyze text rejected
# ═══════════════════════════════════════════════════════════════════════════

class TestOversizedTextPayload:
    """Text payloads exceeding MAX_TEXT_LENGTH are rejected."""

    def test_oversized_text_returns_422(self):
        """
        Sending a text longer than MAX_TEXT_LENGTH to /documents/analyze
        should return 422 validation error (Pydantic max_length).
        """
        oversized_text = "x" * (MAX_TEXT_LENGTH + 1)
        response = client.post(
            "/documents/analyze",
            json={"text": oversized_text},
        )
        assert response.status_code == 422

    def test_text_at_max_length_is_accepted(self):
        """
        A text exactly at MAX_TEXT_LENGTH should be accepted (if the backend
        is reachable — will fail at the Gemini call, not validation).
        """
        max_text = "x" * MAX_TEXT_LENGTH
        # This will hit 502 (no Gemini key) but NOT 422 — proving validation passes.
        response = client.post(
            "/documents/analyze",
            json={"text": max_text},
        )
        # Either 200 (with mock) or 502 (no API key) — but NOT 422.
        assert response.status_code != 422


# ═══════════════════════════════════════════════════════════════════════════
# (c) Unsupported target_language rejected before API call
# ═══════════════════════════════════════════════════════════════════════════

class TestLanguageValidation:
    """Unsupported language codes are caught at the router level."""

    @patch("app.routers.translate._get_supported_codes")
    def test_unsupported_language_returns_422(self, mock_codes):
        """
        An unsupported language code should return 422 with a clear
        message referencing /translate/languages, NOT a 502 from the API.
        """
        mock_codes.return_value = {"es", "fr", "de", "zh"}

        response = client.post(
            "/translate",
            json={"text": "Hello", "target_language": "xyz"},
        )

        assert response.status_code == 422
        data = response.json()["detail"]
        assert data["error"] == "unsupported_language"
        assert "xyz" in data["detail"]
        assert "/translate/languages" in data["detail"]

    @patch("app.routers.translate._get_supported_codes")
    @patch("app.services.translate_service._get_client")
    def test_supported_language_passes_validation(self, mock_client, mock_codes):
        """A supported language code should pass validation and reach the API."""
        mock_codes.return_value = {"es", "fr", "de"}

        mock_translate_client = MagicMock()
        mock_client.return_value = mock_translate_client
        mock_translate_client.translate.return_value = {
            "translatedText": "Hola"
        }

        response = client.post(
            "/translate",
            json={"text": "Hello", "target_language": "es"},
        )

        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# (d) Error sanitizer
# ═══════════════════════════════════════════════════════════════════════════

class TestErrorSanitizer:
    """Error messages with internal details are sanitized."""

    def test_file_path_is_stripped(self):
        """Messages containing file paths are replaced with a fallback."""
        msg = "Error at /Users/arnav/Desktop/ClauseWise/backend/app/services/gemini_service.py:42"
        result = sanitize_error(msg, service="gemini")
        assert "/Users/" not in result
        assert "gemini_service.py" not in result

    def test_stack_trace_is_stripped(self):
        """Messages containing stack traces are replaced."""
        msg = 'Traceback (most recent call last):\n  File "/app/main.py"'
        result = sanitize_error(msg, service="default")
        assert "Traceback" not in result

    def test_api_key_fragment_is_stripped(self):
        """Messages containing API key patterns are replaced."""
        msg = "Invalid API key: AIzaSyABCDEF1234567890abcdefghij"
        result = sanitize_error(msg, service="gemini")
        assert "AIza" not in result

    def test_clean_message_passes_through(self):
        """Messages without internal details are returned unchanged."""
        msg = "GEMINI_API_KEY is not set. Add it to your .env file."
        result = sanitize_error(msg, service="gemini")
        assert result == msg


# ═══════════════════════════════════════════════════════════════════════════
# (e) Session store uses UUID4 (non-guessable)
# ═══════════════════════════════════════════════════════════════════════════

class TestSessionStoreUUID:
    """Session IDs must be random UUIDs, not sequential or guessable."""

    def setup_method(self):
        session_store.clear_all()

    def test_document_id_is_valid_uuid4(self):
        """document_id should be a valid UUID4 string."""
        doc_id = session_store.create_session("test", "LEASE")
        parsed = uuid.UUID(doc_id, version=4)
        assert str(parsed) == doc_id

    def test_document_ids_are_not_sequential(self):
        """Two consecutive document_ids should not be sequential."""
        id1 = session_store.create_session("doc1", "LEASE")
        id2 = session_store.create_session("doc2", "LEASE")
        assert id1 != id2
        # UUID4 uses random bits — they shouldn't be numerically adjacent.
        int1 = uuid.UUID(id1).int
        int2 = uuid.UUID(id2).int
        assert abs(int1 - int2) > 1000, "IDs appear sequential"
