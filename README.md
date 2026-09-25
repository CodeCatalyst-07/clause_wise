# ⚖️ ClauseWise

**A GenAI-powered legal document assistant** that helps everyday users understand complex legal documents — leases, NDAs, employment contracts, and terms of service — without needing a law degree.

Upload or paste a document, and ClauseWise instantly classifies it, extracts key clauses, flags risks, generates a plain-English summary, and lets you ask follow-up questions in a grounded chat — all in your preferred language.

> ⚠️ **Responsible Use:** This tool provides general legal information, not legal advice. Consult a licensed attorney for your specific situation.

---

## Problem Statement

Legal documents are long, dense, and full of jargon. Most people sign leases, NDAs, and employment contracts without fully understanding what they agree to — exposing themselves to hidden fees, auto-renewal clauses, and one-sided termination conditions.

**ClauseWise addresses this by providing:**

- **Document simplification** — AI-generated plain-English summaries written at an accessible 8th-grade reading level
- **Risk highlighting** — automatic flagging of clauses that require scrutiny (auto-renewal penalties, liability waivers, non-compete clauses, indemnification traps)
- **Structured extraction** — key fields (parties, dates, financial amounts, obligations) pulled into clean, scannable case files
- **Document-grounded Q&A** — ask follow-up questions with answers strictly grounded in the document text, not hallucinated
- **Attorney preparation** — auto-generated "questions to ask a lawyer" based on identified risk flags, helping users prepare for a legal consultation
- **Multilingual accessibility** — summaries and risk flags translatable to 100+ languages via the Cloud Translation API

All outputs stay descriptive and informational — ClauseWise never gives legal advice, and explicitly redirects advice-seeking questions to consulting a licensed attorney.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              React Frontend (Vite SPA)              │
│  "Legal Redline Dossier" Design (Newsreader+Inter) │
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
│  Rate Limiter (SlowAPI)    Error Sanitizer           │
│  Session Store (in-memory, 30min TTL)                │
│  Configurable CORS (ALLOWED_ORIGINS)                 │
└──────────────────────────────────────────────────────┘
```

### Google Cloud Services

| Service | Purpose | Why this service |
|---|---|---|
| **Gemini API** | Classification, extraction, summarization, attorney Qs, chat Q&A | Structured JSON output (`response_mime_type="application/json"` + Pydantic schema constraints) guarantees reliable extraction; resilient fallback across Flash models (`gemini-2.5-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`). |
| **Document AI** | OCR for PDF/image uploads | Production-grade OCR handling complex layouts, scanned PDFs, and handwriting — critical for real-world legal documents. |
| **Cloud Translation API** | Multilingual accessibility | Dynamically populates supported languages (100+ languages) and delivers translations for non-English speakers. |

---

## Features

| Feature | Endpoint | Description |
|---|---|---|
| **File upload + OCR** | `POST /documents/upload` | Upload PDF/JPEG/PNG → Document AI OCR → full analysis pipeline |
| **Text analysis** | `POST /documents/analyze` | Paste raw text → classification + extraction + plain-English summary |
| **Document-grounded chat** | `POST /chat` | Ask follow-up questions grounded strictly in the analyzed document |
| **Attorney preparation** | `POST /documents/analyze` & `/chat` | Proactively suggests 2–3 questions to bring to a lawyer for flagged risks |
| **Translation** | `POST /translate` | Translate summaries and risk flags to 100+ supported languages |
| **Language list** | `GET /translate/languages` | Dynamic list of supported languages populated from the API |
| **Health check** | `GET /health` | Health check for container orchestrators and monitoring |

---

## Tech Stack & Design System

- **Backend:** Python 3.11+, FastAPI, Uvicorn, SlowAPI (rate limiting), Pydantic Settings
- **Frontend:** React 19, Vite, Vanilla CSS tokens, ESLint + A11y
- **Design System ("Legal Redline Dossier"):**
  - **Typography:** *Newsreader* (editorial legal serif for headings & excerpts), *JetBrains Mono* (monospaced metadata & clause stamps), *Inter* (functional UI controls)
  - **Palette:** Archival vellum reading cards (`#f5f2eb`), deep ink-navy binder chrome (`#090e17` / `#111a26`), redline danger accents (`#dc2626`), legal gold focus rings (`#d97706`)
  - **Accessibility:** WCAG AA contrast ratio compliance, visible keyboard focus indicators, screen reader ARIA landmarks
- **AI/ML:** Google Gemini (Flash series with resilient fallback), Google Document AI, Google Cloud Translation
- **Testing:** pytest (backend, 64 tests), Vitest + Testing Library (frontend, 8 tests)
- **Deployment:** Dockerfile for containerization, Vercel SPA configuration, configurable CORS

---

## Quickstart (Local Development)

### Prerequisites

- Python 3.11 or later
- Node.js 18 or later & npm
- A Google Cloud project with Gemini, Document AI, and Cloud Translation APIs enabled

### 1. Clone & Configure Secrets

```bash
git clone https://github.com/CodeCatalyst-07/clause_wise.git
cd clause_wise

# Backend configuration
cp backend/.env.example backend/.env
# Edit backend/.env with your API keys:
#   GEMINI_API_KEY=your_gemini_key
#   GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
#   DOCAI_PROCESSOR_ID=projects/.../locations/.../processors/...
#   TRANSLATE_API_KEY=your_translation_key

# Frontend configuration (default points to http://localhost:8000)
cp frontend/.env.example frontend/.env
```

### 2. Start the Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- API root: `http://localhost:8000`
- Interactive API docs (Swagger): `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### 3. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```
- Web application: `http://localhost:5173`

---

## Testing & Verification

The project includes an automated test suite across backend and frontend with zero external network dependencies:

```bash
# Backend test suite (64 tests: routers, OCR, rate limiting, sanitization, schemas)
cd backend && source .venv/bin/activate
pytest -v

# Frontend component & integration test suite (8 tests)
cd frontend
npm test

# Accessibility audit (zero errors, WCAG AA compliance)
npm run lint:a11y

# Production bundle validation
npm run build
```

---

## Deployment Guide

### Option A: Google Cloud Run (Backend) + Vercel (Frontend) — Recommended

#### 1. Deploy Backend to Google Cloud Run
ClauseWise includes a production [backend/Dockerfile](backend/Dockerfile) ready for Cloud Run:

```bash
cd backend
gcloud run deploy clausewise-api \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY="YOUR_KEY",TRANSLATE_API_KEY="YOUR_KEY",DOCAI_PROCESSOR_ID="YOUR_PROCESSOR_ID",ALLOWED_ORIGINS="https://YOUR-APP.vercel.app"
```
Copy the generated Cloud Run URL (e.g. `https://clausewise-api-xyz.a.run.app`).

#### 2. Deploy Frontend to Vercel
1. Import `CodeCatalyst-07/clause_wise` into [Vercel](https://vercel.com).
2. Set **Root Directory** to `frontend`.
3. Add Environment Variable:
   - `VITE_API_BASE_URL`: `https://clausewise-api-xyz.a.run.app`
4. Click **Deploy**.

---

### Option B: Render (Full-Stack Free Tier)

1. **Deploy Backend Web Service:**
   - Connect repo on [Render](https://render.com) → New **Web Service**.
   - Root Directory: `backend`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Add Environment Variables: `GEMINI_API_KEY`, `TRANSLATE_API_KEY`, `DOCAI_PROCESSOR_ID`, `ALLOWED_ORIGINS`
2. **Deploy Frontend:**
   - Deploy as a **Static Site** on Render or on **Vercel** with `VITE_API_BASE_URL` pointing to your Render backend.

---

### Option C: Run with Docker Locally

```bash
cd backend
docker build -t clausewise-backend .
docker run -p 8000:8000 --env-file .env clausewise-backend
```

---

## How This Maps to the Hackathon Grading Criteria

### 1. Code Quality
- **Schema registry pattern** — [`schemas.py`](backend/app/models/schemas.py) maps each document type to a Pydantic extraction schema.
- **Lazy client singletons** — [`gemini_service.py`](backend/app/services/gemini_service.py), [`docai_service.py`](backend/app/services/docai_service.py), and [`translate_service.py`](backend/app/services/translate_service.py) initialize API clients on first use with clean dependency injection.
- **Strict typing & documentation** — Every module and router includes comprehensive docstrings and typed request/response contracts.

### 2. Security & Privacy
- **Zero hardcoded credentials** — All secrets loaded strictly from environment variables.
- **In-memory file processing** — Files uploaded to `/documents/upload` are processed in memory and never written to persistent disk.
- **Magic-byte file validation** — Prevents MIME-spoofing attacks on uploads.
- **Error sanitization** — [`error_sanitizer.py`](backend/app/core/error_sanitizer.py) strips file paths, stack traces, and API key fragments before returning responses to callers.
- **Rate limiting** — SlowAPI limits paid API endpoints to protect against abuse and billing runaways.
- **Origin-locked CORS** — Strict origins enforced with production override support via `ALLOWED_ORIGINS`.

### 3. Google Services Integration
- **Gemini API:** Multi-step pipeline with strict JSON schema constraints and automatic model fallback across Flash variants.
- **Document AI:** Handles complex multi-column and scanned legal agreements.
- **Cloud Translation:** Dynamically lists and translates content into 100+ languages without hardcoded dictionaries.

### 4. Problem Statement Alignment & Responsible AI
- **Accessible summaries** — Translates complex legal prose to an 8th-grade reading level.
- **Proactive attorney questions** — Generates concrete consultation questions for flagged risks.
- **Legal disclaimers** — Prominent legal disclaimer banners in every panel, response body, and UI view.
- **Advice redirection** — Never provides legal counsel; redirects advisory questions to qualified attorneys.

---

## License

This project is created for educational and hackathon submission purposes.
