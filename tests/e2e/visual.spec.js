import { expect, test } from "@playwright/test";
import { ensureTestProperty } from "./support.js";

async function loginAdmin(page) {
  const response = await page.request.post("/api/admin/auth/login", {
    data: { username: "admin", password: "ChangeMe123!", remember_me: false },
  });
  expect(response.ok()).toBeTruthy();
  const csrf = (await response.json()).user.csrf_token;
  await ensureTestProperty(page.request, csrf);
  return csrf;
}

test.beforeEach(async ({ page }) => {
  const csrf = await loginAdmin(page);
  const existing = await (await page.request.get("/api/admin/properties")).json();
  for (const property of existing.properties || []) {
    const removed = await page.request.delete(`/api/admin/properties/${property.property_id}`, {
      headers: { "X-CSRF-Token": csrf },
    });
    expect(removed.ok()).toBeTruthy();
  }
  const created = await page.request.put("/api/admin/properties/e2e-property", {
    headers: { "X-CSRF-Token": csrf },
    data: { property_id: "e2e-property", hotel_name: "E2E Property", timezone: "Asia/Manila" },
  });
  expect(created.ok()).toBeTruthy();
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "light" });
  await page.addInitScript(() => {
    localStorage.setItem("concierge-intro-seen", "1");
    localStorage.removeItem("concierge-draft");
    localStorage.removeItem("concierge-accessibility");
  });
});

test("guest home visual baseline", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#suggestion-list button")).toHaveCount(0);

  await expect(page).toHaveScreenshot("guest-home.png", {
    animations: "disabled",
    caret: "hide",
    fullPage: true,
    maxDiffPixelRatio: 0.01,
  });
});

test("admin design panel visual baseline", async ({ page }) => {
  await loginAdmin(page);
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
  if ((page.viewportSize()?.width || 1200) <= 620) {
    await page.locator("#sidebar-toggle").click();
  }
  const designButton = page.locator(".nav-item").filter({ hasText: "Design" }).first();
  await designButton.evaluate((element) => {
    const group = element.closest("details");
    if (group) group.open = true;
  });
  await designButton.click();
  await expect(page.locator("#appearance")).toBeVisible();

  await expect(page.locator("#appearance")).toHaveScreenshot("admin-design.png", {
    animations: "disabled",
    caret: "hide",
    maxDiffPixelRatio: 0.01,
  });
});
