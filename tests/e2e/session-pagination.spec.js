import { expect, test } from "@playwright/test";
import { ensureTestProperty } from "./support.js";

const csrfByRequest = new WeakMap();

test.beforeEach(async ({ page }) => {
  const login = await page.request.post("/api/admin/auth/login", {
    data: { username: "admin", password: "PlaywrightOnly-Admin-123!", remember_me: false },
  });
  expect(login.ok()).toBeTruthy();
  csrfByRequest.set(page.request, (await login.json()).user.csrf_token);
});

async function openPanel(page, label) {
  await page.locator('body[data-admin-ready="true"]').waitFor();
  if (await page.evaluate(() => window.matchMedia("(max-width: 620px)").matches)) {
    await page.locator("#sidebar-toggle").click();
  }
  const button = page.locator(".nav-item").filter({ hasText: label }).first();
  await button.evaluate((element) => {
    const group = element.closest("details");
    if (group) group.open = true;
  });
  await button.click();
}

test("guest stays search on the server and paginate on desktop and mobile", async ({ page }) => {
  const csrf = csrfByRequest.get(page.request);
  const propertyId = await ensureTestProperty(page.request, csrf);
  const headers = { "X-CSRF-Token": csrf };
  const marker = Date.now().toString(16).slice(-4).toUpperCase();
  const roomPrefix = `Paging ${marker}`;
  for (let index = 1; index <= 27; index += 1) {
    const mac = `02:00:00:${marker.slice(0, 2)}:${marker.slice(2, 4)}:${index.toString(16).padStart(2, "0")}`;
    const response = await page.request.post(`/api/admin/properties/${encodeURIComponent(propertyId)}/sessions/reconnect`, {
      headers,
      data: { raw_mac: mac, room: `${roomPrefix} ${index}` },
    });
    expect(response.ok(), await response.text()).toBeTruthy();
  }

  await page.goto("/admin");
  await page.locator("#property-switcher").selectOption(propertyId);
  await openPanel(page, "Guest Sessions");
  await page.locator("#session-record-filter").selectOption("active-stays");
  const firstPageResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname.endsWith("/sessions") && url.searchParams.get("q") === roomPrefix
      && url.searchParams.get("filter") === "active-stays" && url.searchParams.get("stay_offset") === "0";
  });
  await page.locator("#session-record-search").fill(roomPrefix);
  const firstPage = await firstPageResponse;
  expect(firstPage.ok()).toBeTruthy();
  const firstData = await firstPage.json();
  expect(firstData.stays).toHaveLength(25);
  expect(firstData.pages.stays).toMatchObject({ total: 27, limit: 25, offset: 0 });
  await expect(page.locator("#session-list")).toContainText("Showing 1–25 of 27");

  const nextPageResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname.endsWith("/sessions") && url.searchParams.get("stay_offset") === "25";
  });
  await page.getByRole("button", { name: "Next page" }).click();
  const nextPage = await nextPageResponse;
  expect(nextPage.ok()).toBeTruthy();
  const nextData = await nextPage.json();
  expect(nextData.stays).toHaveLength(2);
  expect(nextData.pages.stays).toMatchObject({ total: 27, limit: 25, offset: 25 });
  await expect(page.locator("#session-list")).toContainText("Showing 26–27 of 27");
  await expect(page.locator("#session-list .session-record-group-list .session-record-card")).toHaveCount(2);
});

test("hotel knowledge entries use bounded pages on desktop and mobile", async ({ page }) => {
  const csrf = csrfByRequest.get(page.request);
  const marker = Date.now().toString(36);
  const propertyId = `knowledge-page-${marker}`;
  const headers = { "X-CSRF-Token": csrf };
  const created = await page.request.put(`/api/admin/properties/${encodeURIComponent(propertyId)}`, {
    headers,
    data: { property_id: propertyId, hotel_name: `Knowledge paging ${marker}`, timezone: "Asia/Manila" },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  for (let index = 1; index <= 27; index += 1) {
    const response = await page.request.put(`/api/admin/properties/${encodeURIComponent(propertyId)}/knowledge`, {
      headers,
      data: { kind: "entry", title: `Paged knowledge ${marker} ${index}`, body: `Approved test fact ${index}`, enabled: false },
    });
    expect(response.ok(), await response.text()).toBeTruthy();
  }

  await page.goto("/admin");
  await page.locator("#property-switcher").selectOption(propertyId);
  await openPanel(page, "Knowledge");
  await expect(page.locator("#knowledge-list .compact-row")).toHaveCount(25);
  await expect(page.locator("#knowledge-entry-pagination")).toContainText("Showing 1–25 of 27");
  await page.locator("#knowledge-entry-pagination").getByRole("button", { name: "Next page" }).click();
  await expect(page.locator("#knowledge-list .compact-row")).toHaveCount(2);
  await expect(page.locator("#knowledge-entry-pagination")).toContainText("Showing 26–27 of 27");
});
