/**
 * UploadPanel — Document upload and text-paste interface.
 *
 * Supports two input modes:
 *   1. File upload (PDF/JPG/PNG) → POST /documents/upload (multipart)
 *   2. Text paste → POST /documents/analyze (JSON)
 *
 * State management rationale:
 *   • `isLoading` drives both the spinner and the disabled state of controls,
 *     preventing double-submissions during the multi-second AI pipeline.
 *   • `error` is set from the backend's structured ErrorResponse so users
 *     see the *specific* validation/service message, not a generic fallback.
 *   • On success, the AnalysisResult is passed to the parent via the
 *     `onAnalysisComplete` callback.
 */

import { useState, useRef } from "react";
import "../styles/UploadPanel.css";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

/**
 * Extract a human-readable error message from a backend error response.
 * The backend returns errors in `{ detail: { detail: "...", error: "..." } }`
 * or `{ detail: [{ msg: "..." }] }` (Pydantic validation) shape.
 */
function extractErrorMessage(data) {
  if (data?.detail?.detail) return data.detail.detail;
  if (typeof data?.detail === "string") return data.detail;
  if (Array.isArray(data?.detail)) return data.detail.map((d) => d.msg).join("; ");
  return "An unexpected error occurred. Please try again.";
}

function UploadPanel({ onAnalysisComplete }) {
  const [mode, setMode] = useState("upload"); // "upload" | "text"
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [pasteText, setPasteText] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [selectedFileName, setSelectedFileName] = useState(null);
  const fileInputRef = useRef(null);

  /**
   * Handle file upload via POST /documents/upload (multipart/form-data).
   */
  const handleFileUpload = async (file) => {
    if (!file) return;

    setSelectedFileName(file.name);
    setError(null);
    setIsLoading(true);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${API_BASE}/documents/upload`, {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(extractErrorMessage(data));
      }

      onAnalysisComplete(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Handle text analysis via POST /documents/analyze (JSON body).
   */
  const handleTextAnalyze = async () => {
    if (!pasteText.trim()) {
      setError("Please enter some document text to analyze.");
      return;
    }

    setError(null);
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/documents/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: pasteText }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(extractErrorMessage(data));
      }

      onAnalysisComplete(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // ---- Drag-and-drop handlers ----
  const handleDragOver = (e) => {
    e.preventDefault();
    setDragActive(true);
  };
  const handleDragLeave = () => setDragActive(false);
  const handleDrop = (e) => {
    e.preventDefault();
    setDragActive(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileUpload(file);
  };

  return (
    <section className="panel upload-panel" aria-label="Document upload">
      <h2>📄 Upload Document</h2>

      {/* ---- Mode tabs ---- */}
      <div className="upload-tabs" role="tablist" aria-label="Input mode">
        <button
          role="tab"
          aria-selected={mode === "upload"}
          className={`upload-tab ${mode === "upload" ? "active" : ""}`}
          onClick={() => setMode("upload")}
          disabled={isLoading}
        >
          Upload File
        </button>
        <button
          role="tab"
          aria-selected={mode === "text"}
          className={`upload-tab ${mode === "text" ? "active" : ""}`}
          onClick={() => setMode("text")}
          disabled={isLoading}
        >
          Paste Text
        </button>
      </div>

      {/* ---- File upload mode ---- */}
      {mode === "upload" && (
        <div
          className={`drop-zone ${dragActive ? "drag-active" : ""}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => !isLoading && fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          aria-label="Click or drag-and-drop a PDF, JPEG, or PNG file to upload"
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              fileInputRef.current?.click();
            }
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png"
            className="file-input-hidden"
            onChange={(e) => handleFileUpload(e.target.files?.[0])}
            disabled={isLoading}
            aria-label="File upload input"
          />
          <div className="drop-zone-content">
            <span className="drop-icon" aria-hidden="true">📁</span>
            <p className="drop-text">
              {selectedFileName
                ? selectedFileName
                : "Drop a file here or click to browse"}
            </p>
            <p className="drop-hint">PDF, JPEG, or PNG • Max 10 MB</p>
          </div>
        </div>
      )}

      {/* ---- Text paste mode ---- */}
      {mode === "text" && (
        <div className="text-input-area">
          <label htmlFor="paste-text-input" className="sr-only">
            Paste your legal document text
          </label>
          <textarea
            id="paste-text-input"
            className="paste-textarea"
            placeholder="Paste your legal document text here…"
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            disabled={isLoading}
            rows={8}
            aria-label="Legal document text input"
          />
          <button
            className="analyze-btn"
            onClick={handleTextAnalyze}
            disabled={isLoading || !pasteText.trim()}
            aria-label="Analyze pasted text"
          >
            {isLoading ? "Analyzing…" : "Analyze Document"}
          </button>
        </div>
      )}

      {/* ---- Loading indicator — announced to screen readers ---- */}
      {isLoading && (
        <div className="upload-loading" aria-live="polite" role="status">
          <div className="spinner" aria-hidden="true" />
          <p>Analyzing document… This may take a few seconds.</p>
        </div>
      )}

      {/* ---- Error display — uses backend's specific error message ---- */}
      {error && (
        <div className="upload-error" aria-live="assertive" role="alert">
          <span aria-hidden="true">❌</span> {error}
        </div>
      )}
    </section>
  );
}

export default UploadPanel;
