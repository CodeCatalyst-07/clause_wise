"""
ClauseWise — Document Type Enumeration

Defines the set of legal document categories that ClauseWise can classify
and route to type-specific extraction pipelines. Each enum member maps to
a dedicated JSON extraction schema in `models/schemas.py`.

The `OTHER` variant acts as a required safety net: when the classifier is
not confident about the document type, the pipeline falls back to a
generic extraction schema rather than guessing or crashing.
"""

from enum import Enum


class DocumentType(str, Enum):
    """
    Supported legal document categories.

    Inherits from `str` so the enum serializes to a plain JSON string
    (e.g. ``"LEASE"``) in API responses without extra conversion.
    """

    LEASE = "LEASE"
    NDA = "NDA"
    TERMS_OF_SERVICE = "TERMS_OF_SERVICE"
    EMPLOYMENT_CONTRACT = "EMPLOYMENT_CONTRACT"
    OTHER = "OTHER"
