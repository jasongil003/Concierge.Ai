import { expect, test } from "@playwright/test";

const csrfByRequest = new WeakMap();

async function loginAdmin(api) {
  const response = await api.post("/api/admin/auth/login", {
    data: { username: "admin", password: "PlaywrightOnly-Admin-123!", remember_me: false },
  });
  expect(response.ok()).toBeTruthy();
  csrfByRequest.set(api, (await response.json()).user.csrf_token);
  const properties = await api.get("/api/admin/properties");
  expect(properties.ok()).toBeTruthy();
  if (!(await properties.json()).properties.length) {
    const created = await api.put("/api/admin/properties/campaign-e2e-property", {
      headers: { "X-CSRF-Token": csrfByRequest.get(api) },
      data: { property_id: "campaign-e2e-property", hotel_name: "Campaign E2E Property", timezone: "Asia/Manila" },
    });
    expect(created.ok()).toBeTruthy();
  }
}

async function openCampaignPanel(page) {
  await page.locator('body[data-admin-ready="true"]').waitFor();
  if ((page.viewportSize()?.width || 1440) <= 620) {
    const shell = page.locator(".platform-shell");
    if (!(await shell.evaluate((element) => element.classList.contains("mobile-nav-open")))) await page.locator("#sidebar-toggle").click();
    await page.locator("details.nav-group").evaluateAll((groups) => { for (const group of groups) group.open = false; });
  }
  const button = page.locator('.nav-item[data-nav-id="notification-campaigns"]');
  await button.evaluate((element) => { const group = element.closest("details"); if (group) group.open = true; });
  await button.scrollIntoViewIfNeeded();
  await button.click();
}

test.beforeEach(async ({ page, request }) => {
  await loginAdmin(request);
  await loginAdmin(page.request);
});

test("notification campaigns: save, preview aggregate consent, and confirm in-app publish", async ({ page }) => {
  let campaigns = [];
  await page.route("**/api/admin/properties/*/notification-campaigns**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (request.method() === "GET" && path.endsWith("/notification-campaigns")) {
      await route.fulfill({ json: { campaigns } });
      return;
    }
    if (request.method() === "POST" && path.endsWith("/notification-campaigns")) {
      const body = request.postDataJSON();
      const campaign = {
        campaign_id: "campaign-e2e-1", property_id: "e2e-property", ...body,
        audience: "active_stays_with_promotional_consent", status: "draft", revision: 1,
        queued_count: 0, suppressed_count: 0, engagement: { read: 0 },
      };
      campaigns = [campaign];
      await route.fulfill({ json: { campaign } });
      return;
    }
    if (request.method() === "POST" && path.endsWith("/preview")) {
      await route.fulfill({ json: {
        campaign_id: "campaign-e2e-1", revision: 1,
        audience: "active_stays_with_promotional_consent", active_stays: 3, eligible: 2,
        no_active_guest_session: 0, promotional_consent_required: 1, promotional_preference_disabled: 0,
      } });
      return;
    }
    if (request.method() === "POST" && path.endsWith("/publish")) {
      const campaign = { ...campaigns[0], status: "published", revision: 3, queued_count: 2, suppressed_count: 1 };
      campaigns = [campaign];
      await route.fulfill({ json: {
        campaign, audience: "active_stays_with_promotional_consent", active_stays_at_preview: 3,
        eligible_at_preview: 2, queued: 2, already_queued: 0, suppressed_at_publish: 1,
        delivery_state: "queued_in_app; delivery and guest read acknowledgement are recorded separately",
      } });
      return;
    }
    await route.continue();
  });

  await page.goto("/admin");
  await openCampaignPanel(page);
  await expect(page.locator("#notification-campaigns")).toBeVisible();
  await page.locator("#notification-campaign-name").fill("Pool hours update");
  await page.locator("#notification-campaign-title").fill("Pool hours this week");
  await page.locator("#notification-campaign-body").fill("The pool closes at 8 PM this week.");
  await page.locator("#notification-campaign-source").fill("operations-event-2026-10-16");
  await page.locator("#notification-campaign-save").click();
  await expect(page.locator("#notification-campaign-list")).toContainText("Pool hours update");
  await page.locator("#notification-campaign-preview-button").click();
  await expect(page.locator("#notification-campaign-preview")).toContainText("2 eligible of 3 active stays");
  await expect(page.locator("#notification-campaign-preview")).toContainText("1 missing promotional consent");
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("#notification-campaign-publish").click();
  await expect(page.locator("#notification-campaign-preview")).toContainText("2 queued in-app");
  await expect(page.locator("#notification-campaign-list")).toContainText("published");
  await expect(page.locator("#notification-campaign-list")).toContainText("2 queued");
});
