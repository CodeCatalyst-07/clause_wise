/**
 * ClauseWise — Frontend Component Tests
 *
 * Covers three key behaviors:
 *   (a) UploadPanel shows loading state during analysis
 *   (b) UploadPanel shows backend error message on failure
 *   (c) SummaryView renders the summary and doc type after analysis
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import UploadPanel from "../components/UploadPanel.jsx";
import SummaryView from "../components/SummaryView.jsx";

// Mock fetch globally for all tests
beforeEach(() => {
  vi.restoreAllMocks();
});

// ═══════════════════════════════════════════════════════════════════════════
// (a) UploadPanel shows loading state
// ═══════════════════════════════════════════════════════════════════════════

describe("UploadPanel loading state", () => {
  it("shows 'Analyzing…' text when text analysis is in flight", async () => {
    // Mock fetch to hang indefinitely (never resolves during this test)
    vi.spyOn(globalThis, "fetch").mockImplementation(
      () => new Promise(() => {})
    );

    const mockCallback = vi.fn();
    render(<UploadPanel onAnalysisComplete={mockCallback} />);

    // Switch to text mode
    const textTab = screen.getByRole("tab", { name: /paste text/i });
    fireEvent.click(textTab);

    // Enter some text
    const textarea = screen.getByLabelText(/legal document text input/i);
    fireEvent.change(textarea, {
      target: { value: "This is a sample lease agreement." },
    });

    // Click analyze
    const analyzeBtn = screen.getByLabelText(/analyze pasted text/i);
    fireEvent.click(analyzeBtn);

    // Loading state should appear
    await waitFor(() => {
      expect(screen.getByText(/analyzing document/i)).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// (b) UploadPanel shows backend error message
// ═══════════════════════════════════════════════════════════════════════════

describe("UploadPanel error display", () => {
  it("shows the backend error message when analysis fails", async () => {
    // Mock fetch to return a backend error response
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => ({
        detail: {
          error: "gemini_service_error",
          detail: "GEMINI_API_KEY is not set. Add it to your .env file.",
          disclaimer: "This tool provides general legal information…",
        },
      }),
    });

    const mockCallback = vi.fn();
    render(<UploadPanel onAnalysisComplete={mockCallback} />);

    // Switch to text mode and enter text
    fireEvent.click(screen.getByRole("tab", { name: /paste text/i }));
    fireEvent.change(screen.getByLabelText(/legal document text input/i), {
      target: { value: "Some contract text" },
    });
    fireEvent.click(screen.getByLabelText(/analyze pasted text/i));

    // Error message from backend should appear
    await waitFor(() => {
      expect(
        screen.getByText(/GEMINI_API_KEY is not set/i)
      ).toBeInTheDocument();
    });

    // Callback should NOT have been called
    expect(mockCallback).not.toHaveBeenCalled();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// (c) SummaryView renders summary and doc type
// ═══════════════════════════════════════════════════════════════════════════

describe("SummaryView rendering", () => {
  it("renders the summary text and detected document type", () => {
    // Mock the language list fetch (useTranslation calls it on mount)
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [
        { language: "es", name: "Spanish" },
        { language: "fr", name: "French" },
      ],
    });

    const mockResult = {
      doc_type: "LEASE",
      summary:
        "This is a one-year residential lease between a landlord and a tenant.",
      extracted: {
        fields: { parties: ["Landlord", "Tenant"] },
        risk_flags: ["Auto-renewal clause"],
      },
      disclaimer: "This tool provides general legal information…",
    };

    render(<SummaryView result={mockResult} />);

    // Doc type label should be displayed
    expect(screen.getByText("Lease Agreement")).toBeInTheDocument();

    // Summary text should be rendered
    expect(
      screen.getByText(/one-year residential lease/i)
    ).toBeInTheDocument();

    // Translation dropdown should be present
    expect(
      screen.getByLabelText(/translate summary language selector/i)
    ).toBeInTheDocument();
  });

  it("returns null when result is not provided", () => {
    const { container } = render(<SummaryView result={null} />);
    expect(container.firstChild).toBeNull();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// (d) ChatPanel — disabled state with no document
// ═══════════════════════════════════════════════════════════════════════════

import ChatPanel from "../components/ChatPanel.jsx";

describe("ChatPanel disabled state", () => {
  it("shows 'Upload a document first' when no documentId", () => {
    render(<ChatPanel documentId={null} />);

    expect(
      screen.getByText(/upload and analyze a document first/i)
    ).toBeInTheDocument();

    // Input should be disabled
    const input = screen.getByLabelText(/ask a question about your document/i);
    expect(input).toBeDisabled();

    // Send button should be disabled
    const sendBtn = screen.getByLabelText(/send question/i);
    expect(sendBtn).toBeDisabled();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// (e) ChatPanel — message send flow + loading state
// ═══════════════════════════════════════════════════════════════════════════

describe("ChatPanel message flow", () => {
  it("shows loading dots after sending a question", async () => {
    // Mock fetch to hang (simulates slow Gemini response)
    vi.spyOn(globalThis, "fetch").mockImplementation(
      () => new Promise(() => {})
    );

    render(<ChatPanel documentId="test-doc-id" />);

    const input = screen.getByLabelText(/ask a question about your document/i);
    fireEvent.change(input, { target: { value: "What is the rent?" } });
    fireEvent.keyDown(input, { key: "Enter" });

    // User message should appear
    await waitFor(() => {
      expect(screen.getByText("What is the rent?")).toBeInTheDocument();
    });

    // Loading dots should be visible
    expect(screen.getByLabelText("Thinking")).toBeInTheDocument();
  });

  it("displays the assistant response after successful fetch", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: "The rent is $2,000 per month.",
        disclaimer: "General legal information only.",
      }),
    });

    render(<ChatPanel documentId="test-doc-id" />);

    const input = screen.getByLabelText(/ask a question about your document/i);
    fireEvent.change(input, { target: { value: "What is the rent?" } });
    fireEvent.click(screen.getByLabelText(/send question/i));

    await waitFor(() => {
      expect(
        screen.getByText("The rent is $2,000 per month.")
      ).toBeInTheDocument();
    });
  });

  it("shows error message on failed chat request", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({
        detail: {
          error: "document_not_found",
          detail: "The document session has expired. Please re-upload.",
          disclaimer: "General legal information.",
        },
      }),
    });

    render(<ChatPanel documentId="expired-id" />);

    const input = screen.getByLabelText(/ask a question about your document/i);
    fireEvent.change(input, { target: { value: "What is the rent?" } });
    fireEvent.click(screen.getByLabelText(/send question/i));

    await waitFor(() => {
      expect(
        screen.getByText(/document session has expired/i)
      ).toBeInTheDocument();
    });
  });
});
