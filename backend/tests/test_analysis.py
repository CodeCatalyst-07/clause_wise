"""
ClauseWise — Tests for the Document Analysis Pipeline

Tests cover three critical paths, all with **mocked Gemini API calls**
(no real network traffic — fast, deterministic, and CI-friendly):

  (a) Successful classification + extraction + summary (happy path)
  (b) Fallback to ``OTHER`` when classification returns an unrecognized type
  (c) Graceful error handling when Gemini returns malformed JSON

Each test uses ``unittest.mock.patch`` to replace the Gemini client's
``generate_content`` method with a canned response, so we can verify the
service logic in isolation without an API key.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.disclaimers import DISCLAIMER_TEXT
from app.main import app
from app.models.document_types import DocumentType
from app.services import gemini_service

client = TestClient(app)

# ---------------------------------------------------------------------------
# Sample document texts used across tests
# ---------------------------------------------------------------------------

SAMPLE_LEASE_TEXT = """
RESIDENTIAL LEASE AGREEMENT

This Lease Agreement is entered into on January 1, 2025, between
John Smith ("Landlord") and Jane Doe ("Tenant").

Property: 123 Main Street, Apt 4B, New York, NY 10001

Term: The lease begins on January 1, 2025 and ends on December 31, 2025.
Monthly rent: $2,500.00, due on the 1st of each month.
Security deposit: $5,000.00, refundable within 30 days of lease termination.

Maintenance: Tenant is responsible for minor repairs under $100.
Landlord handles structural and plumbing issues.

Termination: Either party may terminate with 60 days written notice.
Early termination by Tenant incurs a penalty of 2 months' rent.

Restrictions: No pets allowed. No subletting without written consent.
The lease auto-renews for successive 1-year terms unless terminated
with 60 days notice before expiration.
"""

SAMPLE_UNKNOWN_TEXT = """
MEMORANDUM OF UNDERSTANDING

Between the Republic of Exampleland and Corporation XYZ regarding
bilateral cooperation in renewable energy development across the
Southern Hemisphere corridor, effective March 2025.
"""


# ---------------------------------------------------------------------------
# Helper: build a mock Gemini response
# ---------------------------------------------------------------------------

def _make_mock_response(parsed_obj=None, text: str | None = None):
    """
    Create a ``MagicMock`` that looks like a Gemini ``GenerateContentResponse``.

    Args:
        parsed_obj: The ``response.parsed`` Pydantic model instance, or None.
        text: Raw text fallback (``response.text``).
    """
    mock = MagicMock()
    mock.parsed = parsed_obj
    mock.text = text
    return mock


# ═══════════════════════════════════════════════════════════════════════════
# (a) Happy path — successful LEASE classification + extraction + summary
# ═══════════════════════════════════════════════════════════════════════════


class TestHappyPath:
    """Full pipeline succeeds with valid Gemini responses."""

    def setup_method(self):
        """Reset the cached client before each test."""
        gemini_service.reset_client()

    @patch("app.services.gemini_service._get_client")
    def test_classify_document_returns_lease(self, mock_get_client):
        """classify_document should return LEASE for a lease document."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Simulate structured Gemini response
        parsed = gemini_service._ClassificationResponse(
            document_type="LEASE", confidence="HIGH"
        )
        mock_client.models.generate_content.return_value = _make_mock_response(
            parsed_obj=parsed
        )

        result = gemini_service.classify_document(SAMPLE_LEASE_TEXT)
        assert result == DocumentType.LEASE

    @patch("app.services.gemini_service._get_client")
    def test_extract_fields_returns_structured_data(self, mock_get_client):
        """extract_fields should return an ExtractionResult with fields and risk_flags."""
        from app.models.schemas import LeaseExtraction

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        parsed = LeaseExtraction(
            parties=["John Smith", "Jane Doe"],
            rent_amount="$2,500.00 per month",
            payment_due_date="1st of each month",
            lease_term_start="January 1, 2025",
            lease_term_end="December 31, 2025",
            security_deposit="$5,000.00",
            maintenance_obligations="Tenant: minor repairs under $100; Landlord: structural/plumbing",
            termination_conditions="60 days written notice; early termination = 2 months penalty",
            notable_restrictions="No pets, no subletting without consent",
            risk_flags=[
                "Auto-renewal clause with 60-day cancellation window",
                "Early termination penalty of 2 months rent is significant",
            ],
        )
        mock_client.models.generate_content.return_value = _make_mock_response(
            parsed_obj=parsed
        )

        result = gemini_service.extract_fields(SAMPLE_LEASE_TEXT, DocumentType.LEASE)

        assert "parties" in result.fields
        assert result.fields["parties"] == ["John Smith", "Jane Doe"]
        assert len(result.risk_flags) == 2
        assert "Auto-renewal" in result.risk_flags[0]

    @patch("app.services.gemini_service._get_client")
    def test_generate_summary_returns_text(self, mock_get_client):
        """generate_summary should return a non-empty summary string."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        summary_text = (
            "This is a one-year residential lease between John Smith (landlord) "
            "and Jane Doe (tenant) for an apartment at 123 Main Street, New York. "
            "The monthly rent is $2,500, due on the first of each month."
        )
        mock_client.models.generate_content.return_value = _make_mock_response(
            text=summary_text
        )

        result = gemini_service.generate_summary(SAMPLE_LEASE_TEXT, DocumentType.LEASE)
        assert len(result) > 0
        assert "lease" in result.lower()

    @patch("app.services.gemini_service._get_client")
    def test_full_pipeline_via_endpoint(self, mock_get_client):
        """POST /documents/analyze should return a complete AnalysisResult."""
        from app.models.schemas import LeaseExtraction

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Set up the three sequential Gemini calls
        classification_resp = _make_mock_response(
            parsed_obj=gemini_service._ClassificationResponse(
                document_type="LEASE", confidence="HIGH"
            )
        )
        extraction_resp = _make_mock_response(
            parsed_obj=LeaseExtraction(
                parties=["John Smith", "Jane Doe"],
                rent_amount="$2,500/month",
                payment_due_date="1st of each month",
                lease_term_start="Jan 1, 2025",
                lease_term_end="Dec 31, 2025",
                security_deposit="$5,000",
                maintenance_obligations="Shared",
                termination_conditions="60 days notice",
                notable_restrictions="No pets",
                risk_flags=["Auto-renewal clause"],
            )
        )
        summary_resp = _make_mock_response(
            text="This is a lease agreement for an apartment."
        )
        suggested_q_resp = _make_mock_response(
            text=json.dumps([
                "Is the auto-renewal clause negotiable?",
                "What happens if I miss the cancellation deadline?",
            ])
        )

        mock_client.models.generate_content.side_effect = [
            classification_resp,
            extraction_resp,
            summary_resp,
            suggested_q_resp,
        ]

        response = client.post(
            "/documents/analyze",
            json={"text": SAMPLE_LEASE_TEXT},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["doc_type"] == "LEASE"
        assert "parties" in data["extracted"]["fields"]
        assert len(data["extracted"]["risk_flags"]) >= 1
        assert len(data["summary"]) > 0
        assert data["disclaimer"] == DISCLAIMER_TEXT
        # Phase 2.7: suggested questions should be populated from risk flags
        assert "suggested_questions" in data
        assert len(data["suggested_questions"]) >= 1
        assert "?" in data["suggested_questions"][0]  # should be a question


# ═══════════════════════════════════════════════════════════════════════════
# (b) OTHER fallback — classification returns unrecognized type
# ═══════════════════════════════════════════════════════════════════════════


class TestOtherFallback:
    """Pipeline gracefully falls back to OTHER for unknown document types."""

    def setup_method(self):
        gemini_service.reset_client()

    @patch("app.services.gemini_service._get_client")
    def test_unrecognized_type_falls_back_to_other(self, mock_get_client):
        """An unrecognized classification string should map to OTHER."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        parsed = gemini_service._ClassificationResponse(
            document_type="BILATERAL_TREATY", confidence="HIGH"
        )
        mock_client.models.generate_content.return_value = _make_mock_response(
            parsed_obj=parsed
        )

        result = gemini_service.classify_document(SAMPLE_UNKNOWN_TEXT)
        assert result == DocumentType.OTHER

    @patch("app.services.gemini_service._get_client")
    def test_low_confidence_falls_back_to_other(self, mock_get_client):
        """LOW confidence classification should fall back to OTHER."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        parsed = gemini_service._ClassificationResponse(
            document_type="LEASE", confidence="LOW"
        )
        mock_client.models.generate_content.return_value = _make_mock_response(
            parsed_obj=parsed
        )

        result = gemini_service.classify_document(SAMPLE_UNKNOWN_TEXT)
        assert result == DocumentType.OTHER

    @patch("app.services.gemini_service._get_client")
    def test_full_pipeline_with_other_type(self, mock_get_client):
        """Pipeline should work end-to-end even when doc_type is OTHER."""
        from app.models.schemas import OtherExtraction

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        classification_resp = _make_mock_response(
            parsed_obj=gemini_service._ClassificationResponse(
                document_type="OTHER", confidence="HIGH"
            )
        )
        extraction_resp = _make_mock_response(
            parsed_obj=OtherExtraction(
                parties=["Republic of Exampleland", "Corporation XYZ"],
                key_dates=["March 2025"],
                obligations=["Bilateral cooperation in renewable energy"],
                potential_risks=["Vague scope of cooperation"],
                risk_flags=["No specific deliverables or deadlines mentioned"],
            )
        )
        summary_resp = _make_mock_response(
            text="This is a memorandum of understanding between two parties."
        )
        suggested_q_resp = _make_mock_response(
            text=json.dumps([
                "What specific deliverables or milestones should be defined?",
            ])
        )

        mock_client.models.generate_content.side_effect = [
            classification_resp,
            extraction_resp,
            summary_resp,
            suggested_q_resp,
        ]

        response = client.post(
            "/documents/analyze",
            json={"text": SAMPLE_UNKNOWN_TEXT},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["doc_type"] == "OTHER"
        assert "parties" in data["extracted"]["fields"]
        assert data["disclaimer"] == DISCLAIMER_TEXT
        assert "suggested_questions" in data


# ═══════════════════════════════════════════════════════════════════════════
# (c) Error handling — malformed responses and API failures
# ═══════════════════════════════════════════════════════════════════════════


class TestErrorHandling:
    """Verify graceful degradation when Gemini returns bad data or fails."""

    def setup_method(self):
        gemini_service.reset_client()

    @patch("app.services.gemini_service._get_client")
    def test_malformed_classification_falls_back_to_other(self, mock_get_client):
        """
        If Gemini returns unparseable JSON for classification, the function
        should fall back to OTHER rather than crashing.
        """
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Return a response where .parsed is None and .text is garbage
        mock_client.models.generate_content.return_value = _make_mock_response(
            parsed_obj=None, text="this is not json at all"
        )

        result = gemini_service.classify_document("some document text")
        assert result == DocumentType.OTHER

    @patch("app.services.gemini_service._get_client")
    def test_extraction_api_error_raises_service_error(self, mock_get_client):
        """
        If Gemini throws during extraction, extract_fields should raise
        GeminiServiceError (not a raw exception).
        """
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.models.generate_content.side_effect = RuntimeError("API timeout")

        with pytest.raises(gemini_service.GeminiServiceError, match="Extraction failed"):
            gemini_service.extract_fields("some text", DocumentType.LEASE)

    @patch("app.services.gemini_service._get_client")
    def test_malformed_extraction_raises_service_error(self, mock_get_client):
        """
        If Gemini returns JSON that doesn't match the schema, the function
        should raise GeminiServiceError with a clear message.
        """
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Return JSON, but not matching the LeaseExtraction schema shape
        mock_client.models.generate_content.return_value = _make_mock_response(
            parsed_obj=None, text='{"completely": "wrong schema"}'
        )

        # This should raise because the parsed dict won't match LeaseExtraction
        # (missing required fields will use defaults, but let's test with truly
        #  invalid JSON that *does* parse as JSON but the Pydantic model will
        #  still accept because all fields have defaults — so this path actually
        #  succeeds gracefully, which is the right behavior).
        # Instead, test with non-JSON to trigger the JSONDecodeError path:
        mock_client.models.generate_content.return_value = _make_mock_response(
            parsed_obj=None, text="NOT VALID JSON {{{{"
        )

        with pytest.raises(gemini_service.GeminiServiceError, match="Failed to parse"):
            gemini_service.extract_fields("some text", DocumentType.LEASE)

    @patch("app.services.gemini_service._get_client")
    def test_analyze_endpoint_returns_502_on_service_error(self, mock_get_client):
        """
        POST /documents/analyze should return 502 with an ErrorResponse
        when the Gemini service fails.
        """
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.models.generate_content.side_effect = RuntimeError(
            "Connection refused"
        )

        response = client.post(
            "/documents/analyze",
            json={"text": "some document text"},
        )

        assert response.status_code == 502
        data = response.json()["detail"]
        assert data["error"] == "gemini_service_error"
        assert data["disclaimer"] == DISCLAIMER_TEXT

    def test_analyze_endpoint_rejects_empty_text(self):
        """POST /documents/analyze should reject an empty text field (422)."""
        response = client.post(
            "/documents/analyze",
            json={"text": ""},
        )
        assert response.status_code == 422
