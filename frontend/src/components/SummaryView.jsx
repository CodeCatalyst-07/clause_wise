/**
 * SummaryView — Renders the AI-generated document summary.
 *
 * Displays:
 *   • The detected document type in plain language
 *   • The plain-English summary from the Gemini pipeline
 *   • A language dropdown (via useTranslation hook) to translate the summary
 *
 * The DisclaimerBanner is rendered at the App level, not here, so it
 * always stays visible regardless of this component's scroll position.
 */

import { useTranslation } from "../hooks/useTranslation";
import TranslateDropdown from "./TranslateDropdown";
import "../styles/SummaryView.css";

/**
 * Human-readable labels for the DocumentType enum values.
 * Displayed as "Detected: Lease Agreement" instead of raw "LEASE".
 */
const DOC_TYPE_LABELS = {
  LEASE: "Lease Agreement",
  NDA: "Non-Disclosure Agreement",
  TERMS_OF_SERVICE: "Terms of Service",
  EMPLOYMENT_CONTRACT: "Employment Contract",
  OTHER: "Legal Document",
};

function SummaryView({ result }) {
  const {
    languages,
    selectedLang,
    setSelectedLang,
    translatedText,
    isTranslating,
    translationError,
    isOriginal,
  } = useTranslation(result?.summary || "");

  if (!result) return null;

  const docTypeLabel = DOC_TYPE_LABELS[result.doc_type] || "Legal Document";
  const displayText = isOriginal ? result.summary : (translatedText || result.summary);

  return (
    <section className="panel summary-view" aria-label="Document summary">
      <h2>📋 Document Summary</h2>

      {/* Detected document type badge */}
      <div className="doc-type-badge" aria-label={`Detected document type: ${docTypeLabel}`}>
        <span className="badge-label">Detected:</span>
        <span className="badge-value">{docTypeLabel}</span>
      </div>

      {/* Translation dropdown */}
      <TranslateDropdown
        languages={languages}
        selectedLang={selectedLang}
        onChange={setSelectedLang}
        isTranslating={isTranslating}
        error={translationError}
        label="Translate summary"
      />

      {/* Summary text — supports markdown-ish line breaks */}
      <div className="summary-content" aria-live="polite">
        {displayText.split("\n").map((line, i) => (
          <p key={i} className={line.startsWith("•") || line.startsWith("-") ? "summary-bullet" : "summary-paragraph"}>
            {line}
          </p>
        ))}
      </div>
    </section>
  );
}

export default SummaryView;
