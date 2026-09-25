"""
ClauseWise — Pydantic Models (Schemas)

This package contains all request/response schemas used by the API routers.
Pydantic models provide automatic validation, serialization, and OpenAPI
documentation generation.

Re-exports are provided here for convenient imports elsewhere in the app:
    from app.models import DocumentType, AnalyzeRequest, AnalysisResult
"""

from app.models.document_types import DocumentType
from app.models.requests import AnalyzeRequest
from app.models.responses import (
    AnalysisResult,
    ExtractionResult,
    ErrorResponse,
)

__all__ = [
    "DocumentType",
    "AnalyzeRequest",
    "AnalysisResult",
    "ExtractionResult",
    "ErrorResponse",
]
