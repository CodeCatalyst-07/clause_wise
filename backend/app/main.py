"""
ClauseWise — FastAPI Application Entrypoint

This module initializes the FastAPI application instance and wires up
all routers (documents, chat, translate). It also defines the /health
endpoint used to verify the backend is reachable from the frontend.

Security middleware configured here:
  • CORS — scoped to known frontend origins (not wildcarded).
  • Rate limiting — via SlowAPI, to protect paid API costs and prevent abuse.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.core.rate_limiter import limiter
from app.routers import documents, chat, translate

app = FastAPI(
    title="ClauseWise API",
    description="GenAI-powered legal document assistant — backend API",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Rate limiting — protect paid API endpoints from abuse and cost overrun.
# Uses an in-memory per-IP counter (appropriate for hackathon/single-instance).
# A production deployment would use Redis for distributed rate state.
# ---------------------------------------------------------------------------
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """
    Return a structured 429 response when the rate limit is exceeded.
    Matches the ErrorResponse shape used by all other error paths.
    """
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": "Too many requests. Please wait a moment and try again.",
            "disclaimer": "",
        },
    )


# ---------------------------------------------------------------------------
# CORS — scoped to known frontend dev-server origins.
#
# NOT wildcarded (`*`) — this is a deliberate security decision. A wildcard
# would allow any website to make API calls to our backend, which is
# dangerous when the API processes sensitive legal documents.
#
# The React dev server may bind to any port in the 5173–5180 range when
# its preferred port is busy, so we allow the full range. In production
# this should be locked down to the actual deployed frontend domain.
# ---------------------------------------------------------------------------
_ALLOWED_ORIGINS = [
    f"http://localhost:{port}" for port in range(5173, 5181)
]
if settings.allowed_origins:
    if settings.allowed_origins.strip() == "*":
        _ALLOWED_ORIGINS = ["*"]
    else:
        _ALLOWED_ORIGINS.extend([
            origin.strip()
            for origin in settings.allowed_origins.split(",")
            if origin.strip()
        ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers — each feature area gets its own router module.
# ---------------------------------------------------------------------------
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(translate.router)


# ---------------------------------------------------------------------------
# Health-check endpoint — used by the frontend to confirm connectivity and
# by CI/CD pipelines to verify the service is alive.
# Not rate-limited — health checks should always succeed.
# ---------------------------------------------------------------------------
@app.get("/health", tags=["health"])
async def health_check():
    """Return a simple status payload so callers can verify the API is up."""
    return {"status": "ok"}
