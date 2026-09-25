/**
 * TranslateDropdown — Reusable language selector with translation status.
 *
 * Renders a dropdown of supported languages and shows loading/error state.
 * Used by both SummaryView and ClauseList to keep the UI consistent.
 */

import "../styles/TranslateDropdown.css";

/**
 * @param {{
 *   languages: Array<{language: string, name: string}>,
 *   selectedLang: string,
 *   onChange: function,
 *   isTranslating: boolean,
 *   error: string|null,
 *   label: string,
 * }} props
 */
function TranslateDropdown({
  languages,
  selectedLang,
  onChange,
  isTranslating,
  error,
  label = "Translate to",
}) {
  return (
    <div className="translate-dropdown-wrapper">
      <label htmlFor={`lang-select-${label}`} className="translate-label">
        🌐 {label}:
      </label>
      <select
        id={`lang-select-${label}`}
        className="translate-select"
        value={selectedLang}
        onChange={(e) => onChange(e.target.value)}
        disabled={isTranslating}
        aria-label={`${label} language selector`}
      >
        <option value="original">Original (English)</option>
        {languages.map((lang) => (
          <option key={lang.language} value={lang.language}>
            {lang.name}
          </option>
        ))}
      </select>

      {/* Loading indicator — announced to screen readers */}
      {isTranslating && (
        <span className="translate-status" aria-live="polite" role="status">
          Translating…
        </span>
      )}

      {/* Error — announced to screen readers */}
      {error && (
        <span className="translate-error" aria-live="assertive" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

export default TranslateDropdown;
