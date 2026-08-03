import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { expect, request as playwrightRequest, test, type Page } from "@playwright/test";

import { expectNoSeriousAccessibilityViolations } from "./support/accessibility";
import { writeFictionalPdf } from "./support/fictionalPdf";
import { attachPdfViewerFailure, observePdfViewer } from "./support/viewerDiagnostics";

const apiBaseUrl = (
  process.env.DOCINTEL_E2E_API_URL ?? "http://127.0.0.1:8000/api/v1"
).replace(/\/$/, "");
const runId = (process.env.DOCINTEL_E2E_RUN_ID ?? "local").replace(/[^a-zA-Z0-9-]/g, "-");
const atlasName = `Phase7B Atlas ${runId}.pdf`;
const novaName = `Phase7B Nova ${runId}.pdf`;
const atlasEvidence = "Atlas audit records are retained for seven years.";
const novaEvidence = "Nova audit records are retained for nine years.";

interface ApiDocument {
  id: string;
  name: string;
  status: string;
}

async function preciseCleanup(): Promise<void> {
  const api = await playwrightRequest.newContext();
  try {
    const response = await api.get(
      `${apiBaseUrl}/documents?limit=100&sort=created_at&order=desc`,
    );
    if (!response.ok()) return;
    const payload = (await response.json()) as { items?: ApiDocument[] };
    for (const document of payload.items ?? []) {
      if (document.name !== atlasName && document.name !== novaName) continue;
      const deletion = await api.delete(`${apiBaseUrl}/documents/${document.id}`);
      if (deletion.status() !== 202 && deletion.status() !== 404) {
        throw new Error(`Cleanup deletion failed for ${document.id}: ${deletion.status()}`);
      }
      await expect
        .poll(async () => (await api.get(`${apiBaseUrl}/documents/${document.id}`)).status(), {
          timeout: 30_000,
        })
        .toBe(404);
    }
  } finally {
    await api.dispose();
  }
}

async function documentIdFor(filename: string): Promise<string> {
  const api = await playwrightRequest.newContext();
  try {
    const response = await api.get(
      `${apiBaseUrl}/documents?limit=100&sort=created_at&order=desc`,
    );
    expect(response.ok()).toBe(true);
    const payload = (await response.json()) as { items?: ApiDocument[] };
    const document = (payload.items ?? []).find((item) => item.name === filename);
    expect(document, `Expected ${filename} in the document API`).toBeDefined();
    return document!.id;
  } finally {
    await api.dispose();
  }
}

function documentRow(page: Page, filename: string) {
  return page.getByRole("listitem").filter({ hasText: filename });
}

test.describe("production DocIntel workflow", () => {
  test.describe.configure({ mode: "serial" });
  let fixtureRoot = "";
  let atlasPath = "";
  let novaPath = "";
  let invalidPath = "";

  test.beforeAll(async () => {
    await preciseCleanup();
    fixtureRoot = await mkdtemp(path.join(tmpdir(), "docintel-phase7b-"));
    atlasPath = path.join(fixtureRoot, atlasName);
    novaPath = path.join(fixtureRoot, novaName);
    invalidPath = path.join(fixtureRoot, `Phase7B invalid ${runId}.txt`);
    await writeFictionalPdf(atlasPath, [
      "Atlas Governance is a fictional organization used only for testing.",
      atlasEvidence,
    ]);
    await writeFictionalPdf(novaPath, [
      "Nova Controls is a fictional organization used only for testing.",
      "This deliberately blank-topic page preserves page numbering.",
      novaEvidence,
    ]);
    await writeFile(invalidPath, "This is deliberately not a PDF.", "utf8");
  });

  test.afterAll(async () => {
    await preciseCleanup();
    if (fixtureRoot) await rm(fixtureRoot, { recursive: true, force: true });
  });

  test("uploads, grounds, cites, refuses, and deletes through the UI", async ({
    page,
  }, testInfo) => {
    const viewerObservation = observePdfViewer(page);
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Turn dense PDFs into answers you can inspect." }),
    ).toBeVisible();
    await expectNoSeriousAccessibilityViolations(page, testInfo, "overview");

    await page.goto("/documents");
    await expect(
      page.getByRole("heading", { name: "Document library", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("0 documents", { exact: true })).toBeVisible();
    await expectNoSeriousAccessibilityViolations(page, testInfo, "documents-empty");

    const acceptedResponses: number[] = [];
    page.on("response", (response) => {
      if (
        response.request().method() === "POST" &&
        response.url() === `${apiBaseUrl}/documents`
      ) {
        acceptedResponses.push(response.status());
      }
    });
    await page.getByLabel("Choose PDF files").setInputFiles([atlasPath, novaPath]);
    await expect.poll(() => acceptedResponses.length, { timeout: 30_000 }).toBe(2);
    expect(acceptedResponses).toEqual([202, 202]);

    await page.getByLabel("Choose PDF files").setInputFiles(invalidPath);
    await expect(page.getByText("Choose a file with a .pdf extension.")).toBeVisible();
    await expectNoSeriousAccessibilityViolations(page, testInfo, "upload-validation");
    await page.getByRole("button", { name: `Dismiss Phase7B invalid ${runId}.txt` }).click();

    await expect(documentRow(page, atlasName)).toBeVisible();
    await expect(documentRow(page, novaName)).toBeVisible();
    await expect(documentRow(page, atlasName).getByText("Evidence ready")).toBeVisible({
      timeout: 90_000,
    });
    await expect(documentRow(page, novaName).getByText("Evidence ready")).toBeVisible({
      timeout: 90_000,
    });
    const atlasDocumentId = await documentIdFor(atlasName);

    await page.getByRole("searchbox", { name: "Search documents" }).fill("Atlas");
    await expect(documentRow(page, atlasName)).toBeVisible();
    await expect(documentRow(page, novaName)).toHaveCount(0);
    await page.getByRole("button", { name: "Clear document search" }).click();
    await page.getByLabel("Filter by status").selectOption("ready");
    await expect(documentRow(page, atlasName)).toBeVisible();
    await expect(documentRow(page, novaName)).toBeVisible();

    await page.getByLabel(`Select ${atlasName} as a question source`).check();
    await page.getByLabel(`Select ${novaName} as a question source`).check();
    await expect(page.getByText("2 READY sources selected")).toBeVisible();
    await page.getByRole("link", { name: "Ask with selection" }).click();

    await expect(
      page.getByRole("heading", { name: "Ask the evidence, not a chatbot." }),
    ).toBeVisible();
    await expect(page.getByLabel("Selected documents").getByText(atlasName)).toBeVisible();
    await expect(page.getByLabel("Selected documents").getByText(novaName)).toBeVisible();
    await expectNoSeriousAccessibilityViolations(page, testInfo, "ask-selected-sources");

    await page.getByLabel("Question for DocIntel").fill("How long are audit records retained?");
    await page.getByRole("button", { name: "Ask DocIntel" }).click();
    await expect(page).toHaveURL(/\/questions\/[0-9a-f-]+$/i, { timeout: 60_000 });
    const answeredPath = new URL(page.url()).pathname;
    await expect(page.getByText("Claims and citations")).toBeVisible();
    await expect(page.getByText("2 evidence records")).toBeVisible();
    await expectNoSeriousAccessibilityViolations(page, testInfo, "grounded-answer");

    const atlasCitation = page.getByRole("button", {
      name: new RegExp(`Open citation 1 for claim \\d+: ${atlasName.replace(".", "\\.")}, page 2`, "i"),
    });
    const novaCitation = page.getByRole("button", {
      name: new RegExp(`Open citation 1 for claim \\d+: ${novaName.replace(".", "\\.")}, page 3`, "i"),
    });
    await expect(atlasCitation).toBeVisible();
    await expect(novaCitation).toBeVisible();

    await atlasCitation.click();
    await expect(page.getByRole("heading", { name: atlasName })).toBeVisible();
    await expect(page.locator(".page-chip").filter({ hasText: "Page 2" })).toBeVisible();
    await expect(page.locator("blockquote").filter({ hasText: atlasEvidence })).toBeVisible();
    try {
      const canvas = page.getByLabel("Rendered PDF page 2");
      await expect(canvas).toBeVisible({ timeout: 30_000 });
      const dimensions = await canvas.evaluate((element) => {
        const value = element as HTMLCanvasElement;
        return { width: value.width, height: value.height };
      });
      expect(dimensions.width).toBeGreaterThan(0);
      expect(dimensions.height).toBeGreaterThan(0);
    } catch (error) {
      await attachPdfViewerFailure(page, testInfo, viewerObservation);
      throw error;
    }
    await expectNoSeriousAccessibilityViolations(page, testInfo, "evidence-pdf");

    await novaCitation.click();
    await expect(page.getByRole("heading", { name: novaName })).toBeVisible();
    await expect(page.locator(".page-chip").filter({ hasText: "Page 3" })).toBeVisible();
    await expect(page.locator("blockquote").filter({ hasText: novaEvidence })).toBeVisible();
    await expect(page.getByLabel("Rendered PDF page 3")).toBeVisible({ timeout: 30_000 });

    await page.goto(answeredPath);
    await expect(page.getByText("Claims and citations")).toBeVisible();

    await page.getByRole("link", { name: "Ask another question" }).click();
    await page.getByLabel("Question for DocIntel").fill("What is the lunar launch password?");
    await page.getByRole("button", { name: "Ask DocIntel" }).click();
    await expect(
      page.getByRole("heading", { name: "The evidence was not strong enough" }),
    ).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText(/did not display an answer or citations/i)).toBeVisible();
    await expectNoSeriousAccessibilityViolations(page, testInfo, "insufficient-evidence");

    await page.goto("/documents");
    await page.getByLabel("Filter by status").selectOption("ready");
    const deleteButton = page.getByRole("button", { name: `Delete ${atlasName}` });
    await deleteButton.click();
    const dialog = page.getByRole("dialog", { name: `Delete ${atlasName}?` });
    await expect(dialog).toBeVisible();
    await expect(page.getByRole("button", { name: "Keep document" })).toBeFocused();
    await expectNoSeriousAccessibilityViolations(page, testInfo, "confirmation-dialog");
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(deleteButton).toBeFocused();

    await deleteButton.click();
    await page.getByRole("button", { name: "Delete document" }).click();
    await expect(page.getByText(`Deletion accepted for ${atlasName}.`)).toBeVisible();
    await expect(documentRow(page, atlasName)).toHaveCount(0, { timeout: 60_000 });

    const api = await playwrightRequest.newContext();
    try {
      await expect
        .poll(
          async () =>
            (await api.get(`${apiBaseUrl}/documents/${atlasDocumentId}`)).status(),
          { timeout: 60_000 },
        )
        .toBe(404);
    } finally {
      await api.dispose();
    }

    await page.goto(answeredPath);
    await expect(
      page.getByRole("heading", { name: "This grounded result is no longer available" }),
    ).toBeVisible();
  });
});
