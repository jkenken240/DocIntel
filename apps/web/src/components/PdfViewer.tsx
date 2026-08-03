import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  FileText,
  LoaderCircle,
  Maximize2,
  Minus,
  Plus,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { PDFDocumentLoadingTask, PDFDocumentProxy } from "pdfjs-dist";

import {
  fetchPdf,
  PdfFetchError,
  type PdfContentTypeCategory,
} from "../lib/api/client";

type ViewerState = "loading" | "ready" | "error";
type ViewerStage =
  | "idle"
  | "protected-request"
  | "response-validation"
  | "response-body-reading"
  | "byte-buffer-validation"
  | "pdfjs-module-loading"
  | "pdfjs-worker-initialization"
  | "pdfjs-loading-task"
  | "pdfjs-document-resolution"
  | "requested-page-loading"
  | "canvas-render-task"
  | "viewer-cleanup";

type ViewerErrorCode =
  | "PROTECTED_PDF_REQUEST_FAILED"
  | "PDF_HTTP_RESPONSE_INVALID"
  | "PDF_RESPONSE_BODY_READ_FAILED"
  | "PDF_BYTE_BUFFER_EMPTY"
  | "PDF_BYTE_BUFFER_DETACHED"
  | "PDFJS_MODULE_LOAD_FAILED"
  | "PDFJS_WORKER_INITIALIZATION_FAILED"
  | "PDFJS_LOADING_TASK_FAILED"
  | "PDFJS_DOCUMENT_LOAD_FAILED"
  | "PDF_PAGE_LOAD_FAILED"
  | "PDF_CANVAS_RENDER_FAILED"
  | "PDF_VIEWER_CANCELLED"
  | "PDF_VIEWER_LIFECYCLE_RESTARTED";

interface ViewerDiagnostic {
  code: ViewerErrorCode;
  stage: ViewerStage;
  httpStatus: number | null;
  contentTypeCategory: PdfContentTypeCategory;
  byteLength: number | null;
  requestedPage: number;
  resolvedPageCount: number | null;
  exceptionName: string;
  cancelled: boolean;
}

const SAFE_EXCEPTION_NAMES = new Set([
  "AbortError",
  "Error",
  "InvalidPDFException",
  "MissingPDFException",
  "OtherError",
  "PasswordException",
  "PdfFetchError",
  "RenderingCancelledException",
  "TypeError",
  "UnexpectedResponseException",
  "UnknownErrorException",
]);

function safeExceptionName(error: unknown): string {
  if (error instanceof PdfFetchError) return error.exceptionName;
  const name = error instanceof Error ? error.name : "OtherError";
  return SAFE_EXCEPTION_NAMES.has(name) ? name : "OtherError";
}

function errorCodeFor(error: unknown, stage: ViewerStage): ViewerErrorCode {
  if (error instanceof PdfFetchError) {
    if (error.stage === "request") return "PROTECTED_PDF_REQUEST_FAILED";
    if (error.stage === "http") return "PDF_HTTP_RESPONSE_INVALID";
    return "PDF_RESPONSE_BODY_READ_FAILED";
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return "PDF_VIEWER_CANCELLED";
  }
  if (stage === "byte-buffer-validation") return "PDF_BYTE_BUFFER_DETACHED";
  if (stage === "pdfjs-module-loading") return "PDFJS_MODULE_LOAD_FAILED";
  if (stage === "pdfjs-worker-initialization") {
    return "PDFJS_WORKER_INITIALIZATION_FAILED";
  }
  if (stage === "pdfjs-loading-task") return "PDFJS_LOADING_TASK_FAILED";
  if (stage === "pdfjs-document-resolution") return "PDFJS_DOCUMENT_LOAD_FAILED";
  if (stage === "requested-page-loading") return "PDF_PAGE_LOAD_FAILED";
  if (stage === "canvas-render-task") return "PDF_CANVAS_RENDER_FAILED";
  return "PDF_VIEWER_LIFECYCLE_RESTARTED";
}

function diagnosticStageFor(
  error: unknown,
  currentStage: ViewerStage,
): ViewerStage {
  if (!(error instanceof PdfFetchError)) return currentStage;
  if (error.stage === "http") return "response-validation";
  if (error.stage === "body") return "response-body-reading";
  return "protected-request";
}

function PdfViewerDocument({
  documentId,
  filename,
  initialPage = 1,
}: {
  documentId: string;
  filename: string;
  initialPage?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [viewerState, setViewerState] = useState<ViewerState>("loading");
  const [viewerStage, setViewerStage] = useState<ViewerStage>("idle");
  const [diagnostic, setDiagnostic] = useState<ViewerDiagnostic | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [pageRequest, setPageRequest] = useState(initialPage);
  const [pageNumber, setPageNumber] = useState(initialPage);
  const [zoom, setZoom] = useState(1.1);
  const [fitWidth, setFitWidth] = useState(true);

  if (pageRequest !== initialPage) {
    setPageRequest(initialPage);
    setPageNumber(
      pdf ? Math.min(Math.max(1, initialPage), pdf.numPages) : initialPage,
    );
  }

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;
    let loadingTask: PDFDocumentLoadingTask | null = null;
    let loadedPdf: PDFDocumentProxy | null = null;
    let disposed = false;
    let stage: ViewerStage = "protected-request";
    let httpStatus: number | null = null;
    let contentType: PdfContentTypeCategory = "missing";
    let byteLength: number | null = null;

    const advance = (next: ViewerStage) => {
      stage = next;
      if (!disposed) setViewerStage(next);
    };

    void (async () => {
      try {
        const fetched = await fetchPdf(documentId, controller.signal);
        httpStatus = fetched.status;
        contentType = fetched.contentTypeCategory;
        byteLength = fetched.byteLength;
        advance("response-validation");
        if (fetched.byteLength === 0) {
          setDiagnostic({
            code: "PDF_BYTE_BUFFER_EMPTY",
            stage: "byte-buffer-validation",
            httpStatus,
            contentTypeCategory: contentType,
            byteLength,
            requestedPage: initialPage,
            resolvedPageCount: null,
            exceptionName: "OtherError",
            cancelled: false,
          });
          setViewerStage("byte-buffer-validation");
          setViewerState("error");
          setErrorMessage("The protected PDF was empty and could not be opened.");
          return;
        }

        advance("byte-buffer-validation");
        const probe = await fetched.blob.slice(0, 1).arrayBuffer();
        if (probe.byteLength === 0) {
          throw new Error("Detached PDF byte buffer.");
        }

        const blob = fetched.blob;
        objectUrl = URL.createObjectURL(blob);
        advance("pdfjs-module-loading");
        const pdfjs = await import("pdfjs-dist");
        advance("pdfjs-worker-initialization");
        const worker = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
        if (!worker.default) throw new Error("PDF worker asset was unavailable.");
        pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
        advance("pdfjs-loading-task");
        loadingTask = pdfjs.getDocument({ url: objectUrl });
        advance("pdfjs-document-resolution");
        loadedPdf = await loadingTask.promise;
        if (disposed) {
          await loadedPdf.cleanup();
          return;
        }
        setPdf(loadedPdf);
        setPageNumber(
          Math.min(Math.max(1, initialPage), loadedPdf.numPages),
        );
        setViewerState("ready");
      } catch (error) {
        if (!controller.signal.aborted && !disposed) {
          const fetchFailure = error instanceof PdfFetchError ? error : null;
          const diagnosticStage = diagnosticStageFor(error, stage);
          setDiagnostic({
            code: errorCodeFor(error, stage),
            stage: diagnosticStage,
            httpStatus: fetchFailure?.status ?? httpStatus,
            contentTypeCategory:
              fetchFailure?.contentTypeCategory ?? contentType,
            byteLength: fetchFailure?.byteLength ?? byteLength,
            requestedPage: initialPage,
            resolvedPageCount: loadedPdf?.numPages ?? null,
            exceptionName: safeExceptionName(error),
            cancelled: false,
          });
          setViewerState("error");
          setErrorMessage(
            error instanceof PdfFetchError
              ? error.message
              : "The PDF source could not be opened.",
          );
        }
      }
    })();

    return () => {
      disposed = true;
      stage = "viewer-cleanup";
      controller.abort();
      void loadingTask?.destroy();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [documentId, initialPage]);

  useEffect(() => {
    if (!pdf || !canvasRef.current) return;
    let cancelled = false;
    let renderTask: { cancel: () => void; promise: Promise<void> } | null = null;
    void (async () => {
      let renderStage: ViewerStage = "requested-page-loading";
      try {
        setViewerStage(renderStage);
        const page = await pdf.getPage(pageNumber);
        if (cancelled || !canvasRef.current) return;
        const baseViewport = page.getViewport({ scale: 1 });
        const availableWidth = Math.max(
          280,
          (frameRef.current?.clientWidth ?? 760) - 32,
        );
        const scale = fitWidth
          ? Math.min(2.2, availableWidth / baseViewport.width)
          : zoom;
        const viewport = page.getViewport({ scale });
        const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
        const canvas = canvasRef.current;
        const context = canvas.getContext("2d");
        if (!context) throw new Error("PDF canvas is unavailable.");
        canvas.width = Math.floor(viewport.width * pixelRatio);
        canvas.height = Math.floor(viewport.height * pixelRatio);
        canvas.style.width = `${Math.floor(viewport.width)}px`;
        canvas.style.height = `${Math.floor(viewport.height)}px`;
        renderStage = "canvas-render-task";
        setViewerStage(renderStage);
        renderTask = page.render({
          canvas,
          canvasContext: context,
          viewport,
          transform:
            pixelRatio === 1 ? undefined : [pixelRatio, 0, 0, pixelRatio, 0, 0],
        });
        await renderTask.promise;
      } catch (error) {
        if (
          !cancelled &&
          !(error instanceof Error && error.name === "RenderingCancelledException")
        ) {
          setDiagnostic({
            code: errorCodeFor(error, renderStage),
            stage: renderStage,
            httpStatus: null,
            contentTypeCategory: "pdf",
            byteLength: null,
            requestedPage: pageNumber,
            resolvedPageCount: pdf.numPages,
            exceptionName: safeExceptionName(error),
            cancelled: false,
          });
          setViewerState("error");
          setErrorMessage("The requested PDF page could not be rendered.");
        }
      }
    })();

    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [fitWidth, pageNumber, pdf, zoom]);

  const totalPages = pdf?.numPages ?? null;

  return (
    <section
      className="pdf-viewer"
      aria-label={`PDF viewer for ${filename}`}
      data-viewer-state={viewerState}
      data-viewer-stage={diagnostic?.stage ?? viewerStage}
      data-viewer-error-code={diagnostic?.code}
      data-viewer-http-status={diagnostic?.httpStatus ?? undefined}
      data-viewer-content-type={diagnostic?.contentTypeCategory}
      data-viewer-byte-length={diagnostic?.byteLength ?? undefined}
      data-viewer-requested-page={diagnostic?.requestedPage ?? pageNumber}
      data-viewer-page-count={diagnostic?.resolvedPageCount ?? totalPages ?? undefined}
      data-viewer-exception-name={diagnostic?.exceptionName}
      data-viewer-cancelled={diagnostic ? String(diagnostic.cancelled) : undefined}
    >
      <div className="pdf-toolbar">
        <div className="pdf-file">
          <FileText size={17} aria-hidden="true" />
          <span title={filename}>{filename}</span>
        </div>
        <div className="pdf-controls" aria-label="PDF page controls">
          <button
            type="button"
            className="icon-button"
            aria-label="Previous PDF page"
            disabled={!pdf || pageNumber <= 1}
            onClick={() => setPageNumber((current) => Math.max(1, current - 1))}
          >
            <ChevronLeft size={18} aria-hidden="true" />
          </button>
          <span className="page-counter" aria-live="polite">
            Page {pageNumber} {totalPages ? `of ${totalPages}` : ""}
          </span>
          <button
            type="button"
            className="icon-button"
            aria-label="Next PDF page"
            disabled={!pdf || pageNumber >= (totalPages ?? 1)}
            onClick={() =>
              setPageNumber((current) =>
                Math.min(totalPages ?? current, current + 1),
              )
            }
          >
            <ChevronRight size={18} aria-hidden="true" />
          </button>
          <span className="toolbar-divider" aria-hidden="true" />
          <button
            type="button"
            className="icon-button"
            aria-label="Zoom out"
            disabled={!pdf || zoom <= 0.6}
            onClick={() => {
              setFitWidth(false);
              setZoom((current) => Math.max(0.6, current - 0.2));
            }}
          >
            <Minus size={17} aria-hidden="true" />
          </button>
          <button
            type="button"
            className={`icon-button ${fitWidth ? "selected" : ""}`}
            aria-label="Fit PDF to width"
            aria-pressed={fitWidth}
            disabled={!pdf}
            onClick={() => setFitWidth(true)}
          >
            <Maximize2 size={16} aria-hidden="true" />
          </button>
          <button
            type="button"
            className="icon-button"
            aria-label="Zoom in"
            disabled={!pdf || zoom >= 2.4}
            onClick={() => {
              setFitWidth(false);
              setZoom((current) => Math.min(2.4, current + 0.2));
            }}
          >
            <Plus size={17} aria-hidden="true" />
          </button>
        </div>
      </div>

      <div
        ref={frameRef}
        className="pdf-frame"
        aria-label="Scrollable PDF page"
        tabIndex={0}
      >
        {viewerState === "loading" ? (
          <div className="viewer-message" role="status">
            <LoaderCircle className="spin" size={22} aria-hidden="true" />
            <span>Opening protected PDF…</span>
          </div>
        ) : null}
        {viewerState === "error" ? (
          <div className="viewer-message viewer-error" role="alert">
            <AlertCircle size={22} aria-hidden="true" />
            <span>{errorMessage}</span>
          </div>
        ) : null}
        <canvas
          ref={canvasRef}
          className={viewerState === "ready" ? "pdf-canvas" : "pdf-canvas hidden"}
          aria-label={`Rendered PDF page ${pageNumber}`}
        />
      </div>
    </section>
  );
}

export function PdfViewer(props: {
  documentId: string;
  filename: string;
  initialPage?: number;
}) {
  return <PdfViewerDocument key={props.documentId} {...props} />;
}
