import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UploadQueue } from "./UploadQueue";

class FakeXMLHttpRequest extends EventTarget {
  static instances: FakeXMLHttpRequest[] = [];

  readonly upload = new EventTarget();
  status = 0;
  responseText = "";
  method = "";
  url = "";
  aborted = false;
  sent = false;
  body: Document | XMLHttpRequestBodyInit | null = null;

  constructor() {
    super();
    FakeXMLHttpRequest.instances.push(this);
  }

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }

  setRequestHeader() {
    // Header values are not material to this network-boundary test.
  }

  send(body: Document | XMLHttpRequestBodyInit | null = null) {
    this.sent = true;
    this.body = body;
  }

  emitProgress(loaded: number, total: number) {
    this.upload.dispatchEvent(
      new ProgressEvent("progress", {
        lengthComputable: true,
        loaded,
        total,
      }),
    );
  }

  respond(status: number, payload: unknown) {
    if (this.aborted) return;
    this.status = status;
    this.responseText = JSON.stringify(payload);
    this.dispatchEvent(new Event("load"));
  }

  fail() {
    if (this.aborted) return;
    this.dispatchEvent(new Event("error"));
  }

  abort() {
    this.aborted = true;
    this.dispatchEvent(new Event("abort"));
  }
}

function renderQueue(autoFocus = false) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidateQueries = vi.spyOn(queryClient, "invalidateQueries");
  const queue = (focus: boolean) => (
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <UploadQueue autoFocus={focus} />
      </QueryClientProvider>
    </StrictMode>
  );
  const rendered = render(queue(autoFocus));
  return {
    ...rendered,
    invalidateQueries,
    setAutoFocus: (focus: boolean) => rendered.rerender(queue(focus)),
  };
}

async function waitForRequest(index = 0) {
  await waitFor(() =>
    expect(FakeXMLHttpRequest.instances.length).toBeGreaterThan(index),
  );
  return FakeXMLHttpRequest.instances[index];
}

afterEach(() => {
  vi.unstubAllGlobals();
  FakeXMLHttpRequest.instances = [];
});

describe("UploadQueue", () => {
  it("tracks progress and removes a successful row after a real 202 XHR lifecycle", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
    const { invalidateQueries } = renderQueue();
    const file = new File(["%PDF-1.7 fictional"], "Quarterly Atlas.pdf", {
      type: "application/pdf",
      lastModified: 10,
    });

    fireEvent.change(screen.getByLabelText("Choose PDF files"), {
      target: { files: [file] },
    });

    expect(await screen.findByText("Quarterly Atlas.pdf")).toBeVisible();
    const request = await waitForRequest();
    expect(request.method).toBe("POST");
    expect(request.url).toMatch(/\/documents$/);
    expect(request.sent).toBe(true);
    expect(request.body).toBeInstanceOf(FormData);
    expect(screen.getByText("1 active")).toBeVisible();

    const progress = screen.getByRole("progressbar", {
      name: "Uploading Quarterly Atlas.pdf",
    });
    expect(progress).toHaveAttribute("aria-valuenow", "0");
    act(() => request.emitProgress(64, 128));
    expect(progress).toHaveAttribute("aria-valuenow", "50");

    act(() =>
      request.respond(202, {
        document: {
          id: "11111111-1111-4111-8111-111111111111",
          name: "Quarterly Atlas.pdf",
        },
      }),
    );

    await waitFor(() =>
      expect(
        screen.queryByRole("list", { name: "Upload queue" }),
      ).not.toBeInTheDocument(),
    );
    expect(screen.queryByText("1 active")).not.toBeInTheDocument();
    expect(screen.queryByText("0 active")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("progressbar", {
        name: "Uploading Quarterly Atlas.pdf",
      }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Quarterly Atlas.pdf uploaded and queued for processing.",
    );
    await waitFor(() =>
      expect(invalidateQueries).toHaveBeenCalledWith({
        queryKey: ["documents"],
      }),
    );
    expect(FakeXMLHttpRequest.instances).toHaveLength(1);

    fireEvent.change(screen.getByLabelText("Choose PDF files"), {
      target: { files: [file] },
    });
    expect(FakeXMLHttpRequest.instances).toHaveLength(1);
    expect(
      screen.queryByRole("list", { name: "Upload queue" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("");
  });

  it("keeps successful, failed, and active files independent in a mixed batch", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
    const { invalidateQueries } = renderQueue();
    const accepted = new File(["%PDF-1.7 accepted"], "Accepted.pdf", {
      type: "application/pdf",
      lastModified: 11,
    });
    const failed = new File(["%PDF-1.7 failed"], "Failed.pdf", {
      type: "application/pdf",
      lastModified: 12,
    });
    const active = new File(["%PDF-1.7 active"], "Active.pdf", {
      type: "application/pdf",
      lastModified: 13,
    });

    fireEvent.change(screen.getByLabelText("Choose PDF files"), {
      target: { files: [accepted, failed, active] },
    });

    const acceptedRequest = await waitForRequest(0);
    const failedRequest = await waitForRequest(1);
    expect(screen.getByText("3 active")).toBeVisible();

    act(() =>
      acceptedRequest.respond(202, {
        document: { id: "accepted", name: "Accepted.pdf" },
      }),
    );
    const activeRequest = await waitForRequest(2);
    act(() =>
      failedRequest.respond(400, {
        title: "Invalid PDF",
        detail: "The PDF could not be accepted.",
        status: 400,
        code: "INVALID_PDF",
      }),
    );

    const list = await screen.findByRole("list", { name: "Upload queue" });
    expect(within(list).queryByText("Accepted.pdf")).not.toBeInTheDocument();
    expect(within(list).getByText("Failed.pdf")).toBeVisible();
    expect(within(list).getByText("Active.pdf")).toBeVisible();
    expect(
      within(list).getByRole("button", { name: "Retry Failed.pdf" }),
    ).toBeVisible();
    expect(
      within(list).getByRole("button", { name: "Dismiss Failed.pdf" }),
    ).toBeVisible();
    expect(
      within(list).getByRole("progressbar", {
        name: "Uploading Active.pdf",
      }),
    ).toBeVisible();
    expect(screen.getByText("1 active")).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Accepted.pdf uploaded and queued for processing.",
    );
    await waitFor(() =>
      expect(invalidateQueries).toHaveBeenCalledWith({
        queryKey: ["documents"],
      }),
    );
    expect(activeRequest.aborted).toBe(false);
  });

  it("rejects a non-PDF before transport and permits dismissal", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
    const user = userEvent.setup();
    renderQueue();
    const file = new File(["not a pdf"], "unsafe.txt", {
      type: "text/plain",
    });

    fireEvent.change(screen.getByLabelText("Choose PDF files"), {
      target: { files: [file] },
    });

    expect(
      await screen.findByText(/Choose a file with a \.pdf extension\./),
    ).toBeVisible();
    expect(FakeXMLHttpRequest.instances).toHaveLength(0);
    expect(
      screen.queryByRole("button", { name: "Retry unsafe.txt" }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Dismiss unsafe.txt" }));
    expect(screen.queryByText("unsafe.txt")).not.toBeInTheDocument();
  });

  it("surfaces a safe server failure and retries only on request", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
    const user = userEvent.setup();
    renderQueue();
    const file = new File(["fictional"], "Broken.pdf", {
      type: "application/pdf",
    });

    await user.upload(screen.getByLabelText("Choose PDF files"), file);
    const failedRequest = await waitForRequest();
    act(() =>
      failedRequest.respond(400, {
        title: "Invalid PDF",
        detail: "The stored file does not have a valid PDF signature.",
        status: 400,
        code: "INVALID_PDF_SIGNATURE",
      }),
    );
    expect(
      await screen.findByText(/does not have a valid PDF signature/i),
    ).toBeVisible();
    expect(FakeXMLHttpRequest.instances).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Retry Broken.pdf" }));

    const retryRequest = await waitForRequest(1);
    act(() =>
      retryRequest.respond(503, {
        title: "Upload unavailable",
        detail: "The upload service is temporarily unavailable.",
        status: 503,
        code: "UPLOAD_UNAVAILABLE",
      }),
    );
    expect(
      await screen.findByText(/temporarily unavailable/i),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Retry Broken.pdf" }),
    ).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "Dismiss Broken.pdf" }),
    );
    expect(screen.queryByText("Broken.pdf")).not.toBeInTheDocument();
  });

  it("aborts an in-flight XHR when Strict Mode unmounts the queue", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
    const { setAutoFocus, unmount } = renderQueue();
    const file = new File(["%PDF-1.7 fictional"], "Unmounted.pdf", {
      type: "application/pdf",
    });

    fireEvent.change(screen.getByLabelText("Choose PDF files"), {
      target: { files: [file] },
    });
    const request = await waitForRequest();
    expect(request.aborted).toBe(false);

    setAutoFocus(true);
    expect(request.aborted).toBe(false);

    unmount();

    expect(request.aborted).toBe(true);
  });
});
