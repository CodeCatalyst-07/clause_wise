/**
 * ClauseWise — React Application Root
 *
 * Assembles the page layout and manages the top-level analysis state.
 * When UploadPanel completes an analysis (via file upload or text paste),
 * it passes the AnalysisResult up here, which then flows down to
 * SummaryView and ClauseList as props.
 *
 * State flow:
 *   UploadPanel → onAnalysisComplete(result) → App state →
 *   → SummaryView(result) + ClauseList(result)
 *
 * The DisclaimerBanner is always visible, never hidden by scroll or state.
 */

import { useEffect, useState } from "react";
import DisclaimerBanner from "./components/DisclaimerBanner";
import UploadPanel from "./components/UploadPanel";
import SummaryView from "./components/SummaryView";
import ClauseList from "./components/ClauseList";
import ChatPanel from "./components/ChatPanel";
import "./styles/App.css";

/** Base URL for the FastAPI backend. Pulled from env so it's never hardcoded. */
const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function App() {
  const [backendStatus, setBackendStatus] = useState("checking…");

  /**
   * Top-level analysis result. Null until the user uploads a document
   * or pastes text. Once set, SummaryView and ClauseList render real data
   * instead of placeholders.
   */
  const [analysisResult, setAnalysisResult] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => setBackendStatus(data.status))
      .catch(() => setBackendStatus("unreachable"));
  }, []);

  return (
    <div className="app">
      {/* Skip link — keyboard users can jump past the header to the main content */}
      <a href="#main-content" className="skip-link">Skip to main content</a>
      {/* ---- Header ---- */}
      <header className="app-header">
        <div className="app-title-wrapper">
          <span className="app-emblem" aria-hidden="true">⚖️</span>
          <h1 className="app-title">ClauseWise</h1>
        </div>
        <p className="app-subtitle">AI-Powered Legal Document Assistant • Redline & Covenants Docket</p>
      </header>

      {/* ---- Legal disclaimer — always visible, never scrolled away ---- */}
      <DisclaimerBanner />

      {/* ---- Health-check status badge ---- */}
      <div className="health-check">
        <span>Backend Engine:</span>
        <span
          className={backendStatus === "ok" ? "status-ok" : "status-error"}
        >
          {backendStatus}
        </span>
      </div>

      {/* ---- Upload panel (full width) ---- */}
      <UploadPanel onAnalysisComplete={setAnalysisResult} />

      {/* ---- Results area (only shown after analysis) ---- */}
      {analysisResult && (
        <main id="main-content" className="app-main">
          <SummaryView result={analysisResult} />
          <ClauseList result={analysisResult} />
        </main>
      )}

      {/* ---- Chat panel (shows below results, receives documentId) ---- */}
      <ChatPanel documentId={analysisResult?.document_id || null} />
    </div>
  );
}

export default App;
