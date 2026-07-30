import { API_BASE_URL, ApiProblem, requestJson } from "./client";
import type {
  DocumentDetail,
  DocumentEnvelope,
  DocumentListResponse,
  DocumentStatus,
  DocumentStatusResponse,
  ProblemDetails,
} from "./contracts";

export type DocumentSort = "created_at" | "name" | "size";
export type SortOrder = "asc" | "desc";

export interface DocumentListParameters {
  search?: string;
  statuses?: DocumentStatus[];
  sort?: DocumentSort;
  order?: SortOrder;
  cursor?: string;
  limit?: number;
}

function documentSearch(parameters: DocumentListParameters): string {
  const search = new URLSearchParams();
  search.set("limit", String(parameters.limit ?? 100));
  if (parameters.cursor) search.set("cursor", parameters.cursor);
  if (parameters.search?.trim()) search.set("search", parameters.search.trim());
  parameters.statuses?.forEach((status) => search.append("status", status));
  search.set("sort", parameters.sort ?? "created_at");
  search.set("order", parameters.order ?? "desc");
  return search.toString();
}

export function listDocuments(
  parameters: DocumentListParameters = {},
  signal?: AbortSignal,
): Promise<DocumentListResponse> {
  return requestJson<DocumentListResponse>(
    `/documents?${documentSearch(parameters)}`,
    { signal },
  );
}

export async function listAllDocuments(
  parameters: Omit<DocumentListParameters, "cursor" | "limit"> = {},
  signal?: AbortSignal,
): Promise<DocumentListResponse> {
  const items: DocumentListResponse["items"] = [];
  const seenCursors = new Set<string>();
  let cursor: string | undefined;

  for (let page = 0; page < 50; page += 1) {
    const response = await listDocuments(
      { ...parameters, cursor, limit: 100 },
      signal,
    );
    items.push(...response.items);
    if (!response.next_cursor || seenCursors.has(response.next_cursor)) {
      return { items, next_cursor: response.next_cursor };
    }
    seenCursors.add(response.next_cursor);
    cursor = response.next_cursor;
  }

  throw new ApiProblem(
    {
      status: 503,
      code: "DOCUMENT_LIST_LIMIT",
      title: "Document list is too large",
      detail: "The complete document library could not be loaded safely.",
    },
    503,
  );
}

export function getDocument(
  documentId: string,
  signal?: AbortSignal,
): Promise<DocumentDetail> {
  return requestJson<DocumentDetail>(
    `/documents/${encodeURIComponent(documentId)}`,
    { signal },
  );
}

export function getDocumentStatus(
  documentId: string,
  signal?: AbortSignal,
): Promise<DocumentStatusResponse> {
  return requestJson<DocumentStatusResponse>(
    `/documents/${encodeURIComponent(documentId)}/status`,
    { signal },
  );
}

export function retryDocument(documentId: string): Promise<DocumentEnvelope> {
  return requestJson<DocumentEnvelope>(
    `/documents/${encodeURIComponent(documentId)}/retry`,
    { method: "POST" },
  );
}

export function deleteDocument(documentId: string): Promise<DocumentEnvelope> {
  return requestJson<DocumentEnvelope>(
    `/documents/${encodeURIComponent(documentId)}`,
    { method: "DELETE" },
  );
}

async function problemFromXhr(xhr: XMLHttpRequest): Promise<ApiProblem> {
  let problem: ProblemDetails = {};
  try {
    const candidate: unknown = JSON.parse(xhr.responseText);
    if (typeof candidate === "object" && candidate !== null) {
      problem = candidate as ProblemDetails;
    }
  } catch {
    // A malformed response is replaced with the safe fallback below.
  }
  return new ApiProblem(problem, xhr.status || 503);
}

export function uploadDocument(
  file: File,
  options: {
    signal?: AbortSignal;
    onProgress?: (percentage: number) => void;
  } = {},
): Promise<DocumentEnvelope> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", file, file.name);

    const abort = () => xhr.abort();
    options.signal?.addEventListener("abort", abort, { once: true });

    xhr.open("POST", `${API_BASE_URL}/documents`);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && event.total > 0) {
        options.onProgress?.(
          Math.min(100, Math.round((event.loaded / event.total) * 100)),
        );
      }
    });
    xhr.addEventListener("load", async () => {
      options.signal?.removeEventListener("abort", abort);
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as DocumentEnvelope);
        } catch {
          reject(
            new ApiProblem(
              {
                status: 502,
                code: "MALFORMED_API_RESPONSE",
                title: "Unexpected API response",
                detail: "DocIntel returned an incomplete upload response.",
              },
              502,
            ),
          );
        }
      } else {
        reject(await problemFromXhr(xhr));
      }
    });
    xhr.addEventListener("error", () => {
      options.signal?.removeEventListener("abort", abort);
      reject(new TypeError("Upload connection failed."));
    });
    xhr.addEventListener("abort", () => {
      options.signal?.removeEventListener("abort", abort);
      reject(new DOMException("Upload cancelled.", "AbortError"));
    });
    xhr.send(form);
  });
}

export function isDocumentTerminal(status: DocumentStatus): boolean {
  return status === "ready" || status === "failed";
}
