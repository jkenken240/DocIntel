import { type Page, type TestInfo } from "@playwright/test";

interface SafeBrowserDiagnostic {
  resource: "protected-pdf" | "pdfjs-worker";
  event: "request-failed" | "response";
  status: number | null;
  contentTypeCategory: "pdf" | "javascript" | "other" | "missing";
  failureName: string | null;
}

const SAFE_ERROR_NAMES = new Set([
  "AbortError",
  "Error",
  "NetworkError",
  "TypeError",
]);

function safeErrorName(value: string | null): string | null {
  if (!value) return null;
  const name = value.split(":", 1)[0]?.trim() ?? "";
  return SAFE_ERROR_NAMES.has(name) ? name : "OtherError";
}

function typeCategory(value: string | undefined) {
  const normalized = value?.split(";", 1)[0]?.trim().toLocaleLowerCase() ?? "";
  if (!normalized) return "missing" as const;
  if (normalized === "application/pdf") return "pdf" as const;
  if (normalized.includes("javascript")) return "javascript" as const;
  return "other" as const;
}

function resourceKind(url: string): SafeBrowserDiagnostic["resource"] | null {
  const pathname = new URL(url).pathname;
  if (/\/documents\/[0-9a-f-]+\/content$/i.test(pathname)) return "protected-pdf";
  if (pathname.includes("pdf.worker")) return "pdfjs-worker";
  return null;
}

export function observePdfViewer(page: Page) {
  const browserEvents: SafeBrowserDiagnostic[] = [];
  const pageErrors: string[] = [];

  page.on("pageerror", (error) => {
    pageErrors.push(SAFE_ERROR_NAMES.has(error.name) ? error.name : "OtherError");
  });
  page.on("requestfailed", (request) => {
    const resource = resourceKind(request.url());
    if (!resource) return;
    browserEvents.push({
      resource,
      event: "request-failed",
      status: null,
      contentTypeCategory: "missing",
      failureName: safeErrorName(request.failure()?.errorText ?? null),
    });
  });
  page.on("response", (response) => {
    const resource = resourceKind(response.url());
    if (!resource) return;
    browserEvents.push({
      resource,
      event: "response",
      status: response.status(),
      contentTypeCategory: typeCategory(response.headers()["content-type"]),
      failureName: null,
    });
  });

  return { browserEvents, pageErrors };
}

export async function attachPdfViewerFailure(
  page: Page,
  testInfo: TestInfo,
  observed: ReturnType<typeof observePdfViewer>,
): Promise<void> {
  const viewer = page.locator(".pdf-viewer").last();
  const viewerAttributes = await viewer.evaluate((element) => ({
    state: element.getAttribute("data-viewer-state"),
    stage: element.getAttribute("data-viewer-stage"),
    errorCode: element.getAttribute("data-viewer-error-code"),
    httpStatus: element.getAttribute("data-viewer-http-status"),
    contentTypeCategory: element.getAttribute("data-viewer-content-type"),
    byteLength: element.getAttribute("data-viewer-byte-length"),
    requestedPage: element.getAttribute("data-viewer-requested-page"),
    pageCount: element.getAttribute("data-viewer-page-count"),
    exceptionName: element.getAttribute("data-viewer-exception-name"),
    cancelled: element.getAttribute("data-viewer-cancelled"),
  }));
  const canvas = viewer.locator("canvas");
  const canvasMetrics = await canvas.evaluate((element) => {
    const canvasElement = element as HTMLCanvasElement;
    const rect = canvasElement.getBoundingClientRect();
    return {
      visible: rect.width > 0 && rect.height > 0,
      cssWidth: Math.round(rect.width),
      cssHeight: Math.round(rect.height),
      pixelWidth: canvasElement.width,
      pixelHeight: canvasElement.height,
    };
  });

  await testInfo.attach("pdf-viewer-diagnostic.json", {
    body: Buffer.from(
      JSON.stringify(
        {
          viewer: viewerAttributes,
          canvas: canvasMetrics,
          pageErrors: observed.pageErrors,
          browserEvents: observed.browserEvents,
        },
        null,
        2,
      ),
    ),
    contentType: "application/json",
  });
}
