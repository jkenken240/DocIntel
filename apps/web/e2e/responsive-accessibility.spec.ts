import { expect, test } from "@playwright/test";

import { expectNoSeriousAccessibilityViolations } from "./support/accessibility";

test("important direct routes remain responsive, keyboard reachable, and reduced-motion aware", async ({
  page,
}, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Mobile navigation" })).toBeVisible();
  expect(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(
    true,
  );
  await expect(page.locator("#workspace-main")).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(
    page.locator(".mobile-header").getByRole("link", { name: "DocIntel overview" }),
  ).toBeFocused();
  await expectNoSeriousAccessibilityViolations(page, testInfo, "mobile-overview");

  await page.goto("/documents");
  await expect(
    page.getByRole("heading", { name: "Document library", exact: true }),
  ).toBeVisible();
  await expect(page.locator("#workspace-main")).toBeFocused();
  await expectNoSeriousAccessibilityViolations(page, testInfo, "mobile-documents");

  await page.goto("/ask");
  await expect(page.locator("#workspace-main")).toBeFocused();
  await expectNoSeriousAccessibilityViolations(page, testInfo, "mobile-ask");
});
