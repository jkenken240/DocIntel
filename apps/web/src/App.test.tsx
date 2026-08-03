import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import type {
  DocumentDetail,
  DocumentSummary,
  QuestionResponse,
} from "./lib/api/contracts";
import { RouterProvider } from "./lib/router";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: { workerSrc: "" },
  getDocument: vi.fn(() => ({
    promise: Promise.resolve({
      numPages: 5,
      cleanup: vi.fn().mockResolvedValue(undefined),
      getPage: vi.fn().mockResolvedValue({
        getViewport: ({ scale }: { scale: number }) => ({
          width: 600 * scale,
          height: 800 * scale,
        }),
        render: vi.fn(() => ({
          cancel: vi.fn(),
          promise: Promise.resolve(),
        })),
      }),
    }),
    destroy: vi.fn().mockResolvedValue(undefined),
  })),
}));

vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({
  default: "/pdf.worker.test.mjs",
}));

const DOCUMENT_ONE = "11111111-1111-4111-8111-111111111111";
const DOCUMENT_TWO = "22222222-2222-4222-8222-222222222222";
const DOCUMENT_FAILED = "33333333-3333-4333-8333-333333333333";
const QUESTION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

function summary(
  overrides: Partial<DocumentSummary> & Pick<DocumentSummary, "id" | "name">,
): DocumentSummary {
  const { id, name, ...rest } = overrides;
  return {
    id,
    name,
    media_type: "application/pdf",
    byte_size: 12_400,
    status: "ready",
    stage: "embedding",
    progress: { completed: 2, total: 2, unit: "pages" },
    created_at: "2026-07-30T02:00:00Z",
    updated_at: "2026-07-30T02:02:00Z",
    ...rest,
  };
}

function detail(document: DocumentSummary, retryable = false): DocumentDetail {
  return {
    ...document,
    sha256: "a".repeat(64),
    page_count: document.status === "ready" ? 3 : 0,
    text_page_count: document.status === "ready" ? 2 : 0,
    chunk_count: document.status === "ready" ? 4 : 0,
    processing_revision: 1,
    processing_version: "phase4-v1",
    pdf_metadata: {},
    stage_started_at: null,
    processing_started_at: null,
    processing_completed_at: null,
    error:
      document.status === "failed"
        ? {
            code: "PROVIDER_TEMPORARY",
            message: "Processing can be retried safely.",
            retryable,
          }
        : null,
  };
}

const readyOne = summary({
  id: DOCUMENT_ONE,
  name: "Atlas Records.pdf",
});
const readyTwo = summary({
  id: DOCUMENT_TWO,
  name: "Nova Amendment.pdf",
  created_at: "2026-07-29T02:00:00Z",
});
const failed = summary({
  id: DOCUMENT_FAILED,
  name: "Retry Policy.pdf",
  status: "failed",
  stage: "embedding",
  progress: { completed: 1, total: 2, unit: "chunks" },
});

function groundedResult(
  status: "answered" | "insufficient_evidence" = "answered",
): QuestionResponse {
  const first = "Atlas retains audit records for seven years.";
  const second = "Nova retains audit records for nine years.";
  const answer = `${first} ${second}`;
  return {
    id: QUESTION_ID,
    question: "How long are audit records retained?",
    selected_document_ids: [DOCUMENT_ONE, DOCUMENT_TWO],
    status,
    insufficient_reason_code:
      status === "insufficient_evidence"
        ? "EVIDENCE_DOES_NOT_ANSWER"
        : null,
    answer_id:
      status === "answered"
        ? "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        : null,
    answer_text: status === "answered" ? answer : null,
    claims:
      status === "answered"
        ? [
            {
              id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
              ordinal: 0,
              char_start: 0,
              char_end: first.length,
              text: first,
              supported: true,
              verification_reason_code: "EXACT_EVIDENCE_MATCH",
              citations: [
                {
                  id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
                  evidence_id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
                  document_id: DOCUMENT_ONE,
                  filename: readyOne.name,
                  page_number: 2,
                  chunk_id: "12121212-1212-4212-8212-121212121212",
                  char_start: 12,
                  char_end: 56,
                  excerpt: first,
                  text_sha256: "1".repeat(64),
                  retrieval_score: 0.91,
                  retrieval_rank: 1,
                },
              ],
            },
            {
              id: "ffffffff-ffff-4fff-8fff-ffffffffffff",
              ordinal: 1,
              char_start: first.length + 1,
              char_end: answer.length,
              text: second,
              supported: true,
              verification_reason_code: "EXACT_EVIDENCE_MATCH",
              citations: [
                {
                  id: "abababab-abab-4bab-8bab-abababababab",
                  evidence_id: "cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd",
                  document_id: DOCUMENT_TWO,
                  filename: readyTwo.name,
                  page_number: 3,
                  chunk_id: "34343434-3434-4434-8434-343434343434",
                  char_start: 4,
                  char_end: 46,
                  excerpt: second,
                  text_sha256: "2".repeat(64),
                  retrieval_score: 0.84,
                  retrieval_rank: 2,
                },
              ],
            },
          ]
        : [],
    evidence:
      status === "answered"
        ? [
            {
              id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
              document_id: DOCUMENT_ONE,
              filename: readyOne.name,
              processing_revision: 1,
              page_id: "78787878-7878-4878-8878-787878787878",
              page_number: 2,
              chunk_id: "12121212-1212-4212-8212-121212121212",
              chunk_ordinal: 0,
              char_start: 12,
              char_end: 56,
              excerpt: first,
              text_sha256: "1".repeat(64),
              retrieval_score: 0.91,
              retrieval_rank: 1,
            },
            {
              id: "cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd",
              document_id: DOCUMENT_TWO,
              filename: readyTwo.name,
              processing_revision: 1,
              page_id: "90909090-9090-4090-8090-909090909090",
              page_number: 3,
              chunk_id: "34343434-3434-4434-8434-343434343434",
              chunk_ordinal: 0,
              char_start: 4,
              char_end: 46,
              excerpt: second,
              text_sha256: "2".repeat(64),
              retrieval_score: 0.84,
              retrieval_rank: 2,
            },
          ]
        : [],
    retrieval_configuration: {
      candidate_pool: 40,
      evidence_count: 6,
    },
    retrieval_configuration_hash: "3".repeat(64),
    embedding_space: {
      id: "56565656-5656-4656-8656-565656565656",
      provider: "mock",
      model: "mock-hash-v1",
      configuration_hash: "4".repeat(64),
      dimensions: 1536,
      distance_metric: "cosine",
    },
    answer_provider: {
      provider: "mock",
      model: "mock-grounded-v1",
      configuration_hash: "5".repeat(64),
    },
    verifier_provider: {
      provider: "mock",
      model: "mock-claim-verifier-v1",
      configuration_hash: "6".repeat(64),
    },
    created_at: "2026-07-30T03:00:00Z",
  };
}

function json(payload: unknown, status = 200, contentType = "application/json") {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": contentType },
  });
}

function readiness() {
  return {
    status: "ready",
    checks: {
      database: { status: "ready", detail: "PostgreSQL query succeeded." },
      provider: {
        status: "ready",
        detail: "Deterministic mock provider configured.",
      },
    },
  };
}

function installFetch(
  handler: (
    url: URL,
    init: RequestInit | undefined,
  ) => Response | Promise<Response>,
) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
    handler(new URL(String(input), "http://localhost"), init),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderApp(path = "/") {
  window.history.replaceState(null, "", path);
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider>
        <App />
      </RouterProvider>
    </QueryClientProvider>,
  );
  return { ...rendered, queryClient };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  window.history.replaceState(null, "", "/");
});

describe("DocIntel workspace", () => {
  it("renders the responsive shell and truthful first-use overview", async () => {
    installFetch((url) => {
      if (url.pathname.endsWith("/health/ready")) return json(readiness());
      if (url.pathname.endsWith("/documents")) {
        return json({ items: [], next_cursor: null });
      }
      throw new Error(`Unhandled ${url}`);
    });

    renderApp("/");

    expect(
      await screen.findByRole("heading", {
        name: "Turn dense PDFs into answers you can inspect.",
      }),
    ).toBeVisible();
    expect(screen.getByText("Start with a PDF")).toBeVisible();
    expect(screen.getByText("Workspace ready")).toBeVisible();
    expect(
      screen.getByRole("navigation", { name: "Primary navigation" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Mobile navigation" }),
    ).toBeInTheDocument();
    expect(document.title).toBe("Overview · DocIntel");
  });

  it("moves focus on route changes without stealing it during page interaction", async () => {
    installFetch((url) => {
      if (url.pathname.endsWith("/health/ready")) return json(readiness());
      if (url.pathname.endsWith("/documents")) {
        return json({ items: [readyOne], next_cursor: null });
      }
      throw new Error(`Unhandled ${url}`);
    });
    const user = userEvent.setup();
    renderApp("/");

    const main = screen.getByRole("main");
    await waitFor(() => expect(main).toHaveFocus());

    await user.click(
      within(screen.getByRole("navigation", { name: "Primary navigation" })).getByRole(
        "link",
        { name: "Documents" },
      ),
    );
    expect(await screen.findByRole("heading", { name: "Document library" })).toBeVisible();
    expect(main).toHaveFocus();

    const search = screen.getByRole("searchbox", { name: "Search documents" });
    await user.type(search, "Atlas");
    expect(search).toHaveFocus();

    await user.click(
      within(screen.getByRole("navigation", { name: "Primary navigation" })).getByRole(
        "link",
        { name: "Ask DocIntel" },
      ),
    );
    expect(
      await screen.findByRole("heading", { name: "Ask the evidence, not a chatbot." }),
    ).toBeVisible();
    expect(main).toHaveFocus();
  });

  it("loads, searches, filters, selects, retries, and deletes documents", async () => {
    const requests: Array<{ method: string; url: string }> = [];
    installFetch((url, init) => {
      const method = init?.method ?? "GET";
      requests.push({ method, url: url.toString() });
      if (url.pathname.endsWith("/health/ready")) return json(readiness());
      if (url.pathname.endsWith("/documents") && method === "GET") {
        return json({ items: [readyOne, failed], next_cursor: null });
      }
      if (url.pathname.endsWith(`/${DOCUMENT_FAILED}`) && method === "GET") {
        return json(detail(failed, true));
      }
      if (url.pathname.endsWith(`/${DOCUMENT_FAILED}/retry`)) {
        return json({ document: detail({ ...failed, status: "queued" }) }, 202);
      }
      if (url.pathname.endsWith(`/${DOCUMENT_ONE}`) && method === "DELETE") {
        return json(
          {
            document: detail({
              ...readyOne,
              status: "deleting",
              stage: "deleting",
            }),
          },
          202,
        );
      }
      throw new Error(`Unhandled ${method} ${url}`);
    });
    const user = userEvent.setup();

    renderApp("/documents");

    expect(await screen.findByText(readyOne.name)).toBeVisible();
    expect(
      screen.getByText("Needs attention", { selector: ".status-badge" }),
    ).toBeVisible();
    expect(
      await screen.findByRole("button", {
        name: `Retry processing ${failed.name}`,
      }),
    ).toBeVisible();

    await user.type(screen.getByLabelText("Search documents"), "Atlas");
    await waitFor(() =>
      expect(
        requests.some(({ url }) => url.includes("search=Atlas")),
      ).toBe(true),
    );
    await user.selectOptions(screen.getByLabelText("Filter by status"), "ready");
    await waitFor(() =>
      expect(
        requests.some(({ url }) => url.includes("status=ready")),
      ).toBe(true),
    );

    await user.click(
      screen.getByLabelText(`Select ${readyOne.name} as a question source`),
    );
    expect(
      screen.getByText(
        (_, element) =>
          element?.classList.contains("selection-dock") === true &&
          element.textContent?.includes("1 READY source selected") === true,
      ),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: /Ask with selection/i }),
    ).toHaveAttribute("href", `/ask?documents=${DOCUMENT_ONE}`);

    await user.click(
      screen.getByRole("button", {
        name: `Retry processing ${failed.name}`,
      }),
    );
    await waitFor(() =>
      expect(
        requests.some(
          ({ method, url }) =>
            method === "POST" && url.endsWith(`/${DOCUMENT_FAILED}/retry`),
        ),
      ).toBe(true),
    );

    await user.click(
      screen.getByRole("button", { name: `Delete ${readyOne.name}` }),
    );
    const dialog = screen.getByRole("dialog");
    expect(
      within(dialog).getByRole("heading", {
        name: `Delete ${readyOne.name}?`,
      }),
    ).toBeVisible();
    expect(
      within(dialog).getByText(/grounded answers that depend/i),
    ).toBeVisible();
    await user.click(
      within(dialog).getByRole("button", { name: "Delete document" }),
    );
    expect(
      await screen.findByText(`Deletion accepted for ${readyOne.name}.`),
    ).toBeVisible();
  });

  it("replaces truthful processing progress when the server reports READY", async () => {
    const processing = summary({
      id: DOCUMENT_ONE,
      name: "Atlas Records.pdf",
      status: "processing",
      stage: "extracting",
      progress: { completed: 1, total: 3, unit: "pages" },
    });
    let listRequests = 0;
    installFetch((url) => {
      if (url.pathname.endsWith("/health/ready")) return json(readiness());
      if (url.pathname.endsWith("/documents")) {
        listRequests += 1;
        return json({
          items: [listRequests === 1 ? processing : readyOne],
          next_cursor: null,
        });
      }
      throw new Error(`Unhandled ${url}`);
    });

    const { queryClient } = renderApp("/documents");

    expect(await screen.findByText("Extracting pages")).toBeVisible();
    expect(screen.getByText("1 of 3 pages")).toBeVisible();
    await act(async () => {
      await queryClient.invalidateQueries({
        queryKey: ["documents", "library"],
      });
    });
    expect(await screen.findByText("Evidence ready")).toBeVisible();
    expect(screen.queryByText("Extracting pages")).not.toBeInTheDocument();
  });

  it("submits one bounded question with selected READY sources", async () => {
    const result = groundedResult();
    let postCount = 0;
    installFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.pathname.endsWith("/health/ready")) return json(readiness());
      if (url.pathname.endsWith("/documents") && method === "GET") {
        return json({ items: [readyOne, readyTwo], next_cursor: null });
      }
      if (url.pathname.endsWith("/questions") && method === "POST") {
        postCount += 1;
        return json(result, 201);
      }
      if (url.pathname.endsWith(`/questions/${QUESTION_ID}`)) {
        return json(result);
      }
      if (url.pathname.endsWith("/content")) {
        return new Response(new Blob(["%PDF-test"]), {
          status: 200,
          headers: { "Content-Type": "application/pdf" },
        });
      }
      throw new Error(`Unhandled ${method} ${url}`);
    });
    const user = userEvent.setup();

    renderApp(`/ask?documents=${DOCUMENT_ONE},${DOCUMENT_TWO}`);

    const textbox = await screen.findByLabelText("Question for DocIntel");
    await user.type(textbox, "How long are audit records retained?");
    const submit = screen.getByRole("button", { name: /Ask DocIntel/i });
    await user.dblClick(submit);

    expect(
      await screen.findByRole("heading", {
        name: "How long are audit records retained?",
      }),
    ).toBeVisible();
    expect(postCount).toBe(1);
    expect(window.location.pathname).toBe(`/questions/${QUESTION_ID}`);
  });

  it("presents structured claims and moves cross-document citations to exact PDF pages", async () => {
    const result = groundedResult();
    const pdfCacheModes: Array<RequestCache | undefined> = [];
    installFetch((url, init) => {
      if (url.pathname.endsWith("/health/ready")) return json(readiness());
      if (url.pathname.endsWith(`/questions/${QUESTION_ID}`)) return json(result);
      if (url.pathname.endsWith("/content")) {
        pdfCacheModes.push(init?.cache);
        return new Response(new Blob(["%PDF-test"]), {
          status: 200,
          headers: { "Content-Type": "application/pdf" },
        });
      }
      throw new Error(`Unhandled ${url}`);
    });
    const user = userEvent.setup();

    renderApp(`/questions/${QUESTION_ID}`);

    expect(await screen.findByText("Claims and citations")).toBeVisible();
    expect(screen.getByText("2 evidence records")).toBeVisible();
    expect(screen.getByText("Page 2")).toBeVisible();
    expect(
      screen.getByText("Atlas retains audit records for seven years.", {
        selector: "blockquote",
      }),
    ).toBeVisible();
    expect(
      await screen.findByLabelText("Rendered PDF page 2"),
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", {
        name: /Open citation 1 for claim 2: Nova Amendment\.pdf, page 3/i,
      }),
    );

    expect(screen.getByText("Page 3")).toBeVisible();
    expect(
      screen.getByText("Nova retains audit records for nine years.", {
        selector: "blockquote",
      }),
    ).toBeVisible();
    expect(await screen.findByLabelText("Rendered PDF page 3")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: readyTwo.name }),
    ).toBeVisible();
    expect(pdfCacheModes.length).toBeGreaterThan(0);
    expect(new Set(pdfCacheModes)).toEqual(new Set(["no-store"]));
  });

  it("treats insufficient evidence as a deliberate non-answer state", async () => {
    const result = groundedResult("insufficient_evidence");
    installFetch((url) => {
      if (url.pathname.endsWith("/health/ready")) return json(readiness());
      if (url.pathname.endsWith(`/questions/${QUESTION_ID}`)) return json(result);
      throw new Error(`Unhandled ${url}`);
    });

    renderApp(`/questions/${QUESTION_ID}`);

    expect(
      await screen.findByRole("heading", {
        name: "The evidence was not strong enough",
      }),
    ).toBeVisible();
    expect(
      screen.getByText(/did not display an answer or citations/i),
    ).toBeVisible();
    expect(screen.queryByText("Claims and citations")).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Revise question" }),
    ).toHaveAttribute(
      "href",
      `/ask?documents=${DOCUMENT_ONE},${DOCUMENT_TWO}`,
    );
  });

  it("shows sanitized problem details and a support trace", async () => {
    installFetch((url) => {
      if (url.pathname.endsWith("/health/ready")) return json(readiness());
      if (url.pathname.endsWith("/documents")) {
        return json(
          {
            title: "Library unavailable",
            detail: "The document library could not be loaded safely.",
            status: 503,
            code: "DATABASE_UNAVAILABLE",
            trace_id: "trace-safe-123",
          },
          503,
          "application/problem+json",
        );
      }
      throw new Error(`Unhandled ${url}`);
    });

    renderApp("/documents");

    expect(await screen.findByText("Library unavailable")).toBeVisible();
    expect(
      screen.getByText("The document library could not be loaded safely."),
    ).toBeVisible();
    expect(screen.getByText("Support trace: trace-safe-123")).toBeVisible();
  });

  it("cancels in-flight document polling when the workspace unmounts", async () => {
    let aborted = false;
    installFetch((url, init) => {
      if (url.pathname.endsWith("/health/ready")) return json(readiness());
      if (url.pathname.endsWith("/documents")) {
        return new Promise<Response>((_, reject) => {
          init?.signal?.addEventListener("abort", () => {
            aborted = true;
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      }
      throw new Error(`Unhandled ${url}`);
    });

    const rendered = renderApp("/documents");
    expect(await screen.findByText("Loading document library")).toBeVisible();
    rendered.unmount();

    await waitFor(() => expect(aborted).toBe(true));
  });
});
