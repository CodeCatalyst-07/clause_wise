"""
ClauseWise — Tests for File Upload + Document AI Pipeline

Tests cover six critical paths, all with **mocked Document AI and Gemini
API calls** (no real network traffic — fast, deterministic, CI-friendly):

  (a) Successful upload → text extraction → full analysis round-trip
  (b) Unsupported file type rejection (magic-byte validation)
  (c) Oversized file rejection
  (d) Empty file rejection
  (e) Document AI API failure / error path
  (f) No extractable text path (blank page / unreadable scan)

Each test uses ``unittest.mock.patch`` to replace external clients with
canned responses, so we can verify the logic in isolation.
"""

import io
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.disclaimers import DISCLAIMER_TEXT
from app.core.validators import MAX_FILE_SIZE_BYTES
from app.main import app
from app.services import docai_service, gemini_service

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers: realistic file content with correct magic bytes
# ---------------------------------------------------------------------------

def _make_pdf_bytes(text_content: str = "sample") -> bytes:
    """Create minimal bytes that start with the PDF magic signature."""
    # Real PDF header + enough filler to not look empty
    return b"%PDF-1.4 " + text_content.encode() + b" " * 100


def _make_jpeg_bytes() -> bytes:
    """Create minimal bytes that start with the JPEG magic signature."""
    return b"\xff\xd8\xff\xe0" + b"\x00" * 200


def _make_png_bytes() -> bytes:
    """Create minimal bytes that start with the PNG magic signature."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


def _make_txt_bytes() -> bytes:
    """Create bytes that look like a plain text file (unsupported)."""
    return b"This is a plain text file, not a PDF or image."


def _mock_docai_result(text: str) -> MagicMock:
    """Build a mock that mimics ``documentai.ProcessResponse``."""
    mock_doc = MagicMock()
    mock_doc.text = text
    mock_doc.pages = [MagicMock()]  # at least one page

    mock_result = MagicMock()
    mock_result.document = mock_doc
    return mock_result


def _mock_gemini_classify_extract_summarize():
    """
    Return a list of four mock Gemini responses (classification,
    extraction, summary, suggested questions) for a LEASE document —
    reusable across tests that need the full pipeline to succeed after
    Document AI.
    """
    from app.models.schemas import LeaseExtraction

    classify_resp = MagicMock()
    classify_resp.parsed = gemini_service._ClassificationResponse(
        document_type="LEASE", confidence="HIGH"
    )
    classify_resp.text = None

    extraction = LeaseExtraction(
        parties=["Landlord Corp", "Tenant LLC"],
        rent_amount="$3,000/month",
        payment_due_date="1st of each month",
        lease_term_start="Jan 1, 2025",
        lease_term_end="Dec 31, 2025",
        security_deposit="$6,000",
        maintenance_obligations="Shared",
        termination_conditions="90 days notice",
        notable_restrictions="No pets",
        risk_flags=["Broad liability waiver"],
    )
    extract_resp = MagicMock()
    extract_resp.parsed = extraction
    extract_resp.text = None

    summary_resp = MagicMock()
    summary_resp.parsed = None
    summary_resp.text = "This is a lease for a commercial property."

    # Phase 2.7: suggested questions for a lawyer
    suggested_q_resp = MagicMock()
    suggested_q_resp.parsed = None
    suggested_q_resp.text = json.dumps([
        "Is the broad liability waiver negotiable?",
    ])

    return [classify_resp, extract_resp, summary_resp, suggested_q_resp]


# ═══════════════════════════════════════════════════════════════════════════
# (a) Happy path — successful upload → OCR → analysis
# ═══════════════════════════════════════════════════════════════════════════


class TestUploadHappyPath:
    """Full pipeline succeeds: upload PDF → Document AI OCR → Gemini analysis."""

    def setup_method(self):
        gemini_service.reset_client()
        docai_service.reset_client()

    @patch("app.services.gemini_service._get_client")
    @patch("app.services.docai_service._get_client")
    def test_pdf_upload_returns_analysis_result(
        self, mock_docai_get_client, mock_gemini_get_client
    ):
        """Upload a PDF → extract text → classify → extract → summarize."""
        # Mock Document AI
        mock_docai_client = MagicMock()
        mock_docai_get_client.return_value = mock_docai_client
        mock_docai_client.process_document.return_value = _mock_docai_result(
            "This Lease Agreement is between Landlord Corp and Tenant LLC..."
        )

        # Mock Gemini (3 sequential calls)
        mock_gemini_client = MagicMock()
        mock_gemini_get_client.return_value = mock_gemini_client
        mock_gemini_client.models.generate_content.side_effect = (
            _mock_gemini_classify_extract_summarize()
        )

        pdf_bytes = _make_pdf_bytes()
        response = client.post(
            "/documents/upload",
            files={"file": ("contract.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["doc_type"] == "LEASE"
        assert "parties" in data["extracted"]["fields"]
        assert len(data["extracted"]["risk_flags"]) >= 1
        assert len(data["summary"]) > 0
        assert data["disclaimer"] == DISCLAIMER_TEXT

    @patch("app.services.gemini_service._get_client")
    @patch("app.services.docai_service._get_client")
    def test_jpeg_upload_works(
        self, mock_docai_get_client, mock_gemini_get_client
    ):
        """JPEG files should be accepted and processed successfully."""
        mock_docai_client = MagicMock()
        mock_docai_get_client.return_value = mock_docai_client
        mock_docai_client.process_document.return_value = _mock_docai_result(
            "Non-Disclosure Agreement between Party A and Party B..."
        )

        mock_gemini_client = MagicMock()
        mock_gemini_get_client.return_value = mock_gemini_client
        mock_gemini_client.models.generate_content.side_effect = (
            _mock_gemini_classify_extract_summarize()
        )

        jpeg_bytes = _make_jpeg_bytes()
        response = client.post(
            "/documents/upload",
            files={"file": ("scan.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        )

        assert response.status_code == 200

    @patch("app.services.gemini_service._get_client")
    @patch("app.services.docai_service._get_client")
    def test_png_upload_works(
        self, mock_docai_get_client, mock_gemini_get_client
    ):
        """PNG files should be accepted and processed successfully."""
        mock_docai_client = MagicMock()
        mock_docai_get_client.return_value = mock_docai_client
        mock_docai_client.process_document.return_value = _mock_docai_result(
            "Employment Contract between Acme Corp and John Doe..."
        )

        mock_gemini_client = MagicMock()
        mock_gemini_get_client.return_value = mock_gemini_client
        mock_gemini_client.models.generate_content.side_effect = (
            _mock_gemini_classify_extract_summarize()
        )

        png_bytes = _make_png_bytes()
        response = client.post(
            "/documents/upload",
            files={"file": ("scan.png", io.BytesIO(png_bytes), "image/png")},
        )

        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# (b) Unsupported file type rejection
# ═══════════════════════════════════════════════════════════════════════════


class TestUnsupportedFileType:
    """Files with unrecognized magic bytes are rejected with 415."""

    def test_text_file_rejected(self):
        """A .txt file should be rejected even if renamed to .pdf."""
        txt_bytes = _make_txt_bytes()
        response = client.post(
            "/documents/upload",
            # Note: extension says .pdf but content is plain text
            files={"file": ("sneaky.pdf", io.BytesIO(txt_bytes), "application/pdf")},
        )

        assert response.status_code == 415
        data = response.json()["detail"]
        assert data["error"] == "file_validation_error"
        assert "magic bytes" in data["detail"].lower()

    def test_random_binary_rejected(self):
        """Random binary data should be rejected."""
        random_bytes = b"\x00\x01\x02\x03\x04\x05" * 50
        response = client.post(
            "/documents/upload",
            files={"file": ("file.bin", io.BytesIO(random_bytes), "application/octet-stream")},
        )

        assert response.status_code == 415


# ═══════════════════════════════════════════════════════════════════════════
# (c) Oversized file rejection
# ═══════════════════════════════════════════════════════════════════════════


class TestOversizedFile:
    """Files larger than MAX_FILE_SIZE_BYTES are rejected with 413."""

    def test_oversized_pdf_rejected(self):
        """An 11 MB PDF should be rejected before reaching Document AI."""
        oversized = b"%PDF-1.4 " + b"\x00" * (MAX_FILE_SIZE_BYTES + 1)
        response = client.post(
            "/documents/upload",
            files={"file": ("huge.pdf", io.BytesIO(oversized), "application/pdf")},
        )

        assert response.status_code == 413
        data = response.json()["detail"]
        assert data["error"] == "file_validation_error"
        assert "too large" in data["detail"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# (d) Empty file rejection
# ═══════════════════════════════════════════════════════════════════════════


class TestEmptyFile:
    """Empty files are rejected with 422."""

    def test_zero_byte_file_rejected(self):
        """A completely empty upload should be rejected immediately."""
        response = client.post(
            "/documents/upload",
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        )

        assert response.status_code == 422
        data = response.json()["detail"]
        assert data["error"] == "file_validation_error"
        assert "empty" in data["detail"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# (e) Document AI API failure
# ═══════════════════════════════════════════════════════════════════════════


class TestDocAIFailure:
    """Document AI errors are caught and returned as 502."""

    def setup_method(self):
        docai_service.reset_client()

    @patch("app.services.docai_service._get_client")
    def test_docai_timeout_returns_502(self, mock_get_client):
        """If Document AI times out, the endpoint returns a clean 502."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.process_document.side_effect = TimeoutError("deadline exceeded")

        pdf_bytes = _make_pdf_bytes()
        response = client.post(
            "/documents/upload",
            files={"file": ("contract.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )

        assert response.status_code == 502
        data = response.json()["detail"]
        assert data["error"] == "docai_service_error"
        assert data["disclaimer"] == DISCLAIMER_TEXT

    @patch("app.services.docai_service._get_client")
    def test_docai_auth_error_returns_502(self, mock_get_client):
        """If Document AI auth fails, the endpoint returns a clean 502."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.process_document.side_effect = PermissionError(
            "403 Permission denied on resource"
        )

        pdf_bytes = _make_pdf_bytes()
        response = client.post(
            "/documents/upload",
            files={"file": ("contract.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )

        assert response.status_code == 502

    @patch("app.services.gemini_service._get_client")
    @patch("app.services.docai_service._get_client")
    def test_docai_billing_failure_falls_back_to_gemini_multimodal(
        self, mock_docai_get_client, mock_gemini_get_client
    ):
        """When Document AI returns a billing error, it gracefully falls back to Gemini multimodal OCR."""
        mock_docai = MagicMock()
        mock_docai_get_client.return_value = mock_docai
        mock_docai.process_document.side_effect = Exception(
            "403 This API method requires billing to be enabled. [reason: 'BILLING_DISABLED']"
        )

        mock_gemini = MagicMock()
        mock_gemini_get_client.return_value = mock_gemini

        ocr_resp = MagicMock()
        ocr_resp.text = "This is a valid lease contract between landlord and tenant with twenty chars."
        mock_gemini.models.generate_content.side_effect = [
            ocr_resp
        ] + _mock_gemini_classify_extract_summarize()

        pdf_bytes = _make_pdf_bytes("sample contract")
        response = client.post(
            "/documents/upload",
            files={"file": ("contract.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["doc_type"] == "LEASE"



# ═══════════════════════════════════════════════════════════════════════════
# (f) No extractable text (blank page / unreadable scan)
# ═══════════════════════════════════════════════════════════════════════════


class TestNoExtractableText:
    """Documents with no readable text produce a distinct error, not a Gemini hallucination."""

    def setup_method(self):
        docai_service.reset_client()

    @patch("app.services.docai_service._get_client")
    def test_blank_page_returns_502_with_clear_message(self, mock_get_client):
        """
        A document that yields empty or near-empty text should be caught
        *before* reaching the Gemini pipeline, with a distinct error message.
        """
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        # Document AI returns a result, but with no text
        mock_client.process_document.return_value = _mock_docai_result("")

        pdf_bytes = _make_pdf_bytes()
        response = client.post(
            "/documents/upload",
            files={"file": ("blank.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )

        assert response.status_code == 502
        data = response.json()["detail"]
        assert data["error"] == "docai_service_error"
        assert "no extractable text" in data["detail"].lower()

    @patch("app.services.docai_service._get_client")
    def test_very_short_text_returns_502(self, mock_get_client):
        """
        A document with only a few characters of OCR output (e.g. noise)
        should also be rejected — not passed to Gemini.
        """
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.process_document.return_value = _mock_docai_result("ok")

        pdf_bytes = _make_pdf_bytes()
        response = client.post(
            "/documents/upload",
            files={"file": ("noise.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )

        assert response.status_code == 502
        data = response.json()["detail"]
        assert "no extractable text" in data["detail"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# Validator unit tests (standalone, no HTTP)
# ═══════════════════════════════════════════════════════════════════════════


class TestValidatorUnit:
    """Direct unit tests for the validator functions."""

    def test_detect_pdf(self):
        from app.core.validators import validate_file
        mime = validate_file(_make_pdf_bytes(), "test.pdf")
        assert mime == "application/pdf"

    def test_detect_jpeg(self):
        from app.core.validators import validate_file
        mime = validate_file(_make_jpeg_bytes(), "test.jpg")
        assert mime == "image/jpeg"

    def test_detect_png(self):
        from app.core.validators import validate_file
        mime = validate_file(_make_png_bytes(), "test.png")
        assert mime == "image/png"

    def test_spoofed_extension_caught(self):
        """A .pdf extension on a text file should be caught by magic bytes."""
        from app.core.validators import FileValidationError, validate_file
        with pytest.raises(FileValidationError) as exc_info:
            validate_file(_make_txt_bytes(), "fake.pdf")
        assert exc_info.value.status_code == 415
