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

export async function fetchPdf(
  documentId: string,
  signal?: AbortSignal,
): Promise<Blob> {
  const response = await fetch(contentUrl(documentId), {
    headers: { Accept: "application/pdf" },
    signal,
  });
  if (!response.ok) {
    throw await problemFromResponse(response);
  }
  return response.blob();
}
