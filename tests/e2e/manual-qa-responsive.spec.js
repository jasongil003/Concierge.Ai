import { expect, test } from "@playwright/test";

const VIEWPORTS = [
  { width: 1920, height: 1080 },
  { width: 1440, height: 900 },
  { width: 1280, height: 720 },
  { width: 1024, height: 768 },
  { width: 768, height: 1024 },
  { width: 430, height: 932 },
  { width: 390, height: 844 },
  { width: 375, height: 812 },
];

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
  if (isMobile) await expect(shell).not.toHaveClass(/mobile-nav-open/);
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
  const pageErrors = [];
  const failedRequests = [];
  const serverErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(`${page.url()} :: ${message.text()}`);
  });
  page.on("pageerror", (error) => pageErrors.push(`${page.url()} :: ${error.message}`));
  page.on("requestfailed", (request) => failedRequests.push(`${request.method()} ${request.url()}`));
  page.on("response", (response) => {
    if (response.status() >= 500) serverErrors.push(`${response.status()} ${response.url()}`);
  });

  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
  const panels = await page.locator(".nav-item[data-panel]").evaluateAll((items) => [...new Set(items.map((item) => item.dataset.panel))]);
  for (const panel of panels) {
    await openAdminPanel(page, panel);
    await expectNoHorizontalOverflow(page, `Admin #${panel} at ${viewport.width}x${viewport.height}`);
  }

  await page.goto("/");
  await expect(page.locator("#home-view")).toBeVisible();
  await expectNoHorizontalOverflow(page, `Guest home at ${viewport.width}x${viewport.height}`);
  for (const [label, panel] of [["Explore", "#explore-view"], ["Requests", "#requests-view"], ["My Stay", "#stay-view"], ["Concierge", "#concierge-view"], ["Home", "#home-view"]]) {
    await page.getByRole("button", { name: label, exact: true }).click();
    await expect(page.locator(panel)).toBeVisible();
    await expectNoHorizontalOverflow(page, `Guest ${label} at ${viewport.width}x${viewport.height}`);
  }

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
  expect(serverErrors).toEqual([]);
});
}
