import type { ProblemDetails } from "./contracts";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1"
).replace(/\/$/, "");

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export class ApiProblem extends Error {
  readonly status: number;
  readonly code: string;
  readonly title: string;
  readonly traceId: string | null;

  constructor(problem: ProblemDetails, fallbackStatus: number) {
    const safeDetail =
      typeof problem.detail === "string" && problem.detail.trim()
        ? problem.detail
        : "DocIntel could not complete the request.";
    super(safeDetail);
    this.name = "ApiProblem";
    this.status =
      typeof problem.status === "number" ? problem.status : fallbackStatus;
    this.code =
      typeof problem.code === "string" ? problem.code : "REQUEST_FAILED";
    this.title =
      typeof problem.title === "string" ? problem.title : "Request failed";
    this.traceId =
      typeof problem.trace_id === "string" ? problem.trace_id : null;
  }
}

async function problemFromResponse(response: Response): Promise<ApiProblem> {
  let payload: ProblemDetails = {};
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/problem+json")) {
    try {
      const candidate: unknown = await response.json();
      if (isRecord(candidate)) {
        payload = candidate as ProblemDetails;
      }
    } catch {
      // A malformed error body is intentionally replaced with a safe fallback.
    }
  }
  return new ApiProblem(payload, response.status);
}

export async function requestJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init.headers,
    },
  });

  if (!response.ok) {
    throw await problemFromResponse(response);
  }

  const payload: unknown = await response.json();
  if (!isRecord(payload)) {
    throw new ApiProblem(
      {
        status: 502,
        code: "MALFORMED_API_RESPONSE",
        title: "Unexpected API response",
        detail: "DocIntel returned an incomplete response.",
      },
      502,
    );
  }
  return payload as T;
}

export function describeError(error: unknown): {
  title: string;
  message: string;
  traceId: string | null;
} {
  if (error instanceof ApiProblem) {
    return {
      title: error.title,
      message: error.message,
      traceId: error.traceId,
    };
  }
  return {
    title: "Connection interrupted",
    message: "DocIntel could not reach the workspace API. Check the service and try again.",
    traceId: null,
  };
}

export function contentUrl(documentId: string): string {
  return `${API_BASE_URL}/documents/${encodeURIComponent(documentId)}/content`;
}

export type PdfContentTypeCategory =
  | "pdf"
  | "problem-json"
  | "json"
  | "other"
  | "missing";

export type PdfFetchFailureStage = "request" | "http" | "body";

export class PdfFetchError extends Error {
  readonly stage: PdfFetchFailureStage;
  readonly status: number | null;
  readonly contentTypeCategory: PdfContentTypeCategory;
  readonly byteLength: number | null;
  readonly exceptionName: string;

  constructor({
    stage,
    status = null,
    contentTypeCategory = "missing",
    byteLength = null,
    exceptionName = "OtherError",
    safeMessage,
  }: {
    stage: PdfFetchFailureStage;
    status?: number | null;
    contentTypeCategory?: PdfContentTypeCategory;
    byteLength?: number | null;
    exceptionName?: string;
    safeMessage: string;
  }) {
    super(safeMessage);
    this.name = "PdfFetchError";
    this.stage = stage;
    this.status = status;
    this.contentTypeCategory = contentTypeCategory;
    this.byteLength = byteLength;
    this.exceptionName = exceptionName;
  }
}

export interface FetchedPdf {
  blob: Blob;
  status: number;
  contentTypeCategory: PdfContentTypeCategory;
  byteLength: number;
}

function contentTypeCategory(value: string | null): PdfContentTypeCategory {
  const normalized = value?.split(";", 1)[0]?.trim().toLocaleLowerCase() ?? "";
  if (!normalized) return "missing";
  if (normalized === "application/pdf") return "pdf";
  if (normalized === "application/problem+json") return "problem-json";
  if (normalized === "application/json") return "json";
  return "other";
}

function safeTransportExceptionName(error: unknown): string {
  const name = error instanceof Error ? error.name : "OtherError";
  return new Set(["AbortError", "Error", "NetworkError", "TypeError"]).has(name)
    ? name
    : "OtherError";
}

export async function fetchPdf(
  documentId: string,
  signal?: AbortSignal,
): Promise<FetchedPdf> {
  let response: Response;
  try {
    response = await fetch(contentUrl(documentId), {
      cache: "no-store",
      headers: { Accept: "application/pdf" },
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new PdfFetchError({
      stage: "request",
      exceptionName: safeTransportExceptionName(error),
      safeMessage:
        "DocIntel could not reach the protected PDF. Check the service and try again.",
    });
  }

  const category = contentTypeCategory(response.headers.get("content-type"));
  if (!response.ok) {
    const problem = await problemFromResponse(response);
    throw new PdfFetchError({
      stage: "http",
      status: response.status,
      contentTypeCategory: category,
      exceptionName: "PdfFetchError",
      safeMessage: problem.message,
    });
  }

  try {
    const blob = await response.blob();
    return {
      blob,
      status: response.status,
      contentTypeCategory: category,
      byteLength: blob.size,
    };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new PdfFetchError({
      stage: "body",
      status: response.status,
      contentTypeCategory: category,
      exceptionName: safeTransportExceptionName(error),
      safeMessage: "The protected PDF response could not be read.",
    });
  }
}
