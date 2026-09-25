# ⚖️ ClauseWise

**A GenAI-powered legal document assistant** that helps everyday users understand their legal documents — leases, NDAs, employment contracts, and terms of service — without needing a law degree.

Upload or paste a document, and ClauseWise instantly classifies it, extracts key clauses, flags risks, generates a plain-English summary, and lets you ask follow-up questions in a grounded chat — all in your preferred language.

> ⚠️ **Responsible Use:** This tool provides general legal information, not legal advice. Consult a licensed attorney for your specific situation.

---

## Problem Statement

Legal documents are long, dense, and full of jargon. Most people sign leases, NDAs, and employment contracts without fully understanding what they agree to — exposing themselves to hidden fees, auto-renewal clauses, and one-sided termination conditions.

**ClauseWise addresses this by providing:**

- **Document simplification** — AI-generated plain-English summaries written at an 8th-grade reading level
- **Risk highlighting** — automatic flagging of clauses that may need the user's attention (e.g., auto-renewal, liability limitations, non-compete restrictions)
- **Structured extraction** — key fields (parties, dates, amounts, obligations) pulled into a scannable format
- **Document-grounded Q&A** — ask follow-up questions with answers strictly grounded in the actual document text, not hallucinated
- **Attorney preparation** — auto-generated "questions to ask a lawyer" based on identified risk flags, helping users prepare for a legal consultation
- **Multilingual accessibility** — summaries and risk flags translatable to 100+ languages via the Cloud Translation API

All outputs stay descriptive and informational — ClauseWise never gives legal advice, and explicitly redirects advice-seeking questions to consulting a licensed attorney.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    React Frontend                    │
│  UploadPanel → SummaryView → ClauseList → ChatPanel │
│  TranslateDropdown (shared)  DisclaimerBanner       │
└──────────────────────┬──────────────────────────────┘
                       │ REST API (JSON / multipart)
┌──────────────────────▼──────────────────────────────┐
│                  FastAPI Backend                      │
│                                                      │
│  /documents/upload ──► Document AI (OCR) ──┐         │
│  /documents/analyze ───────────────────────┤         │
│                                            ▼         │
│                                  ┌─────────────────┐ │
│                                  │  Gemini Pipeline │ │
│                                  │  1. Classify     │ │
│                                  │  2. Extract      │ │
│                                  │  3. Summarize    │ │
│                                  │  4. Suggest Qs   │ │
│                                  └────────┬────────┘ │
│                                           ▼          │
│  /chat ──► Session Store ──► Gemini (grounded Q&A)   │
│  /translate ──► Cloud Translation API                │
│                                                      │
│  Rate Limiter (30/min/IP)  Error Sanitizer           │
│  Session Store (in-memory, 30min TTL)                │
└──────────────────────────────────────────────────────┘
```

### Google Cloud Services

| Service | Purpose | Why this service |
|---|---|---|
| **Gemini API** | Classification, extraction, summarization, chat Q&A | Structured JSON output (schema-constrained) ensures reliable parsing; multi-step prompting enables the classify→extract→summarize pipeline |
| **Document AI** | OCR for PDF/image uploads | Production-grade OCR that handles scanned documents, handwriting, and complex layouts — critical for real-world legal documents that aren't always digital-native |
| **Cloud Translation API** | Multilingual accessibility | Supports 100+ languages dynamically (the frontend populates its dropdown from the API, not a hardcoded list), making the tool accessible to non-English speakers |

---

## Features

| Feature | Endpoint | Description |
|---|---|---|
| File upload + OCR | `POST /documents/upload` | Upload PDF/JPEG/PNG → Document AI OCR → full analysis pipeline |
| Text analysis | `POST /documents/analyze` | Paste raw text → classification + extraction + summary |
| Document-grounded chat | `POST /chat` | Ask follow-up questions grounded in the document text |
| Translation | `POST /translate` | Translate summaries and risk flags to 100+ languages |
| Language list | `GET /translate/languages` | Dynamic list of supported languages for the frontend |
| Health check | `GET /health` | Backend connectivity check |

---

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, Uvicorn
- **Frontend:** React 19 (Vite), vanilla CSS, Inter font
- **AI/ML Services:** Google Gemini 2.0 Flash, Google Document AI, Google Cloud Translation
- **Testing:** pytest (backend, 63 tests), Vitest + Testing Library (frontend, 8 tests)
- **Security:** SlowAPI rate limiting, magic-byte file validation, error sanitization
- **Accessibility:** eslint-plugin-jsx-a11y, WCAG AA contrast, skip-link, ARIA landmarks

---

## Setup Instructions

### Prerequisites

- Python 3.11 or later
- Node.js 18 or later & npm
- A Google Cloud project with Gemini, Document AI, and Translation APIs enabled

### 1. Clone & configure secrets

```bash
git clone <repo-url> && cd clausewise

# Backend — copy .env template and fill in your API keys
cp backend/.env.example backend/.env
# Edit backend/.env:
#   GEMINI_API_KEY=your-gemini-key
#   GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
#   DOCAI_PROCESSOR_ID=projects/.../locations/.../processors/...
#   TRANSLATE_API_KEY=your-translation-key

# Frontend — copy .env template (defaults are fine for local dev)
cp frontend/.env.example frontend/.env
```

### 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# API is now at http://localhost:8000
# Health check: http://localhost:8000/health
# API docs: http://localhost:8000/docs
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
# App is now at http://localhost:5173
```

### 4. Run tests

```bash
# Backend (63 tests)
cd backend && python -m pytest tests/ -v

# Frontend (8 tests)
cd frontend && npm test

# Accessibility lint
cd frontend && npm run lint:a11y
```

---

## How This Maps to the Grading Criteria

### 1. Code Quality

- **Schema registry pattern** — `models/schemas.py` maps each `DocumentType` to a Pydantic extraction schema, so adding a new document type is a single schema class + registry entry
- **Lazy client singletons** — each service (`gemini_service`, `docai_service`, `translate_service`) initializes its API client on first use, not at import time
- **Docstrings throughout** — every module, function, and class has a descriptive docstring explaining *why*, not just *what*
- **Modular router/service split** — routers handle HTTP concerns; services handle API logic; models handle validation

→ See: [`gemini_service.py`](backend/app/services/gemini_service.py), [`schemas.py`](backend/app/models/schemas.py), [`documents.py`](backend/app/routers/documents.py)

### 2. Security

- Secrets loaded from env vars only, never hardcoded (verified by automated grep scans)
- Files validated by magic bytes, not extension (prevents spoofing)
- Uploaded files processed in-memory only, never written to disk
- Error messages sanitized to strip file paths, stack traces, and API key fragments
- Rate limiting (30 req/min/IP) on all paid-API endpoints
- CORS scoped to known frontend origins (not wildcarded)
- Input validation with max_length on all free-text fields

→ See: [`SECURITY.md`](SECURITY.md)

### 3. Efficiency

- **Cheapest-first validation** — empty check → size check → magic-byte check, before any expensive API call
- **Rate limiting** — prevents cost overrun from API abuse
- **Shared translation hook** — `useTranslation.js` caches the language list and avoids duplicate API calls across components
- **Session store lazy sweep** — expired entries are cleaned up lazily on access and on new session creation, not via a background timer

→ See: [`validators.py`](backend/app/core/validators.py), [`useTranslation.js`](frontend/src/hooks/useTranslation.js)

### 4. Testing

- **71 total tests** (63 backend + 8 frontend), all mocked — zero network calls
- **Backend:** pytest with `unittest.mock.patch` — covers happy paths, error fallbacks, validation, rate limiting, security
- **Frontend:** Vitest + Testing Library — covers loading states, error display, component rendering, chat flow

```bash
# Run the full suite
cd backend && python -m pytest tests/ -v    # 63 tests, ~0.5s
cd frontend && npm test                      # 8 tests, ~0.5s
```

→ See: [`tests/`](backend/tests/), [`components.test.jsx`](frontend/src/test/components.test.jsx)

### 5. Accessibility

- **WCAG AA contrast** — all text/background combinations verified ≥4.5:1 ratio
- **Don't rely on color alone** — risk flags use a visible "⚠ Risk:" text prefix + icon, not just a warning-yellow border
- **ARIA landmarks** — `aria-label`, `aria-live`, `role="status"`, `role="alert"`, `role="log"` on all dynamic regions
- **Keyboard navigation** — skip-link, tab-accessible drop zone, Enter/Space activation, visible `:focus-visible` rings on all interactive elements
- **Repeatable lint** — `eslint-plugin-jsx-a11y` configured with recommended rules; run `npm run lint:a11y`

→ See: [`index.css`](frontend/src/index.css) (tokens + focus rings), [`eslint.config.js`](frontend/eslint.config.js)

### 6. Google Services Integration

| Service | Integration Point | Structured Output? |
|---|---|---|
| **Gemini API** | Classification, extraction (schema-constrained JSON), summarization, suggested questions, chat Q&A | ✅ `response_mime_type` + `response_schema` on classify/extract/suggest steps |
| **Document AI** | OCR for PDF/JPEG/PNG uploads | N/A (returns extracted text) |
| **Cloud Translation** | Translate summaries, risk flags; dynamic language list for frontend dropdown | N/A (returns translated text + language list) |

→ See: [`gemini_service.py`](backend/app/services/gemini_service.py), [`docai_service.py`](backend/app/services/docai_service.py), [`translate_service.py`](backend/app/services/translate_service.py)

### 7. Problem Statement Alignment

| Problem Statement Need | ClauseWise Feature |
|---|---|
| *Simplify complex documents* | Plain-English summaries at 8th-grade reading level |
| *Highlight risks and obligations* | Automatic risk flag extraction with visual "⚠ Risk:" labels; single-document scope (cross-document comparison is a known limitation — see below) |
| *Q&A on documents* | Document-grounded chat with advice redirection |
| *Help users prepare for a legal professional* | Chat proactively suggests 2–3 specific questions to ask an attorney when risky or important clauses are discussed |
| *Next-steps guidance* | Risk flags + attorney-prep questions give users concrete talking points, not just passive deflection |
| *Multilingual access* | Translation to 100+ languages via Cloud Translation API |
| *Responsible AI* | Disclaimer in every response + inline near chat input; never uses advisory language |

---

## Responsible Use

ClauseWise is designed to **inform, not advise**:

- Every API response and UI panel includes the legal disclaimer
- AI summaries use only factual, descriptive language ("the document states X"), never advisory language ("you should X")
- Advice-seeking chat questions (e.g., "should I sign this?") are redirected: the model provides relevant document context, then explicitly suggests consulting a licensed attorney
- Raw document text is never logged or persisted — only metadata (file size, document type)

---

## Known Limitations

- **Single-document scope** — only one document can be analyzed per session; there's no multi-document comparison feature
- **No persistent chat history** — conversation state lives in the browser and is lost on page refresh
- **In-memory session store** — document text is held in-memory with a 30-minute TTL; this does not survive server restarts and is not suitable for production scale
- **No user authentication** — the API is unauthenticated; a production deployment would require OAuth2/JWT and per-user session isolation

---

## License

This project is for educational and hackathon purposes.
