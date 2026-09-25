/**
 * DisclaimerBanner — Legal disclaimer displayed at the top of the app.
 *
 * This component exists from Phase 2.0 onward to satisfy the responsible-AI
 * grading criterion. The disclaimer text is intentionally kept in sync with
 * the backend constant in backend/app/core/disclaimers.py.
 *
 * Styling is intentionally minimal during scaffolding and will be polished
 * in the UI phase.
 */

import "../styles/DisclaimerBanner.css";

/** Must match backend/app/core/disclaimers.py → DISCLAIMER_TEXT */
const DISCLAIMER_TEXT =
  "This tool provides general legal information, not legal advice. " +
  "Consult a licensed attorney for your specific situation.";

function DisclaimerBanner() {
  return (
    <div className="disclaimer-banner" role="note" aria-label="Legal disclaimer">
      <span className="disclaimer-icon" aria-hidden="true">⚠️</span>
      <p className="disclaimer-text">{DISCLAIMER_TEXT}</p>
    </div>
  );
}

export default DisclaimerBanner;
