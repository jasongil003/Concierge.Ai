import { expect, test } from "@playwright/test";
import { prepareGuestFixture } from "./support.js";

test.beforeEach(async ({ request }) => prepareGuestFixture(request));

test("guest home and concierge retain aligned content with classic scrollbars", async ({ page }) => {
  await page.route("**/api/guest/intro**", (route) => route.fulfill({ json: { mode: "none" } }));
  // Keep the application's CSP intact; extend its same-origin stylesheet.
  await page.route("**/static/styles.css*", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, body: `${await response.text()}\n.guest-view::-webkit-scrollbar { width: 15px; }` });
  });
  await page.goto("/");
  await expect(page.locator(".experience-configured-navigation")).toBeVisible();
  // Explicit widths reproduce non-overlay Linux/Windows scrollbars on macOS too.
  for (const width of [320, 375, 768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await page.locator(".experience-configured-navigation").getByRole("button", { name: "Home", exact: true }).click();
    await expect(page.locator(".experience-hero")).toBeVisible();
    const hero = await page.locator(".experience-hero").boundingBox();
    await page.locator(".experience-configured-navigation").getByRole("button", { name: "Concierge", exact: true }).click();
    await expect(page.locator("#concierge-card")).toBeVisible();
    const card = await page.locator("#concierge-card").boundingBox();
    expect(hero.x, `home/chat left edge at ${width}px`).toBeCloseTo(card.x, 0);
    expect(hero.width, `home/chat content width at ${width}px`).toBeCloseTo(card.width, 0);
  }
});
