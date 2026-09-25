"""
ClauseWise — Error Sanitization Utilities

Ensures that error messages sent to clients never leak internal details
(stack traces, file paths, raw exception messages, API key fragments).

The pattern:
  • Internal exceptions are logged server-side (metadata only).
  • Client-facing error messages use a sanitized, generic-but-specific-enough
    description so the user understands what went wrong without seeing internals.
"""

from __future__ import annotations

import re


# Patterns that indicate internal details that should never reach the client.
_INTERNAL_PATTERNS = [
    re.compile(r"/Users/[^\s]+", re.IGNORECASE),        # file paths
    re.compile(r"/home/[^\s]+", re.IGNORECASE),          # Linux paths
    re.compile(r"[A-Za-z]:\\[^\s]+", re.IGNORECASE),     # Windows paths
    re.compile(r"Traceback \(most recent", re.IGNORECASE),  # stack traces
    re.compile(r"File \"[^\"]+\"", re.IGNORECASE),       # Python tracebacks
    re.compile(r"AIza[A-Za-z0-9_-]{10,}"),               # GCP API key prefix
    re.compile(r"sk-[A-Za-z0-9]{10,}"),                  # OpenAI-style keys
]

# Human-readable fallback messages by service.
_FALLBACK_MESSAGES = {
    "gemini": "The AI service encountered an error. Please try again shortly.",
    "docai": "Document processing failed. Please try again with a different file.",
    "translate": "Translation failed. Please try again shortly.",
    "default": "An internal error occurred. Please try again.",
}


def sanitize_error(raw_message: str, service: str = "default") -> str:
    """
    Sanitize an error message before sending it to the client.

    If the raw message contains patterns indicating internal details
    (file paths, stack traces, API key fragments), it is replaced with
    a clean fallback message. Otherwise the original message is returned.

    Args:
        raw_message: The raw exception message (may contain internals).
        service: The service name for a context-appropriate fallback
            ("gemini", "docai", "translate", or "default").

    Returns:
        A client-safe error message string.
    """
    for pattern in _INTERNAL_PATTERNS:
        if pattern.search(raw_message):
            return _FALLBACK_MESSAGES.get(service, _FALLBACK_MESSAGES["default"])

    return raw_message
