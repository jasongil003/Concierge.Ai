import { expect, test } from "@playwright/test";
import { prepareGuestFixture } from "./support.js";

test.beforeEach(async ({ request }) => prepareGuestFixture(request));

test("guest privacy explains staff access and retained conversations truthfully", async ({ page }) => {
  await page.route("**/api/guest/intro**", (route) => route.fulfill({
    json: { mode: "none", first_visit_only: true, allow_skip: true },
  }));
  await page.goto("/");
  await expect(page.locator("#home-view")).toBeVisible();
  await expect(page.locator("#concierge-card")).not.toContainText("Private conversation");
  await expect(page.locator(".privacy-note")).toContainText("Authorized hotel staff can review retained conversations");
  await expect(page.locator("#restaurant-staff-dialog")).toContainText("Authorized hotel staff can also review retained concierge conversations");
  await page.locator(".experience-configured-header .experience-configured-menu").click();
  await page.locator('[data-menu-action="privacy"]').click();
  const messages = page.locator("#message-list");
  await expect(messages).toContainText("Authorized hotel staff can review conversation history");
  await expect(messages).toContainText("closing this page does not delete them");
  await expect(messages).not.toContainText("aren't shown to hotel staff");
  await expect(messages).not.toContainText("Chat context stays in this open session");
});
