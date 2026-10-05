import { expect, test } from "@playwright/test";

const password = "PlaywrightOnly-Admin-123!";

async function login(api) {
  const response = await api.post("/api/admin/auth/login", {
    data: { username: "admin", password, remember_me: false },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()).user.csrf_token;
}

test("property-scoped pages and settings stay safe when no property exists", async ({ page }) => {
  const badRequests = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/admin/properties//")) badRequests.push(request.url());
  });

  await login(page.request);
  await page.route("**/api/admin/properties", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ properties: [] }),
  }));
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
  await expect(page.locator("#property-onboarding")).toBeVisible();
  await expect(page.locator("#onboarding-create-property")).toBeVisible();
  await expect(page.locator(".sidebar-health strong")).toHaveText("System status unavailable");
  const blocked = await page.evaluate(async () => {
    try {
      await jsonFetch("/api/admin/properties//service-catalog");
      return false;
    } catch (error) {
      return /Select a property/.test(error.message);
    }
  });
  expect(blocked).toBe(true);

  for (const navId of ["dashboard", "guest-requests", "guest-sessions", "system-health", "alerts", "restaurants", "service-catalog"]) {
    await page.locator(`[data-nav-id="${navId}"]`).evaluate((button) => button.click());
    await expect(page.locator("#property-onboarding")).toBeVisible();
    if (navId === "system-health") {
      await expect(page.locator("#system-health-summary strong")).toHaveText("System health unavailable");
    }
  }

  await page.locator("#refresh-dashboard").evaluate((button) => button.click());
  await page.route("**/api/admin/system/email", (route) => route.fulfill({
    status: 500,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Email settings unavailable" }),
  }));
  await page.locator('[data-nav-id="settings"]').evaluate((button) => button.click());
  await expect(page.locator("#system-settings")).toHaveClass(/active/);
  await expect(page.locator("#app-settings-property-note")).toContainText("Create or select a property");
  await expect(page.locator("#setting-language")).toBeDisabled();
  await expect(page.locator("#smtp-status")).toBeVisible();
  await expect(page.locator("#toast")).toContainText("Email settings unavailable");
  expect(badRequests).toEqual([]);
});

test("health API failures and incomplete checks render unavailable", async ({ page }) => {
  const csrf = await login(page.request);
  const propertyId = `health-context-${Date.now().toString(36)}`;
  const created = await page.request.put(`/api/admin/properties/${propertyId}`, {
    headers: { "X-CSRF-Token": csrf },
    data: { property_id: propertyId, hotel_name: "Health Context Test", timezone: "UTC" },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  const property = await created.json();
  try {
    await page.route("**/api/admin/properties", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ properties: [property] }),
    }));

    await page.goto("/admin");
    await page.locator('body[data-admin-ready="true"]').waitFor();
    await expect(page.locator("#property-switcher")).toHaveValue(propertyId);
    const unauthorizedScope = await page.evaluate(async (id) => {
      try {
        await jsonFetch(`/api/admin/properties/${encodeURIComponent(id)}/service-catalog`);
        return false;
      } catch (error) {
        return /Select a valid property/.test(error.message);
      }
    }, "unknown-property-id");
    expect(unauthorizedScope).toBe(true);
    await page.route("**/operations/dashboard*", (route) => route.abort("failed"));
    await page.locator('[data-nav-id="system-health"]').evaluate((button) => button.click());
    await expect(page.locator("#system-health-summary strong")).toHaveText("System health unavailable");
    await expect(page.locator(".sidebar-health strong")).not.toHaveText("System operational");

    await page.unroute("**/operations/dashboard*");
    await page.route("**/operations/dashboard*", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ health: { state: "healthy", components: [] } }),
    }));
    await page.locator("#refresh-health").click();
    await expect(page.locator("#system-health-summary strong")).toHaveText("System health unavailable");
    await expect(page.locator(".sidebar-health strong")).not.toHaveText("System operational");

    await page.unroute("**/operations/dashboard*");
    await page.addInitScript(() => {
      const nativeSetTimeout = window.setTimeout.bind(window);
      window.setTimeout = (callback, delay, ...args) => nativeSetTimeout(callback, delay === 15000 ? 20 : delay, ...args);
      const nativeFetch = window.fetch.bind(window);
      window.fetch = (input, options = {}) => {
        const url = typeof input === "string" ? input : input.url;
        if (!url.includes("/operations/dashboard")) return nativeFetch(input, options);
        return new Promise((_, reject) => {
          const abort = () => reject(new DOMException("Health request timed out", "AbortError"));
          if (options.signal?.aborted) abort();
          else options.signal?.addEventListener("abort", abort, { once: true });
        });
      };
    });
    await page.reload();
    await page.locator('body[data-admin-ready="true"]').waitFor();
    await expect(page.locator("#property-switcher")).toHaveValue(propertyId);
    await expect(page.locator("#system-health-summary strong")).toHaveText("System health unavailable");
    await expect(page.locator(".sidebar-health strong")).not.toHaveText("System operational");
  } finally {
    const removed = await page.request.delete(`/api/admin/properties/${propertyId}`, {
      headers: { "X-CSRF-Token": csrf },
    });
    expect(removed.ok(), await removed.text()).toBeTruthy();
  }
});
