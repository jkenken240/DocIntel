import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type TestInfo } from "@playwright/test";

export async function expectNoSeriousAccessibilityViolations(
  page: Page,
  testInfo: TestInfo,
  state: string,
): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  const violations = results.violations.filter(
    ({ impact }) => impact === "critical" || impact === "serious",
  );
  if (violations.length > 0) {
    await testInfo.attach(`axe-${state}.json`, {
      body: Buffer.from(JSON.stringify(violations, null, 2)),
      contentType: "application/json",
    });
  }
  expect(violations, `${state} has serious or critical axe violations`).toEqual([]);
}
