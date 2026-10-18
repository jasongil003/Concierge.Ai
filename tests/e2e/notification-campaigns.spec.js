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
      const status = url.searchParams.get("status") || "all";
      const filtered = campaigns.filter((campaign) => status === "all" || (status === "expired" ? Number(campaign.engagement?.expired || 0) > 0 : campaign.status === status));
      const status_counts = Object.fromEntries(["draft", "publishing", "published", "failed"].map((value) => [value, campaigns.filter((campaign) => campaign.status === value).length]));
      const delivery_counts = Object.fromEntries(["queued", "sent", "delivered", "read", "failed", "expired"].map((value) => [value, campaigns.reduce((sum, campaign) => sum + Number(campaign.engagement?.[value] || 0), 0)]));
      await route.fulfill({ json: { campaigns: filtered, total: filtered.length, limit: 25, offset: 0, status_counts, delivery_counts } });
      return;
    }
    if (request.method() === "POST" && path.endsWith("/notification-campaigns")) {
      const body = request.postDataJSON();
      const campaign = {
        campaign_id: "campaign-e2e-1", property_id: "e2e-property", ...body,
        audience: "active_stays_with_promotional_consent", status: "draft", revision: 1,
        created_by: "Campaign Admin",
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
      const campaign = { ...campaigns[0], status: "published", revision: 3, queued_count: 2, suppressed_count: 1, engagement: { queued: 2, sent: 0, delivered: 0, read: 0, failed: 0, expired: 0 } };
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
  await page.locator("#notification-campaign-new").click();
  await expect(page.locator("#notification-campaign-dialog")).toBeVisible();
  await page.locator("#notification-campaign-name").fill("Pool hours update");
  await page.locator("#notification-campaign-title").fill("Pool hours this week");
  await page.locator("#notification-campaign-body").fill("The pool closes at 8 PM this week.");
  await expect(page.locator("#notification-message-preview-title")).toHaveText("Pool hours this week");
  await expect(page.locator("#notification-message-preview-body")).toHaveText("The pool closes at 8 PM this week.");
  await page.locator("#notification-campaign-source").fill("operations-event-2026-10-16");
  await page.locator("#notification-campaign-dialog").screenshot({ path: "test-results/notification-center/campaign-drawer-content.png" });
  await page.locator("#notification-campaign-save").click();
  await expect(page.locator("#notification-campaign-list")).toContainText("Pool hours update");
  await expect(page.locator("[data-campaign-step-panel='audience']")).toBeVisible();
  await page.locator("#notification-campaign-preview-button").click();
  await expect(page.locator("#notification-campaign-preview")).toContainText("2 eligible of 3 active stays");
  await expect(page.locator("#notification-campaign-preview")).toContainText("1 missing promotional consent");
  await page.locator("#notification-campaign-next").click();
  await expect(page.locator("[data-campaign-step-panel='delivery']")).toBeVisible();
  await page.locator("#notification-campaign-next").click();
  await expect(page.locator("#notification-review-audience")).toContainText("2 eligible of 3 active stays");
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("#notification-campaign-publish").click();
  await expect(page.locator("#notification-campaign-preview")).toContainText("2 queued in-app");
  await expect(page.locator("#notification-campaign-list")).toContainText("published");
  await expect(page.locator("#notification-campaign-list")).toContainText("2 queued");
});

test("notification campaign history: search and page server results", async ({ page }) => {
  const allCampaigns = Array.from({ length: 26 }, (_, index) => ({
    campaign_id: `campaign-${String(index + 1).padStart(2, "0")}`,
    name: `Campaign ${String(index + 1).padStart(2, "0")}`,
    title: `Verified update ${index + 1}`,
    body: `Campaign body ${index + 1}`,
    source_reference: `event-${index + 1}`,
    status: "published",
    revision: 1,
    queued_count: 0,
    suppressed_count: 0,
    engagement: { read: 0 },
  }));
  const requestedOffsets = [];
  await page.route("**/api/admin/properties/*/notification-campaigns**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "GET" && url.pathname.endsWith("/notification-campaigns")) {
      const query = (url.searchParams.get("q") || "").toLocaleLowerCase();
      const status = url.searchParams.get("status") || "all";
      const limit = Number(url.searchParams.get("limit") || 25);
      const offset = Number(url.searchParams.get("offset") || 0);
      requestedOffsets.push(offset);
      const filtered = allCampaigns.filter((campaign) => (status === "all" || (status === "expired" ? Number(campaign.engagement?.expired || 0) > 0 : campaign.status === status)) && `${campaign.name} ${campaign.title} ${campaign.body} ${campaign.source_reference}`.toLocaleLowerCase().includes(query));
      const status_counts = Object.fromEntries(["draft", "publishing", "published", "failed"].map((value) => [value, allCampaigns.filter((campaign) => campaign.status === value).length]));
      await route.fulfill({ json: { campaigns: filtered.slice(offset, offset + limit), total: filtered.length, limit, offset, status_counts, delivery_counts: { queued: 0, sent: 0, delivered: 0, read: 0, failed: 0, expired: 0 } } });
      return;
    }
    await route.continue();
  });

  await page.goto("/admin");
  await openCampaignPanel(page);
  await expect(page.locator("#notification-campaign-page-info")).toHaveText("Page 1 of 2");
  await expect(page.locator("#notification-campaign-list")).toContainText("Campaign 01");
  await page.locator("#notification-campaign-page-next").click();
  await expect(page.locator("#notification-campaign-page-info")).toHaveText("Page 2 of 2");
  await expect(page.locator("#notification-campaign-list")).toContainText("Campaign 26");
  await page.locator("#notification-campaign-page-previous").click();
  await expect(page.locator("#notification-campaign-page-info")).toHaveText("Page 1 of 2");

  await page.locator("#notification-campaign-search").fill("Campaign 26");
  await expect(page.locator("#notification-campaign-page-info")).toHaveText("Page 1 of 1");
  await expect(page.locator("#notification-campaign-list")).toContainText("Campaign 26");
  await expect(page.locator("#notification-campaign-list")).not.toContainText("Campaign 01");
  await expect.poll(() => requestedOffsets.at(-1)).toBe(0);
});

test("notification center uses server status counts, filters campaigns, and reflows across breakpoints", async ({ page }) => {
  const campaigns = [
    { campaign_id: "draft-1", name: "Lobby hours draft", title: "Lobby hours", body: "Draft copy", source_reference: "event-101", created_by: "A. Manager", status: "draft", revision: 2, updated_at: 1792300000, engagement: { queued: 0, delivered: 0, read: 0, failed: 0 } },
    { campaign_id: "published-1", name: "Spa opening", title: "Spa is open", body: "Visit the spa", source_reference: "ops-2026-77", created_by: "B. Manager", status: "published", revision: 3, updated_at: 1792300300, engagement: { queued: 3, delivered: 2, read: 1, failed: 0, expired: 2 } },
    { campaign_id: "failed-1", name: "Garden update", title: "Garden access", body: "Access is limited", source_reference: "ops-2026-79", created_by: "C. Manager", status: "failed", revision: 4, updated_at: 1792300600, engagement: { queued: 0, delivered: 0, read: 0, failed: 1 } },
  ];
  const requestedStatuses = [];
  await page.route("**/api/admin/properties/*/notification-campaigns**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "GET" && url.pathname.endsWith("/notification-campaigns")) {
      const status = url.searchParams.get("status") || "all";
      const query = (url.searchParams.get("q") || "").toLocaleLowerCase();
      const limit = Number(url.searchParams.get("limit") || 25);
      const offset = Number(url.searchParams.get("offset") || 0);
      requestedStatuses.push(status);
      const filtered = campaigns.filter((campaign) => (status === "all" || (status === "expired" ? Number(campaign.engagement?.expired || 0) > 0 : campaign.status === status)) && `${campaign.name} ${campaign.title} ${campaign.body} ${campaign.source_reference}`.toLocaleLowerCase().includes(query));
      const status_counts = { draft: 1, publishing: 0, published: 1, failed: 1 };
      const delivery_counts = { queued: 3, sent: 3, delivered: 2, read: 1, failed: 1, expired: 2 };
      await route.fulfill({ json: { campaigns: filtered.slice(offset, offset + limit), total: filtered.length, limit, offset, status_counts, delivery_counts } });
      return;
    }
    await route.continue();
  });

  await page.goto("/admin");
  await openCampaignPanel(page);
  await expect(page.locator("#notification-summary-all")).toHaveText("3");
  await expect(page.locator("#notification-summary-expired")).toHaveText("2");
  await expect(page.locator("#notification-campaign-list")).toContainText("Lobby hours draft");
  await expect(page.locator("#notification-campaign-list")).toContainText("Created by A. Manager");
  await page.locator('[data-campaign-status="failed"]').click();
  await expect(page.locator("#notification-campaign-filter-label")).toHaveText("Failed");
  await expect(page.locator("#notification-campaign-list")).toContainText("Garden update");
  await expect(page.locator("#notification-campaign-list")).not.toContainText("Lobby hours draft");
  expect(requestedStatuses).toContain("failed");
  await page.locator('[data-campaign-status="expired"]').click();
  await expect(page.locator("#notification-campaign-filter-label")).toHaveText("Campaigns with expired notices");
  await expect(page.locator("#notification-campaign-list")).toContainText("Spa opening");
  expect(requestedStatuses).toContain("expired");

  for (const viewport of [
    { width: 1440, height: 960, name: "desktop" },
    { width: 768, height: 1024, name: "tablet" },
    { width: 390, height: 844, name: "mobile" },
  ]) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    if (viewport.width <= 620) {
      const shell = page.locator(".platform-shell");
      if (await shell.evaluate((element) => element.classList.contains("mobile-nav-open"))) await page.locator("#sidebar-toggle").click();
      await expect.poll(() => page.locator("#platform-sidebar").evaluate((element) => element.getBoundingClientRect().right)).toBeLessThanOrEqual(0);
    }
    const panel = page.locator("#notification-campaigns");
    await expect(panel).toBeVisible();
    await expect.poll(() => panel.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    await page.locator(".platform-main").evaluate((element) => { element.scrollTop = 0; });
    await page.screenshot({ path: `test-results/notification-center/${viewport.name}.png` });
    if (viewport.name === "mobile") {
      await page.locator(".platform-main").evaluate((element) => { element.scrollTop = element.scrollHeight; });
      await page.screenshot({ path: "test-results/notification-center/mobile-queue.png" });
      await page.locator(".platform-main").evaluate((element) => { element.scrollTop = 0; });
    }
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator("#notification-campaign-new").click();
  await expect(page.locator("#notification-campaign-dialog")).toBeVisible();
  await expect(page.locator("#notification-campaign-publish")).toBeHidden();
  await page.locator("#notification-campaign-name").fill("New synthetic draft");
  await page.locator("#notification-campaign-title").fill("A guest update");
  await page.locator("#notification-campaign-body").fill("This is a preview-only synthetic message.");
  await page.locator("#notification-campaign-source").fill("synthetic-event-1");
  await page.locator("#notification-campaign-next").click();
  await expect(page.locator("[data-campaign-step-panel='audience']")).toBeVisible();
  await expect(page.locator("#notification-campaign-preview-button")).toBeDisabled();
  await page.locator("#notification-campaign-dialog").screenshot({ path: "test-results/notification-center/mobile-draft-drawer.png" });
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("#notification-campaign-close").click();
});
