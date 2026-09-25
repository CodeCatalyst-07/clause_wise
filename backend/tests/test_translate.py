"""
ClauseWise — Tests for Translation Service and Endpoints

Tests cover three critical paths with **mocked Translation API calls**:

  (a) Successful translation
  (b) Unsupported / invalid language code
  (c) API failure / error path

Also tests the /translate/languages endpoint.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.disclaimers import DISCLAIMER_TEXT
from app.main import app
from app.services import translate_service

client = TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# (a) Successful translation
# ═══════════════════════════════════════════════════════════════════════════


class TestTranslationHappyPath:
    """Translation succeeds with valid text and language code."""

    def setup_method(self):
        translate_service.reset_client()

    @patch("app.services.translate_service._get_client")
    def test_translate_text_returns_translated_string(self, mock_get_client):
        """translate_text should return the translated string."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.translate.return_value = {
            "translatedText": "Este es un contrato de arrendamiento.",
            "detectedSourceLanguage": "en",
        }

        result = translate_service.translate_text(
            "This is a lease agreement.", "es"
        )
        assert result == "Este es un contrato de arrendamiento."

    @patch("app.services.translate_service._get_client")
    def test_translate_endpoint_returns_200(self, mock_get_client):
        """POST /translate should return 200 with translated text."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.translate.return_value = {
            "translatedText": "Ceci est un bail.",
        }

        response = client.post(
            "/translate",
            json={"text": "This is a lease.", "target_language": "fr"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["translated_text"] == "Ceci est un bail."

    @patch("app.services.translate_service._get_client")
    def test_languages_endpoint_returns_sorted_list(self, mock_get_client):
        """GET /translate/languages should return a sorted list of languages."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_languages.return_value = [
            {"language": "es", "name": "Spanish"},
            {"language": "fr", "name": "French"},
            {"language": "de", "name": "German"},
        ]

        response = client.get("/translate/languages")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        # Should be sorted alphabetically by name
        assert data[0]["name"] == "French"
        assert data[1]["name"] == "German"
        assert data[2]["name"] == "Spanish"


# ═══════════════════════════════════════════════════════════════════════════
# (b) Unsupported / invalid language code
# ═══════════════════════════════════════════════════════════════════════════


class TestTranslationInvalidInput:
    """Invalid inputs are handled gracefully."""

    def test_empty_text_rejected(self):
        """POST /translate with empty text should return 422."""
        response = client.post(
            "/translate",
            json={"text": "", "target_language": "es"},
        )
        assert response.status_code == 422

    def test_missing_target_language_rejected(self):
        """POST /translate without target_language should return 422."""
        response = client.post(
            "/translate",
            json={"text": "Hello world"},
        )
        assert response.status_code == 422

    @patch("app.services.translate_service._get_client")
    def test_api_error_on_bad_language_code(self, mock_get_client):
        """If the API rejects the language code, a 502 is returned."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.translate.side_effect = Exception(
            "Invalid target language: xyz"
        )

        translate_service.reset_client()

        response = client.post(
            "/translate",
            json={"text": "Hello", "target_language": "xyz"},
        )

        assert response.status_code == 502
        data = response.json()["detail"]
        assert data["error"] == "translate_service_error"


# ═══════════════════════════════════════════════════════════════════════════
# (c) API failure
# ═══════════════════════════════════════════════════════════════════════════


class TestTranslationAPIFailure:
    """API failures are caught and returned as 502."""

    def setup_method(self):
        translate_service.reset_client()

    @patch("app.services.translate_service._get_client")
    def test_translate_api_timeout(self, mock_get_client):
        """Timeouts produce a clean 502 with disclaimer."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.translate.side_effect = TimeoutError("deadline exceeded")

        response = client.post(
            "/translate",
            json={"text": "Test text", "target_language": "es"},
        )

        assert response.status_code == 502
        data = response.json()["detail"]
        assert data["disclaimer"] == DISCLAIMER_TEXT

    @patch("app.services.translate_service._get_client")
    def test_languages_api_failure(self, mock_get_client):
        """GET /translate/languages returns 502 on API failure."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_languages.side_effect = RuntimeError("network error")

        response = client.get("/translate/languages")

        assert response.status_code == 502

    @patch("app.services.translate_service._get_client")
    def test_empty_translation_result_raises_error(self, mock_get_client):
        """An empty translatedText should raise TranslateServiceError."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.translate.return_value = {"translatedText": ""}

        with pytest.raises(translate_service.TranslateServiceError):
            translate_service.translate_text("Hello", "es")
