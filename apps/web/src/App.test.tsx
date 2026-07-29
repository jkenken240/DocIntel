import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

describe("App", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows dependency checks returned by the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            status: "ready",
            checks: {
              database: {
                status: "ready",
                detail: "PostgreSQL query succeeded.",
              },
              provider: {
                status: "ready",
                detail: "Deterministic mock provider configured.",
              },
            },
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    renderApp();

    expect(
      screen.getByRole("heading", { name: "DocIntel platform foundation" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("PostgreSQL query succeeded.")).toBeVisible();
    expect(screen.getByText("Ready")).toBeVisible();
  });

  it("reports an unavailable API without presenting false readiness", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    renderApp();

    expect(
      await screen.findByText(/The API could not be reached/i),
    ).toBeVisible();
    expect(screen.getByText("Not ready")).toBeVisible();
  });
});
