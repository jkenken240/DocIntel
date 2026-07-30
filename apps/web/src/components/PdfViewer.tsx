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

import { describeError, fetchPdf } from "../lib/api/client";

type ViewerState = "loading" | "ready" | "error";

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

    void (async () => {
      try {
        const blob = await fetchPdf(documentId, controller.signal);
        objectUrl = URL.createObjectURL(blob);
        const [pdfjs, worker] = await Promise.all([
          import("pdfjs-dist"),
          import("pdfjs-dist/build/pdf.worker.min.mjs?url"),
        ]);
        pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
        loadingTask = pdfjs.getDocument({ url: objectUrl });
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
        if (!controller.signal.aborted) {
          setViewerState("error");
          setErrorMessage(
            describeError(error).message ||
              "The PDF source could not be opened.",
          );
        }
      }
    })();

    return () => {
      disposed = true;
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
      try {
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
    <section className="pdf-viewer" aria-label={`PDF viewer for ${filename}`}>
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

      <div ref={frameRef} className="pdf-frame">
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
