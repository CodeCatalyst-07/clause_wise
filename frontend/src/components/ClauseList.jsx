/**
 * ClauseList — Renders extracted fields and risk flags.
 *
 * Displays:
 *   • Extracted fields as a labeled list (human-readable labels, not raw keys)
 *   • Risk flags in a visually prominent warning-style section
 *   • A language dropdown to translate risk flags
 *
 * Risk flags are the "smart assistant" output — they should visually stand
 * out, not blend in with neutral extracted fields.
 */

import { useTranslation } from "../hooks/useTranslation";
import TranslateDropdown from "./TranslateDropdown";
import "../styles/ClauseList.css";

/**
 * Human-readable labels for extraction field keys.
 * Maps snake_case API keys to display labels.
 */
const FIELD_LABELS = {
  parties: "Parties",
  rent_amount: "Rent Amount",
  payment_due_date: "Payment Due Date",
  lease_term_start: "Lease Start",
  lease_term_end: "Lease End",
  security_deposit: "Security Deposit",
  maintenance_obligations: "Maintenance",
  termination_conditions: "Termination Conditions",
  notable_restrictions: "Notable Restrictions",
  confidentiality_scope: "Confidentiality Scope",
  duration: "Duration",
  exceptions_to_confidentiality: "Exceptions",
  remedies_for_breach: "Remedies for Breach",
  parties_or_service_name: "Service / Parties",
  data_usage_terms: "Data Usage",
  liability_limitations: "Liability Limitations",
  dispute_resolution_method: "Dispute Resolution",
  cancellation_termination_terms: "Cancellation / Termination",
  role_or_title: "Role / Title",
  compensation: "Compensation",
  non_compete: "Non-Compete",
  benefits: "Benefits",
  key_dates: "Key Dates",
  obligations: "Obligations",
  potential_risks: "Potential Risks",
};

/**
 * Render a single field value. Arrays are displayed as comma-separated lists;
 * empty values are shown as "Not specified".
 */
function FieldValue({ value }) {
  if (Array.isArray(value)) {
    return value.length > 0 ? (
      <ul className="field-list">
        {value.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    ) : (
      <span className="field-empty">Not specified</span>
    );
  }
  return <span>{value || <span className="field-empty">Not specified</span>}</span>;
}

function ClauseList({ result }) {
  // Join risk flags into a single string for translation
  const riskFlagsText = result?.extracted?.risk_flags?.join("\n") || "";

  const {
    languages,
    selectedLang,
    setSelectedLang,
    translatedText,
    isTranslating,
    translationError,
    isOriginal,
  } = useTranslation(riskFlagsText);

  if (!result) return null;

  const { fields } = result.extracted;
  const riskFlags = result.extracted.risk_flags || [];

  // Display translated risk flags (split back from the translated block)
  const displayRiskFlags = isOriginal
    ? riskFlags
    : (translatedText || riskFlagsText).split("\n").filter(Boolean);

  return (
    <section className="panel clause-list" aria-label="Extracted clauses and risk flags">
      <h2>📑 Extracted Clauses</h2>

      {/* ---- Extracted fields ---- */}
      <div className="fields-grid">
        {Object.entries(fields).map(([key, value]) => {
          const label = FIELD_LABELS[key] || key.replace(/_/g, " ");
          return (
            <div key={key} className="field-item">
              <dt className="field-label">{label}</dt>
              <dd className="field-value">
                <FieldValue value={value} />
              </dd>
            </div>
          );
        })}
      </div>

      {/* ---- Risk flags — visually distinct warning section ---- */}
      {riskFlags.length > 0 && (
        <div className="risk-flags-section" aria-label="Risk flags">
          <h3 className="risk-flags-title">⚠️ Risk Flags</h3>
          <p className="risk-flags-subtitle">
            Clauses that may need your attention
          </p>

          {/* Translation dropdown for risk flags */}
          <TranslateDropdown
            languages={languages}
            selectedLang={selectedLang}
            onChange={setSelectedLang}
            isTranslating={isTranslating}
            error={translationError}
            label="Translate risk flags"
          />

          <ul className="risk-flags-list" aria-live="polite">
            {displayRiskFlags.map((flag, i) => (
              <li key={i} className="risk-flag-item">
                <span className="risk-flag-icon" aria-hidden="true">🔸</span>
                <span className="risk-flag-label">Risk:</span>
                {flag}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ---- Suggested questions for a lawyer — proactive preparation ---- */}
      {result.suggested_questions && result.suggested_questions.length > 0 && (
        <div className="suggested-questions-section" aria-label="Suggested questions for a lawyer">
          <h3 className="suggested-questions-title">💬 Questions to Ask a Lawyer</h3>
          <p className="suggested-questions-subtitle">
            Based on the risk flags above, here are questions you could bring to
            a licensed attorney:
          </p>
          <ol className="suggested-questions-list">
            {result.suggested_questions.map((q, i) => (
              <li key={i} className="suggested-question-item">{q}</li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}

export default ClauseList;
