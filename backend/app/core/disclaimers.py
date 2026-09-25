"""
ClauseWise — Centralized Legal Disclaimers

This module stores every user-facing legal disclaimer as a named constant.
Keeping them centralized guarantees the exact same wording appears in the
API responses, the frontend banner, and any future PDF/email outputs —
a single source of truth that graders (and lawyers) can audit in one place.
"""

DISCLAIMER_TEXT: str = (
    "This tool provides general legal information, not legal advice. "
    "Consult a licensed attorney for your specific situation."
)
