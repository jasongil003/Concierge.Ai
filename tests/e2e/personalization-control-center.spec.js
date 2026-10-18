import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { ensureTestProperty } from "./support.js";

const csrfByRequest = new WeakMap();

async function loginAdmin(api) {
  const response = await api.post("/api/admin/auth/login", {
    data: { username: "admin", password: "PlaywrightOnly-Admin-123!", remember_me: false },
  });
  expect(response.ok()).toBeTruthy();
  const csrf = (await response.json()).user.csrf_token;
  csrfByRequest.set(api, csrf);
  return ensureTestProperty(api, csrf);
}

test.beforeEach(async ({ page }) => {
  await loginAdmin(page.request);
});

test("personalization control center explains choices, protects drafts, and reflows", async ({ page }, testInfo) => {
  const api = page.request;
  const propertyId = await ensureTestProperty(api, csrfByRequest.get(api));
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
  await page.evaluate(() => window.activatePanel("personalization-settings"));
  await expect(page.getByRole("heading", { name: "Personalization Control Center" })).toBeVisible();
  await expect(page.getByText("Property availability is not guest consent")).toBeVisible();
  await expect(page.locator("#personalization-overview-status")).toContainText(/Available|Off/);

  await page.getByRole("tab", { name: "Privacy & memory" }).click();
  await expect(page.getByRole("heading", { name: "What each privacy level means" })).toBeVisible();
  await page.getByRole("button", { name: "Preview guest choices" }).click();
  const preview = page.getByRole("dialog", { name: "Privacy choices" });
  await expect(preview).toBeVisible();
  await expect(preview.getByText("Allow external service providers to process data for concierge features.")).toBeVisible();
  await expect(preview.locator("input[type=checkbox]:checked")).toHaveCount(0);
  await page.getByRole("button", { name: "Close guest privacy preview" }).click();
  await expect(preview).toBeHidden();

  const learning = page.locator("#personalization-learning");
  const originalLearning = await learning.isChecked();
  await learning.setChecked(!originalLearning);
  await expect(page.locator("#personalization-save-state")).toHaveText("Unsaved changes");
  await expect(page.locator("#save-personalization-policy")).toBeEnabled();
  await page.getByRole("button", { name: "Discard changes" }).click();
  await expect(learning).toBeChecked({ checked: originalLearning });
  await expect(page.locator("#save-personalization-policy")).toBeDisabled();

  await page.getByRole("tab", { name: "Sources & integrations" }).click();
  const policyResponse = await api.get(`/api/admin/properties/${propertyId}/personalization`);
  expect(policyResponse.ok()).toBeTruthy();
  const originalInternet = (await policyResponse.json()).allow_internet_recommendations;
  const internet = page.locator("#personalization-internet");
  await internet.setChecked(!originalInternet);
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.locator("#personalization-save-state")).toHaveText("All changes saved");
  await expect(page.locator("#save-personalization-policy")).toBeDisabled();
  const savedPolicy = await api.get(`/api/admin/properties/${propertyId}/personalization`).then((response) => response.json());
  expect(savedPolicy.allow_internet_recommendations).toBe(!originalInternet);
  await page.reload();
  await page.locator('body[data-admin-ready="true"]').waitFor();
  await page.evaluate(() => window.activatePanel("personalization-settings"));
  await page.getByRole("tab", { name: "Sources & integrations" }).click();
  await expect(page.locator("#personalization-internet")).toBeChecked({ checked: !originalInternet });
  await page.locator("#personalization-internet").setChecked(originalInternet);
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.locator("#personalization-save-state")).toHaveText("All changes saved");

  await page.getByRole("tab", { name: "Sources & integrations" }).focus();
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByRole("tab", { name: "Privacy & memory" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Sources & integrations" }).click();
  await expect(page.getByRole("heading", { name: "Hotel-managed and external suggestions" })).toBeVisible();
  await expect(page.locator("#personalization-pms-status")).toContainText("No PMS sync");

  const diagnostic = await api.get(`/api/admin/properties/${propertyId}/personalization/diagnostics`);
  expect(diagnostic.ok()).toBeTruthy();
  const diagnosticBody = await diagnostic.json();
  expect(diagnosticBody.cleanup.status).toBe("not_tracked");
  expect(diagnosticBody.pms.sync_provider).toBe("not_configured");
  expect(JSON.stringify(diagnosticBody)).not.toContain("api_key_value");

  if (testInfo.project.name === "chromium") {
    mkdirSync(join(process.cwd(), "test-results", "personalization-control-center"), { recursive: true });
    await page.locator("#toast").evaluate((element) => element.classList.remove("show"));
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole("tab", { name: "Overview" }).click();
    await page.screenshot({
      path: join(process.cwd(), "test-results", "personalization-control-center", "overview.png"),
      animations: "disabled",
    });
    await page.getByRole("tab", { name: "Privacy & memory" }).click();
    await page.screenshot({
      path: join(process.cwd(), "test-results", "personalization-control-center", "memory.png"),
      animations: "disabled",
    });
    await page.locator("#personalization-supported-categories").scrollIntoViewIfNeeded();
    await page.screenshot({
      path: join(process.cwd(), "test-results", "personalization-control-center", "memory-details.png"),
      animations: "disabled",
    });
    await page.getByRole("tab", { name: "Sources & integrations" }).click();
    await page.locator("#personalization-policy-history").scrollIntoViewIfNeeded();
    await page.screenshot({
      path: join(process.cwd(), "test-results", "personalization-control-center", "sources-details.png"),
      animations: "disabled",
    });
    await page.locator(".platform-main").evaluate((element) => { element.scrollTop = 0; });
    for (const [width, height, name] of [
      [1440, 1000, "desktop"],
      [768, 1024, "tablet"],
      [390, 844, "mobile"],
    ]) {
      await page.setViewportSize({ width, height });
      await page.waitForTimeout(100);
      if (width <= 620 && await page.locator(".platform-shell").evaluate((element) => element.classList.contains("mobile-nav-open"))) {
        await page.locator("#sidebar-toggle").click();
      }
      await expect(page.locator("#personalization-settings")).toBeVisible();
      const dimensions = await page.locator("#personalization-settings").evaluate((element) => ({
        scrollWidth: element.scrollWidth,
        clientWidth: element.clientWidth,
        shell: document.querySelector(".platform-shell").className,
        overflowing: [...element.querySelectorAll("*")]
          .filter((child) => child.scrollWidth > child.clientWidth + 1)
          .slice(0, 5)
          .map((child) => ({ selector: child.id || child.className || child.tagName, scrollWidth: child.scrollWidth, clientWidth: child.clientWidth })),
      }));
      expect(dimensions.scrollWidth <= dimensions.clientWidth + 1, `${name} viewport should not overflow horizontally (${JSON.stringify(dimensions)})`).toBeTruthy();
      await page.screenshot({
        path: join(process.cwd(), "test-results", "personalization-control-center", `${name}.png`),
        animations: "disabled",
      });
    }
  }
});
