"""
ClauseWise — In-Memory Session Store

Provides ephemeral, session-scoped storage for document text so the chat
endpoint can reference a previously-analyzed document across multiple
follow-up questions.

**This is intentionally in-memory and ephemeral, NOT a persistence layer.**
Document text is never written to disk or to a database. This is consistent
with the security stance established in Phase 2.2: legal documents contain
sensitive information (PII, financial terms), and persistent storage of
raw document text creates unnecessary risk.

Entries have a configurable TTL (default 30 minutes). Stale entries are
lazily evicted on each access and also cleaned up via an explicit sweep
function that can be called periodically.

For hackathon/demo scope, a simple ``dict`` keyed by UUID is sufficient.
If this were production, it would be replaced with a Redis store or
encrypted server-side sessions — the interface is small enough that
swapping the implementation requires changing only this module.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SESSION_TTL_MINUTES: int = 30
"""How long a document entry stays alive before expiring."""


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

_store: dict[str, dict[str, Any]] = {}
"""
Maps ``document_id`` → session data dict. Each entry has:
  - ``text``: The full plain-text content of the analyzed document.
  - ``doc_type``: The classified ``DocumentType`` value (as a string).
  - ``created_at``: UTC datetime when the entry was created.
"""


def create_session(text: str, doc_type: str) -> str:
    """
    Store document text and return a new ``document_id``.

    Args:
        text: The full extracted/pasted document text.
        doc_type: The classified document type (string value of the enum).

    Returns:
        A UUID string that identifies this session entry.
    """
    document_id = str(uuid.uuid4())
    _store[document_id] = {
        "text": text,
        "doc_type": doc_type,
        "created_at": datetime.now(timezone.utc),
    }
    logger.info(
        "Session created: document_id=%s, doc_type=%s, text_chars=%d",
        document_id,
        doc_type,
        len(text),
    )
    # Lazy cleanup: sweep stale entries whenever we create a new one.
    # This keeps the store bounded without a background thread.
    sweep_expired()
    return document_id


def get_session(document_id: str) -> dict[str, Any] | None:
    """
    Retrieve a session entry by ``document_id``.

    Returns ``None`` if the entry does not exist or has expired.
    Expired entries are deleted lazily on access.

    Args:
        document_id: The UUID returned by ``create_session``.

    Returns:
        The session dict (with ``text``, ``doc_type``, ``created_at``) or
        ``None`` if missing/expired.
    """
    entry = _store.get(document_id)
    if entry is None:
        return None

    # Check TTL — delete and return None if expired.
    age = datetime.now(timezone.utc) - entry["created_at"]
    if age > timedelta(minutes=SESSION_TTL_MINUTES):
        logger.info(
            "Session expired (age=%s): document_id=%s",
            age,
            document_id,
        )
        del _store[document_id]
        return None

    return entry


def sweep_expired() -> int:
    """
    Remove all expired entries from the store.

    Returns:
        The number of entries removed.
    """
    now = datetime.now(timezone.utc)
    cutoff = timedelta(minutes=SESSION_TTL_MINUTES)
    expired_ids = [
        doc_id
        for doc_id, entry in _store.items()
        if (now - entry["created_at"]) > cutoff
    ]
    for doc_id in expired_ids:
        del _store[doc_id]

    if expired_ids:
        logger.info("Swept %d expired session(s).", len(expired_ids))

    return len(expired_ids)


def clear_all() -> None:
    """
    Clear the entire store. Used in tests to ensure isolation between
    test cases. NOT intended for production use.
    """
    _store.clear()
