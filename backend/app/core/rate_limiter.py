"""
ClauseWise — Rate Limiter Configuration

Provides a shared SlowAPI rate limiter instance used across all routers
that call external paid APIs. This protects both cost (Efficiency) and
abuse potential (Security).

Configuration:
  • Default: 30 requests/minute per IP address.
  • Applies to: /documents/analyze, /documents/upload, /translate, /chat
  • Does NOT apply to: /health, /translate/languages (read-only, no cost)

The limiter uses an in-memory storage backend, appropriate for hackathon
scope. A production deployment would use Redis for distributed rate
limiting across multiple server instances.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# ---------------------------------------------------------------------------
# Shared limiter instance
# ---------------------------------------------------------------------------

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["30/minute"],
    storage_uri="memory://",
)
"""
In-memory rate limiter. Import this in each router and decorate endpoints.

Usage::

    from app.core.rate_limiter import limiter

    @router.post("/endpoint")
    @limiter.limit("30/minute")
    async def my_endpoint(request: Request):
        ...
"""
