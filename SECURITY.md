# ClauseWise — Security Documentation

This document describes the security posture of ClauseWise, a GenAI-powered legal document assistant.
It covers data handling, secrets management, input validation, rate limiting, and known limitations.

---

## Data Handling

### What is processed

ClauseWise processes legal documents (leases, NDAs, employment contracts, terms of service) through:

1. **File upload + OCR** — PDF/JPEG/PNG files are sent to Google Document AI for text extraction.
2. **AI analysis** — Extracted text is sent to Google Gemini for classification, extraction, and summarization.
3. **Translation** — Summary text and risk flags can be translated via Google Cloud Translation API.
4. **Chat Q&A** — Users can ask follow-up questions grounded in the analyzed document.

### Where data lives

| Data | Storage | Lifetime |
|---|---|---|
| Uploaded file bytes | In-memory only | Discarded after OCR extraction (never written to disk) |
| Extracted document text | In-memory session store | 30-minute TTL, then automatically evicted |
| Chat conversation history | Frontend state only | Lost on page refresh (never stored server-side) |
| Analysis results | Frontend state only | Lost on page refresh |

**No data is ever written to disk, a database, or persistent storage.**

The in-memory session store (`core/session_store.py`) holds document text for up to 30 minutes so
the chat endpoint can reference it for follow-up questions. Expired entries are lazily evicted on
access and swept whenever a new session is created.

### What is never logged

- Raw document text or file contents (only metadata: filename, size, detected MIME type)
- Chat questions or answers
- Translation input or output
- Any PII from documents

Server-side logging is limited to:
- Operation metadata (file size, document type, character counts)
- Error categories (not raw exception messages — see Error Sanitization below)
- Session lifecycle events (creation, expiry — IDs only, not content)

---

## Secrets Management

All secrets are loaded exclusively from environment variables via `config.py` (Pydantic `BaseSettings`).

| Secret | Env Var | Purpose |
|---|---|---|
| Gemini API key | `GEMINI_API_KEY` | AI analysis + chat Q&A |
| GCP service account | `GOOGLE_APPLICATION_CREDENTIALS` | Document AI OCR |
| Translation API key | `TRANSLATE_API_KEY` | Cloud Translation API |
| Document AI processor | `DOCAI_PROCESSOR_ID` | Document AI processor resource name |

**No secrets are ever hardcoded in source code.** This has been verified by automated grep scans
for API key patterns (`AIza*`, `sk-*`, `ghp_*`) across the entire repository.

The `.gitignore` excludes:
- `.env`, `.env.local`, `.env.production`
- `credentials.json`, `*-service-account*.json`
- `*.key`, `*.pem`

The `.env.example` file contains placeholder values only (empty strings), never real keys.

---

## Input Validation

Every endpoint validates all inputs before processing:

| Endpoint | Validation |
|---|---|
| `POST /documents/analyze` | `text`: min 1 char, max 500,000 chars |
| `POST /documents/upload` | Empty check → size check (max 10 MB) → magic-byte content check (PDF/JPEG/PNG) |
| `POST /translate` | `text`: min 1, max 50,000 chars; `target_language`: validated against actual supported-languages list |
| `POST /chat` | `question`: min 1, max 2,000 chars; `document_id`: max 100 chars; `history`: max 50 messages, each max 10,000 chars |

### File upload security

- Files are validated **by magic bytes (content), not file extension** — extensions can be trivially spoofed.
- Only PDF (`%PDF`), JPEG (`FF D8 FF`), and PNG (`89 50 4E 47`) are accepted.
- Files exceeding 10 MB are rejected before any external API call.
- File bytes are processed entirely in memory and never written to disk.

---

## Rate Limiting

All endpoints that call external paid APIs are rate-limited to **30 requests per minute per IP address**
using SlowAPI (in-memory storage):

| Endpoint | Rate Limit | Why |
|---|---|---|
| `POST /documents/analyze` | 30/min/IP | Gemini API cost |
| `POST /documents/upload` | 30/min/IP | Document AI + Gemini cost |
| `POST /translate` | 30/min/IP | Translation API cost |
| `POST /chat` | 30/min/IP | Gemini API cost |

Exceeding the limit returns a structured **429 Too Many Requests** response:
```json
{
  "error": "rate_limit_exceeded",
  "detail": "Too many requests. Please wait a moment and try again."
}
```

Not rate-limited: `GET /health`, `GET /translate/languages` (read-only, no external API cost).

---

## CORS Policy

CORS is scoped to known frontend origins (`http://localhost:5173` through `http://localhost:5180`).
It is **not wildcarded** — a wildcard (`*`) would allow any website to call the API, which is
dangerous when processing sensitive legal documents.

Allowed HTTP methods are restricted to `GET` and `POST` (the only methods the API uses).

---

## Error Sanitization

All error responses pass through `core/error_sanitizer.py` before reaching the client. The sanitizer
detects and replaces messages containing:

- File paths (`/Users/...`, `/home/...`, `C:\...`)
- Stack traces (`Traceback (most recent call last)`)
- Python traceback frames (`File "..."`)
- API key fragments (`AIza...`, `sk-...`)

Internal exceptions are logged server-side (metadata only) and replaced with clean, context-appropriate
fallback messages for the client.

---

## Session Store Security

- Session IDs are **UUID v4** (128-bit random) — cryptographically unpredictable.
- There is no enumeration endpoint — you cannot list or discover other sessions.
- Expired sessions (>30 minutes) are deleted on access and swept on new session creation.
- The session store is intentionally ephemeral (in-memory `dict`) — it does not survive server restarts.

---

## Known Limitations

This is a hackathon demo. A production deployment would need:

- **Distributed rate limiting** — The current in-memory limiter only works for single-instance deployments. Production would use Redis-backed rate limiting across multiple server instances.
- **Encrypted session storage** — Document text in the session store is currently held in plaintext in-memory. Production would encrypt it at rest and use a proper session management system (e.g., Redis with TLS).
- **Authentication & authorization** — The API is currently unauthenticated. Production would require user authentication (OAuth2/JWT) and per-user session isolation.
- **HTTPS enforcement** — The dev server uses HTTP. Production must enforce HTTPS for all API traffic and set appropriate security headers (HSTS, CSP, X-Frame-Options).
- **Audit logging** — Production would log access events (who accessed what, when) for compliance, while continuing to exclude raw document content.
