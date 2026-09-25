/**
 * ChatPanel — Document-grounded Q&A interface.
 *
 * Lets the user ask follow-up questions about the analyzed document.
 * Answers are grounded in the actual document text via the Gemini API
 * (POST /chat), not generic or hallucinated.
 *
 * State management rationale:
 *   • `messages` is the conversation history displayed in the UI and also
 *     sent as `history` with each request (stateless server).
 *   • `isLoading` disables the input during the multi-second API call.
 *   • `documentId` comes from the parent's AnalysisResult — if null, the
 *     chat input is disabled with a "Upload a document first" message.
 *   • The disclaimer is shown inline near the chat input, where advice-
 *     seeking risk is highest.
 */

import { useState, useRef, useEffect } from "react";
import "../styles/ChatPanel.css";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

/** Disclaimer shown near the chat input (matches backend DISCLAIMER_TEXT). */
const DISCLAIMER_TEXT =
  "This tool provides general legal information, not legal advice. " +
  "Consult a licensed attorney for your specific situation.";

function ChatPanel({ documentId }) {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const messagesEndRef = useRef(null);

  // Auto-scroll to latest message (guarded for test environments where
  // scrollIntoView may not exist in jsdom).
  useEffect(() => {
    if (typeof messagesEndRef.current?.scrollIntoView === "function") {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isLoading]);

  // Reset chat when a new document is analyzed
  useEffect(() => {
    setMessages([]);
    setError(null);
  }, [documentId]);

  const isDisabled = !documentId;

  /**
   * Send a question to POST /chat and append the response to the
   * conversation history.
   */
  const handleSend = async () => {
    const question = inputValue.trim();
    if (!question || isLoading || isDisabled) return;

    // Add user message to history
    const userMessage = { role: "user", content: question };
    const updatedMessages = [...messages, userMessage];
    setMessages(updatedMessages);
    setInputValue("");
    setError(null);
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_id: documentId,
          question,
          history: messages, // send prior history (before this question)
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        const errMsg =
          data?.detail?.detail ||
          (typeof data?.detail === "string" ? data.detail : "Failed to get a response.");
        throw new Error(errMsg);
      }

      // Add assistant response to history
      setMessages([...updatedMessages, { role: "assistant", content: data.answer }]);
    } catch (err) {
      setError(err.message);
      // Remove the user message on failure so they can retry
      setMessages(messages);
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Submit on Enter key (not just the send button).
   */
  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <section className="panel chat-panel" aria-label="Document Q&A chat">
      <h2>💬 Ask a Question</h2>

      {/* ---- Disabled state: no document uploaded ---- */}
      {isDisabled && (
        <p className="chat-disabled-msg">
          Upload and analyze a document first to start asking questions.
        </p>
      )}

      {/* ---- Message history ---- */}
      {!isDisabled && (
        <div className="chat-messages" aria-live="polite" role="log" aria-label="Chat messages">
          {messages.length === 0 && !isLoading && (
            <p className="chat-empty-hint">
              Ask anything about your document — e.g. "What is the rent amount?"
              or "Are there any auto-renewal clauses?"
            </p>
          )}

          {messages.map((msg, i) => (
            <div
              key={i}
              className={`chat-bubble ${msg.role === "user" ? "chat-user" : "chat-assistant"}`}
            >
              <span className="chat-role" aria-hidden="true">
                {msg.role === "user" ? "You" : "ClauseWise"}
              </span>
              <p className="chat-content">{msg.content}</p>
            </div>
          ))}

          {/* Loading indicator */}
          {isLoading && (
            <div className="chat-bubble chat-assistant chat-loading" role="status" aria-live="polite">
              <span className="chat-role" aria-hidden="true">ClauseWise</span>
              <p className="chat-content">
                <span className="typing-dots" aria-label="Thinking">
                  <span>●</span><span>●</span><span>●</span>
                </span>
              </p>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      )}

      {/* ---- Error display ---- */}
      {error && (
        <div className="chat-error" aria-live="assertive" role="alert">
          <span aria-hidden="true">❌</span> {error}
        </div>
      )}

      {/* ---- Disclaimer near chat input (highest advice-seeking risk) ---- */}
      {!isDisabled && (
        <p className="chat-disclaimer" role="note">
          ⚠️ {DISCLAIMER_TEXT}
        </p>
      )}

      {/* ---- Input area ---- */}
      <div className="chat-input-area">
        <label htmlFor="chat-input" className="sr-only">
          Ask a question about your document
        </label>
        <input
          id="chat-input"
          type="text"
          className="chat-input"
          placeholder={isDisabled ? "Upload a document first…" : "Ask about your document…"}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isDisabled || isLoading}
          aria-label="Ask a question about your document"
        />
        <button
          className="chat-send-btn"
          onClick={handleSend}
          disabled={isDisabled || isLoading || !inputValue.trim()}
          aria-label="Send question"
        >
          {isLoading ? "…" : "Send"}
        </button>
      </div>
    </section>
  );
}

export default ChatPanel;
