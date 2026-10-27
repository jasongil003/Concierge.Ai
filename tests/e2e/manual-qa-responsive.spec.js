import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const VIEWPORTS = [
  { width: 1920, height: 1080 },
  { width: 1440, height: 900 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
  { width: 375, height: 812 },
];
const AUDIT_DIRECTORY = process.env.PLAYWRIGHT_AUDIT_DIR || "test-results/manual-qa";

function screenshotPath(section, view, viewport) {
  const device = viewport.width >= 1000 ? "desktop" : viewport.width >= 700 ? "tablet" : "mobile";
  const directory = join(AUDIT_DIRECTORY, "screenshots", section, device);
  mkdirSync(directory, { recursive: true });
  return join(directory, `${view}-${viewport.width}x${viewport.height}.png`);
}

async function signIn(page) {
  const response = await page.request.post("/api/admin/auth/login", {
    data: { username: "admin", password: "PlaywrightOnly-Admin-123!", remember_me: false },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  const auth = (await response.json()).user;
  const properties = await page.request.get("/api/admin/properties");
  expect(properties.ok()).toBeTruthy();
  if (!(await properties.json()).properties.length) {
    const created = await page.request.put("/api/admin/properties/e2e-property", {
      headers: { "X-CSRF-Token": auth.csrf_token },
      data: { property_id: "e2e-property", hotel_name: "E2E Property", timezone: "Asia/Manila" },
    });
    expect(created.ok(), await created.text()).toBeTruthy();
  }
}

async function openAdminPanel(page, panel) {
  const isMobile = page.viewportSize().width <= 620;
  const shell = page.locator(".platform-shell");
  if (isMobile && !(await shell.evaluate((element) => element.classList.contains("mobile-nav-open")))) {
    await page.locator("#sidebar-toggle").click();
    await expect(shell).toHaveClass(/mobile-nav-open/);
  }
  const item = page.locator(`.nav-item[data-panel="${panel}"]`).first();
  await item.evaluate((element) => {
    const group = element.closest("details.nav-group");
    if (group) group.open = true;
  });
  await item.scrollIntoViewIfNeeded();
  await item.click();
  await expect(page.locator(".panel.active")).toHaveAttribute("id", panel);
  await expect(page.locator(".panel.active > .page-title h1, .panel.active > .onboarding-card h1").first()).toBeVisible();
  if (isMobile) {
    await expect(shell).not.toHaveClass(/mobile-nav-open/);
    await expect.poll(() => page.locator(".platform-sidebar").evaluate((element) => {
      const offset = new DOMMatrixReadOnly(getComputedStyle(element).transform).m41;
      return offset <= -element.getBoundingClientRect().width;
    })).toBeTruthy();
  }
}

async function waitForSettledPanel(page, panel) {
  if (["overview", "alerts", "analytics", "reports", "system-health"].includes(panel)) {
    const summary = page.locator("#system-health-summary strong");
    await expect(summary).not.toHaveText(/^(Loading system checks|Checking system health)$/);
  }
  if (panel === "conversations") {
    await expect(page.locator("#refresh-conversations")).toBeEnabled();
    await expect(page.locator("#refresh-conversations")).toHaveText("Refresh inbox");
    await expect(page.locator("#conversation-list")).not.toContainText("Loading inbox");
  }
  if (["knowledge", "documents", "faqs"].includes(panel)) {
    await expect(page.locator("#knowledge-health")).not.toContainText("Loading measured coverage");
  }
  if (panel === "location") {
    await expect(page.locator("#location-directory-stats")).not.toContainText("Loading directory");
    await expect(page.locator("#location-facility-count")).not.toHaveText("Loading…");
    await expect(page.locator("#location-map-publication")).not.toContainText("loading");
  }
  if (panel === "personalization-settings") {
    await expect(page.locator("#personalization-consent-total")).not.toHaveText("Loading");
    await expect(page.locator("#personalization-consent-summary")).not.toContainText("Consent totals are loading");
  }
  if (panel === "guest") {
    await expect(page.locator("#guest-module-count")).not.toContainText("Loading modules");
  }
}

async function expectNoHorizontalOverflow(page, label) {
  const measurement = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
    offenders: [...document.querySelectorAll("body *")].map((element) => {
      const rect = element.getBoundingClientRect();
      return { tag: element.tagName, id: element.id, className: typeof element.className === "string" ? element.className : "", left: Math.round(rect.left), right: Math.round(rect.right), width: Math.round(rect.width) };
    }).filter((item) => item.width > 0 && item.right > window.innerWidth + 1).sort((a, b) => b.right - a.right).slice(0, 8),
  }));
  expect(measurement.document, `${label}: ${JSON.stringify(measurement)}`).toBeLessThanOrEqual(measurement.viewport + 1);
  expect(measurement.body, `${label}: ${JSON.stringify(measurement)}`).toBeLessThanOrEqual(measurement.viewport + 1);
}

for (const viewport of VIEWPORTS) {
test(`manual QA responsive matrix covers every admin destination at ${viewport.width}x${viewport.height}`, async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The viewport matrix runs once in Chromium.");
  test.setTimeout(180_000);
  await signIn(page);
  await page.setViewportSize(viewport);

  const consoleErrors = [];
  mkdirSync(AUDIT_DIRECTORY, { recursive: true });
  const pageErrors = [];
  const failedRequests = [];
  const serverErrors = [];
  const notFoundResponses = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => failedRequests.push(`${request.method()} ${request.url()}`));
  page.on("response", (response) => {
    if (response.status() === 404) {
      const request = response.request();
      notFoundResponses.push(`${request.method()} ${response.url()} [${request.resourceType()}${request.isNavigationRequest() ? ", navigation" : ""}]`);
    }
    if (response.status() >= 500) serverErrors.push(`${response.status()} ${response.url()}`);
  });

  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
  const panels = await page.locator(".nav-item[data-panel]").evaluateAll((items) => [...new Set(items.map((item) => item.dataset.panel))]);
  for (const panel of panels) {
    await openAdminPanel(page, panel);
    await waitForSettledPanel(page, panel);
    if (panel === "requests") {
      await expect(page.locator("#request-last-updated")).toContainText("Updated");
      await expect(page.locator("#service-request-list .request-queue-state")).toHaveCount(0);
    }
    await expectNoHorizontalOverflow(page, `Admin #${panel} at ${viewport.width}x${viewport.height}`);
    await page.screenshot({ path: screenshotPath("admin", `admin-${panel}`, viewport), fullPage: true });
  }

  await page.goto("/");
  await expect(page.locator("#home-view")).toBeVisible();
  await expectNoHorizontalOverflow(page, `Guest home at ${viewport.width}x${viewport.height}`);
  await page.screenshot({ path: screenshotPath("guest", "guest-home", viewport), fullPage: true });
  const guestNavigation = page.locator(".experience-configured-navigation");
  await expect(guestNavigation).toBeVisible();
  for (const [label, panel] of [["Explore", "#explore-view"], ["Requests", "#requests-view"], ["My Stay", "#stay-view"], ["Concierge", "#concierge-view"], ["Home", "#home-view"]]) {
    await guestNavigation.getByRole("button", { name: label, exact: true }).click();
    await expect(page.locator(panel)).toBeVisible();
    await expectNoHorizontalOverflow(page, `Guest ${label} at ${viewport.width}x${viewport.height}`);
    await page.screenshot({ path: screenshotPath("guest", `guest-${label.toLowerCase().replaceAll(" ", "-")}`, viewport), fullPage: true });
  }

  expect(pageErrors).toEqual([]);
  expect(consoleErrors, JSON.stringify({ notFoundResponses })).toEqual([]);
  expect(notFoundResponses).toEqual([]);
  expect(failedRequests).toEqual([]);
  expect(serverErrors).toEqual([]);
});
}
