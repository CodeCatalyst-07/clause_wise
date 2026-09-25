/**
 * useTranslation — Shared hook for translation dropdown logic.
 *
 * Used by both SummaryView and ClauseList to avoid duplicating the
 * language-fetching and text-translation logic. Provides:
 *   • A list of supported languages (fetched once from the backend).
 *   • A function to translate text to a selected language.
 *   • Loading/error state management.
 *
 * The hook caches the language list in module-level state so it's only
 * fetched once, even if multiple components mount the hook.
 */

import { useState, useEffect, useRef, useCallback } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

/**
 * Module-level cache for languages. Shared across all hook instances
 * so we only fetch GET /translate/languages once.
 */
let cachedLanguages = null;
let languageFetchPromise = null;

/**
 * Fetch the supported language list, using a shared cache.
 * @returns {Promise<Array<{language: string, name: string}>>}
 */
async function fetchLanguages() {
  if (cachedLanguages) return cachedLanguages;
  if (languageFetchPromise) return languageFetchPromise;

  languageFetchPromise = fetch(`${API_BASE}/translate/languages`)
    .then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .then((data) => {
      cachedLanguages = data;
      return data;
    })
    .catch((err) => {
      languageFetchPromise = null; // allow retry on next mount
      throw err;
    });

  return languageFetchPromise;
}

/**
 * Custom hook for translating text via the backend /translate endpoint.
 *
 * @param {string} originalText — the English text to potentially translate
 * @returns {{
 *   languages: Array<{language: string, name: string}>,
 *   selectedLang: string,
 *   setSelectedLang: function,
 *   translatedText: string|null,
 *   isTranslating: boolean,
 *   translationError: string|null,
 *   isOriginal: boolean,
 * }}
 */
export function useTranslation(originalText) {
  const [languages, setLanguages] = useState([]);
  const [selectedLang, setSelectedLang] = useState("original");
  const [translatedText, setTranslatedText] = useState(null);
  const [isTranslating, setIsTranslating] = useState(false);
  const [translationError, setTranslationError] = useState(null);

  // Track the latest request to avoid race conditions when the user
  // switches languages rapidly.
  const latestRequestRef = useRef(0);

  // Fetch languages on mount (uses module-level cache)
  useEffect(() => {
    fetchLanguages()
      .then(setLanguages)
      .catch(() => {
        /* languages list unavailable — dropdown stays empty */
      });
  }, []);

  // Translate when language selection changes
  const handleLanguageChange = useCallback(
    async (langCode) => {
      setSelectedLang(langCode);
      setTranslationError(null);

      if (langCode === "original" || !originalText) {
        setTranslatedText(null);
        return;
      }

      const requestId = ++latestRequestRef.current;
      setIsTranslating(true);

      try {
        const res = await fetch(`${API_BASE}/translate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: originalText,
            target_language: langCode,
          }),
        });

        // Only update if this is still the latest request
        if (requestId !== latestRequestRef.current) return;

        if (!res.ok) {
          const errData = await res.json().catch(() => null);
          throw new Error(
            errData?.detail?.detail || `Translation failed (HTTP ${res.status})`
          );
        }

        const data = await res.json();
        setTranslatedText(data.translated_text);
      } catch (err) {
        if (requestId === latestRequestRef.current) {
          setTranslationError(err.message);
          setTranslatedText(null);
        }
      } finally {
        if (requestId === latestRequestRef.current) {
          setIsTranslating(false);
        }
      }
    },
    [originalText]
  );

  return {
    languages,
    selectedLang,
    setSelectedLang: handleLanguageChange,
    translatedText,
    isTranslating,
    translationError,
    isOriginal: selectedLang === "original",
  };
}
