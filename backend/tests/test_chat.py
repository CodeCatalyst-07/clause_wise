"""
ClauseWise — Tests for Chat Q&A Endpoint and Session Store

Tests cover five critical paths with **mocked Gemini API calls**:

  (a) Successful Q&A round-trip with a valid document_id
  (b) Missing/expired document_id error
  (c) Empty question validation error
  (d) Gemini API failure
  (e) Advice-seeking question → appropriate redirect response

Also includes unit tests for the session store (create, get, expiry, sweep).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.disclaimers import DISCLAIMER_TEXT
from app.core import session_store
from app.main import app
from app.services import gemini_service

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_session(text: str = "Sample lease agreement text.", doc_type: str = "LEASE") -> str:
    """Create a session and return the document_id."""
    return session_store.create_session(text, doc_type)


def _mock_gemini_for_analysis():
    """Return mock Gemini responses for the analysis pipeline (3 calls)."""
    from app.models.schemas import LeaseExtraction

    classify_resp = MagicMock()
    classify_resp.parsed = gemini_service._ClassificationResponse(
        document_type="LEASE", confidence="HIGH"
    )
    classify_resp.text = None

    extraction = LeaseExtraction(
        parties=["Landlord", "Tenant"],
        rent_amount="$2,000/month",
        payment_due_date="1st",
        lease_term_start="Jan 1, 2025",
        lease_term_end="Dec 31, 2025",
        security_deposit="$4,000",
        maintenance_obligations="Tenant",
        termination_conditions="30 days notice",
        notable_restrictions="None",
        risk_flags=["Auto-renewal"],
    )
    extract_resp = MagicMock()
    extract_resp.parsed = extraction
    extract_resp.text = None

    summary_resp = MagicMock()
    summary_resp.parsed = None
    summary_resp.text = "This is a residential lease."

    return [classify_resp, extract_resp, summary_resp]


# ═══════════════════════════════════════════════════════════════════════════
# Session Store Unit Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSessionStore:
    """Unit tests for the in-memory session store."""

    def setup_method(self):
        session_store.clear_all()

    def test_create_and_get_session(self):
        """Creating a session should return a UUID that can be retrieved."""
        doc_id = _create_test_session()
        session = session_store.get_session(doc_id)

        assert session is not None
        assert session["text"] == "Sample lease agreement text."
        assert session["doc_type"] == "LEASE"
        assert "created_at" in session

    def test_missing_session_returns_none(self):
        """Looking up a non-existent ID should return None."""
        result = session_store.get_session("nonexistent-uuid")
        assert result is None

    def test_expired_session_returns_none(self):
        """A session older than TTL should return None and be deleted."""
        doc_id = _create_test_session()
        # Artificially age the entry past the TTL
        session_store._store[doc_id]["created_at"] = (
            datetime.now(timezone.utc)
            - timedelta(minutes=session_store.SESSION_TTL_MINUTES + 1)
        )

        result = session_store.get_session(doc_id)
        assert result is None
        # Should be cleaned up
        assert doc_id not in session_store._store

    def test_sweep_removes_expired(self):
        """sweep_expired() should remove stale entries."""
        fresh_id = _create_test_session("Fresh doc")
        old_id = _create_test_session("Old doc")

        session_store._store[old_id]["created_at"] = (
            datetime.now(timezone.utc)
            - timedelta(minutes=session_store.SESSION_TTL_MINUTES + 5)
        )

        removed = session_store.sweep_expired()
        assert removed == 1
        assert session_store.get_session(fresh_id) is not None
        assert session_store.get_session(old_id) is None

    def test_clear_all(self):
        """clear_all() should empty the store."""
        _create_test_session()
        _create_test_session()
        session_store.clear_all()
        assert len(session_store._store) == 0


# ═══════════════════════════════════════════════════════════════════════════
# (a) Successful Q&A round-trip
# ═══════════════════════════════════════════════════════════════════════════

class TestChatHappyPath:
    """Successful chat Q&A with a valid document session."""

    def setup_method(self):
        session_store.clear_all()
        gemini_service.reset_client()

    @patch("app.services.gemini_service._get_client")
    def test_chat_returns_grounded_answer(self, mock_get_client):
        """POST /chat with valid document_id returns a grounded answer."""
        doc_id = _create_test_session(
            "This lease runs from Jan 1 to Dec 31, 2025. Rent is $2,000/month."
        )

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content.return_value = MagicMock(
            text="The lease runs from January 1, 2025 to December 31, 2025."
        )

        response = client.post(
            "/chat",
            json={
                "document_id": doc_id,
                "question": "When does the lease end?",
                "history": [],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "lease" in data["answer"].lower()
        assert data["disclaimer"] == DISCLAIMER_TEXT

    @patch("app.services.gemini_service._get_client")
    def test_chat_with_history(self, mock_get_client):
        """Chat should accept conversation history for follow-up coherence."""
        doc_id = _create_test_session("Rent is $2,000/month.")

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content.return_value = MagicMock(
            text="Yes, the rent amount is $2,000 per month."
        )

        response = client.post(
            "/chat",
            json={
                "document_id": doc_id,
                "question": "Can you confirm that?",
                "history": [
                    {"role": "user", "content": "What is the rent?"},
                    {"role": "assistant", "content": "The rent is $2,000/month."},
                ],
            },
        )

        assert response.status_code == 200

    @patch("app.services.gemini_service._get_client")
    def test_full_pipeline_then_chat(self, mock_get_client):
        """Analyze a document, then use the returned document_id for chat."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # First: analysis pipeline (3 calls)
        mock_client.models.generate_content.side_effect = (
            _mock_gemini_for_analysis()
        )

        analyze_response = client.post(
            "/documents/analyze",
            json={"text": "This is a lease agreement for 123 Main St."},
        )
        assert analyze_response.status_code == 200
        doc_id = analyze_response.json()["document_id"]
        assert doc_id is not None

        # Then: chat (1 call)
        mock_client.models.generate_content.side_effect = None
        mock_client.models.generate_content.return_value = MagicMock(
            text="The property is at 123 Main St."
        )

        chat_response = client.post(
            "/chat",
            json={
                "document_id": doc_id,
                "question": "What is the property address?",
                "history": [],
            },
        )
        assert chat_response.status_code == 200
        assert "123 Main St" in chat_response.json()["answer"]


# ═══════════════════════════════════════════════════════════════════════════
# (b) Missing / expired document_id
# ═══════════════════════════════════════════════════════════════════════════

class TestChatMissingDocument:
    """Missing or expired document_id returns 404."""

    def setup_method(self):
        session_store.clear_all()

    def test_unknown_document_id_returns_404(self):
        """A non-existent document_id should return 404 with a clear message."""
        response = client.post(
            "/chat",
            json={
                "document_id": "nonexistent-uuid",
                "question": "What is the rent?",
                "history": [],
            },
        )

        assert response.status_code == 404
        data = response.json()["detail"]
        assert data["error"] == "document_not_found"
        assert "re-upload" in data["detail"].lower() or "re-analyze" in data["detail"].lower()
        assert data["disclaimer"] == DISCLAIMER_TEXT

    def test_expired_document_id_returns_404(self):
        """An expired session should return 404, not 500."""
        doc_id = _create_test_session()
        session_store._store[doc_id]["created_at"] = (
            datetime.now(timezone.utc)
            - timedelta(minutes=session_store.SESSION_TTL_MINUTES + 1)
        )

        response = client.post(
            "/chat",
            json={
                "document_id": doc_id,
                "question": "What is the rent?",
                "history": [],
            },
        )

        assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# (c) Empty question validation
# ═══════════════════════════════════════════════════════════════════════════

class TestChatValidation:
    """Input validation for the chat endpoint."""

    def test_empty_question_returns_422(self):
        """An empty question should be rejected by Pydantic validation."""
        response = client.post(
            "/chat",
            json={
                "document_id": "some-id",
                "question": "",
                "history": [],
            },
        )
        assert response.status_code == 422

    def test_missing_document_id_returns_422(self):
        """Missing document_id field should be rejected."""
        response = client.post(
            "/chat",
            json={"question": "What is the rent?"},
        )
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# (d) Gemini API failure
# ═══════════════════════════════════════════════════════════════════════════

class TestChatGeminiFailure:
    """Gemini failures during chat are returned as 502."""

    def setup_method(self):
        session_store.clear_all()
        gemini_service.reset_client()

    @patch("app.services.gemini_service._get_client")
    def test_gemini_timeout_returns_502(self, mock_get_client):
        """If Gemini times out, the chat endpoint returns 502."""
        doc_id = _create_test_session()

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content.side_effect = TimeoutError("deadline exceeded")

        response = client.post(
            "/chat",
            json={
                "document_id": doc_id,
                "question": "What is the rent?",
                "history": [],
            },
        )

        assert response.status_code == 502
        data = response.json()["detail"]
        assert data["error"] == "gemini_service_error"
        assert data["disclaimer"] == DISCLAIMER_TEXT


# ═══════════════════════════════════════════════════════════════════════════
# (e) Advice-seeking question → redirect
# ═══════════════════════════════════════════════════════════════════════════

class TestChatAdviceRedirect:
    """Advice-seeking questions get a redirect response."""

    def setup_method(self):
        session_store.clear_all()
        gemini_service.reset_client()

    @patch("app.services.gemini_service._get_client")
    def test_advice_question_redirects_to_attorney(self, mock_get_client):
        """
        When asked 'should I sign this?', the model should provide relevant
        info, redirect to an attorney, AND proactively suggest questions to
        ask the lawyer (Phase 2.7 addition — "prepare for a legal professional"
        use case from the problem statement).
        """
        doc_id = _create_test_session(
            "This lease has a $5,000 security deposit and auto-renewal."
        )

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        # Simulated model response that follows our prompt's advice-redirect
        # AND proactive attorney-prep rules (rules #2 and #5)
        mock_client.models.generate_content.return_value = MagicMock(
            text=(
                "The document includes a $5,000 security deposit and an "
                "auto-renewal clause. For advice on your specific situation, "
                "please consult a licensed attorney.\n\n"
                "Questions you might ask a lawyer:\n"
                "- Is the $5,000 security deposit negotiable?\n"
                "- What happens if I miss the auto-renewal cancellation deadline?"
            )
        )

        response = client.post(
            "/chat",
            json={
                "document_id": doc_id,
                "question": "Should I sign this lease?",
                "history": [],
            },
        )

        assert response.status_code == 200
        answer = response.json()["answer"]
        assert "attorney" in answer.lower()
        assert "consult" in answer.lower()
        # Phase 2.7: proactive attorney-prep suggestions should be present
        assert "questions you might ask" in answer.lower()
