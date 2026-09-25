# ClauseWise — Frontend

The modern React 19 interface for **ClauseWise**, designed with an archival **"Legal Redline Dossier"** visual language.

## Architecture

- **React 19** with **Vite**
- **Vanilla CSS** with a comprehensive token system (`src/index.css`)
- **Typography:**
  - *Newsreader* (Google Fonts serif) for legal headings, summaries, and document excerpts
  - *JetBrains Mono* for clause tags, metadata stamps, and badges
  - *Inter* for functional UI controls, buttons, and inputs
- **Design Tokens:** Archival vellum reading cards, ink-navy binder chrome, redline danger badges, amber warning accents
- **Accessibility:** Full WCAG AA contrast compliance, keyboard focus rings, skip navigation link, ARIA landmarks and live regions

## Development

```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Run Vitest component tests
npm test

# Run accessibility linter
npm run lint:a11y

# Build production bundle
npm run build
```

## Environment Variables

- `VITE_API_BASE_URL`: URL to the ClauseWise backend (e.g. `http://localhost:8000` for local development, or your deployed Cloud Run/Render API URL).
