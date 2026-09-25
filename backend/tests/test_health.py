"""
ClauseWise — Backend Test Suite

Uses pytest + httpx (via FastAPI's TestClient) to exercise the API.
This initial file contains a single health-check test that proves:
  1. The test toolchain (pytest) is correctly installed and configured.
  2. The FastAPI app boots without import errors.
  3. The /health endpoint responds with 200 and the expected payload.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check_returns_200():
    """GET /health should return HTTP 200 with {"status": "ok"}."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok"}
