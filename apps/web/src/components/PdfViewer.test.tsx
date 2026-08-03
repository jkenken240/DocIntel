import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PdfViewer } from "./PdfViewer";

const getDocumentMock = vi.hoisted(() => vi.fn());

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: { workerSrc: "" },
  getDocument: getDocumentMock,
}));

vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({
  default: "/pdf.worker.test.mjs",
}));

afterEach(() => {
  vi.unstubAllGlobals();
  getDocumentMock.mockReset();
});

describe("PdfViewer diagnostics", () => {
  it("classifies an invalid HTTP response without exposing response details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            status: 503,
            detail: "A sanitized service response.",
          }),
          {
            status: 503,
            headers: { "Content-Type": "application/problem+json" },
          },
        ),
      ),
    );

    render(<PdfViewer documentId="document-1" filename="Atlas.pdf" initialPage={2} />);
    const viewer = screen.getByLabelText("PDF viewer for Atlas.pdf");
    expect(screen.getByLabelText("Scrollable PDF page")).toHaveAttribute(
      "tabindex",
      "0",
    );

    await waitFor(() =>
      expect(viewer).toHaveAttribute(
        "data-viewer-error-code",
        "PDF_HTTP_RESPONSE_INVALID",
      ),
    );
    expect(viewer).toHaveAttribute("data-viewer-stage", "response-validation");
    expect(viewer).toHaveAttribute("data-viewer-http-status", "503");
    expect(viewer).toHaveAttribute("data-viewer-content-type", "problem-json");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "A sanitized service response.",
    );
  });

  it("classifies body-read failures and never renders unsafe exception details", async () => {
    const response = new Response("%PDF-test", {
      status: 200,
      headers: { "Content-Type": "application/pdf" },
    });
    vi.spyOn(response, "blob").mockRejectedValue(
      new Error("PRIVATE_TOKEN must never appear in the interface"),
    );
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    render(<PdfViewer documentId="document-2" filename="Nova.pdf" />);
    const viewer = screen.getByLabelText("PDF viewer for Nova.pdf");

    await waitFor(() =>
      expect(viewer).toHaveAttribute(
        "data-viewer-error-code",
        "PDF_RESPONSE_BODY_READ_FAILED",
      ),
    );
    expect(viewer).toHaveAttribute("data-viewer-exception-name", "Error");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The protected PDF response could not be read.",
    );
    expect(screen.queryByText(/PRIVATE_TOKEN/)).not.toBeInTheDocument();
  });

  it("classifies PDF.js document-resolution failures without exposing exceptions", async () => {
    const unsafeFailure = new Error("customer text and stack must stay private");
    unsafeFailure.name = "InvalidPDFException";
    getDocumentMock.mockReturnValue({
      promise: Promise.reject(unsafeFailure),
      destroy: vi.fn().mockResolvedValue(undefined),
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(new Blob(["%PDF-test"]), {
          status: 200,
          headers: { "Content-Type": "application/pdf" },
        }),
      ),
    );

    render(<PdfViewer documentId="document-3" filename="Controls.pdf" />);
    const viewer = screen.getByLabelText("PDF viewer for Controls.pdf");

    await waitFor(() =>
      expect(viewer).toHaveAttribute(
        "data-viewer-error-code",
        "PDFJS_DOCUMENT_LOAD_FAILED",
      ),
    );
    expect(viewer).toHaveAttribute(
      "data-viewer-stage",
      "pdfjs-document-resolution",
    );
    expect(viewer).toHaveAttribute(
      "data-viewer-exception-name",
      "InvalidPDFException",
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The PDF source could not be opened.",
    );
    expect(
      screen.queryByText(/customer text|stack must stay private/),
    ).not.toBeInTheDocument();
  });
});
