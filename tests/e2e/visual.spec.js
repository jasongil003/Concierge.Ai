import { expect, test } from "@playwright/test";

async function loginAdmin(page) {
  const response = await page.request.post("/api/admin/auth/login", {
    data: { username: "admin", password: "ChangeMe123!", remember_me: false },
  });
  expect(response.ok()).toBeTruthy();
}

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "light" });
  await page.addInitScript(() => {
    localStorage.setItem("concierge-intro-seen", "1");
    localStorage.removeItem("concierge-draft");
    localStorage.removeItem("concierge-accessibility");
  });
});

test("guest home visual baseline", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#suggestion-list button").first()).toBeVisible();

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
