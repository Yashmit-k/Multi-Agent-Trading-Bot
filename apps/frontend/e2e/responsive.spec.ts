import { test, expect } from "@playwright/test";

test("layout is usable on the configured viewport", async ({ page }) => {
  test.skip(!process.env.PLAYWRIGHT_BASE_URL && !process.env.CI, "requires a running frontend");
  await page.setViewportSize({ width: 375, height: 720 });
  await page.goto("/dashboard");
  await expect(page.getByTestId("mode-banner")).toBeVisible();
});
