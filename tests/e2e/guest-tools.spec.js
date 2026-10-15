import { expect, test } from "@playwright/test";
import { prepareGuestFixture } from "./support.js";

async function setIntelligentUi(request, enabled) {
  const login = await request.post("/api/admin/auth/login", {
    data: { username: "admin", password: "PlaywrightOnly-Admin-123!", remember_me: false },
  });
  expect(login.ok()).toBeTruthy();
  const csrf = (await login.json()).user.csrf_token;
  const propertiesResponse = await request.get("/api/admin/properties");
  expect(propertiesResponse.ok()).toBeTruthy();
  const propertyId = (await propertiesResponse.json()).properties[0]?.property_id;
  expect(propertyId).toBeTruthy();
  const propertyResponse = await request.get(`/api/admin/properties/${encodeURIComponent(propertyId)}`);
  expect(propertyResponse.ok()).toBeTruthy();
  const property = await propertyResponse.json();
  property.app_settings = {
    ...(property.app_settings || {}),
    guest_experience: {
      ...(property.app_settings?.guest_experience || {}),
      intelligent_ui: { enabled },
    },
  };
  const saved = await request.put(`/api/admin/properties/${encodeURIComponent(propertyId)}`, {
    headers: { "X-CSRF-Token": csrf },
    data: property,
  });
  expect(saved.ok(), await saved.text()).toBeTruthy();
}

test.beforeEach(async ({ request }) => {
  await prepareGuestFixture(request);
  await setIntelligentUi(request, true);
});

test.afterEach(async ({ request }) => {
  await setIntelligentUi(request, false);
});

test("guest inbox renders safely, acknowledges receipt and explicit read, and saves preferences and privacy choices", async ({ page }) => {
  const ackActions = [];
  const preferenceUpdates = [];
  const privacyUpdates = [];
  const hostileTitle = '<img src=x onerror="window.__inboxXss=1"> Room update';
  const hostileBody = '<script>window.__inboxXss=2</script>The pool closes at 8 PM.';
  await page.addInitScript(() => {
    window.__gpsCalls = 0;
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: {
        getCurrentPosition: () => { window.__gpsCalls += 1; },
        watchPosition: () => { window.__gpsCalls += 1; return 1; },
      },
    });
  });
  await page.route("**/api/guest/intro**", (route) => route.fulfill({
    json: { mode: "none", first_visit_only: true, allow_skip: true },
  }));
  await page.route("**/api/guest/notifications**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "GET") {
      await route.fulfill({
        json: {
          notifications: [{
            notification_id: "notice-1", title: hostileTitle, body: hostileBody,
            status: "sent", created_at: 100,
          }],
          preferences: { operational: true, assistance: true, experience: false, promotional: false },
          can_manage: true,
        },
      });
      return;
    }
    const body = request.postDataJSON();
    if (url.pathname.endsWith("/preferences")) {
      preferenceUpdates.push(body);
      await route.fulfill({ json: { preferences: { ...body } } });
      return;
    }
    if (url.pathname.endsWith("/ack")) {
      ackActions.push(body.action);
      await route.fulfill({ json: { notification_id: "notice-1", status: body.action } });
      return;
    }
    await route.fulfill({ status: 404, json: { detail: "Not found" } });
  });
  await page.route("**/api/guest/privacy", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: { consents: {
          location_services: false,
          proactive_notifications: false,
          promotional_messages: false,
          external_data_processing: false,
        } },
      });
      return;
    }
    privacyUpdates.push(route.request().postDataJSON());
    await route.fulfill({ json: { consents: privacyUpdates.at(-1).consents } });
  });

  await page.goto("/");
  await expect(page.locator("#app-shell")).toBeVisible();
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("concierge-v2-session-id"))).toBeTruthy();
  await page.getByRole("button", { name: "Inbox & privacy" }).click();
  const dialog = page.getByRole("dialog", { name: "Inbox & privacy" });
  await expect(dialog).toBeVisible();
  const inboxItem = dialog.locator(".guest-inbox-item");
  await expect(inboxItem).toContainText(hostileTitle);
  await expect(inboxItem).toContainText(hostileBody);
  await expect(inboxItem.locator("img, script")).toHaveCount(0);
  await expect(inboxItem.locator("h4")).toHaveText(hostileTitle);
  await expect(inboxItem.locator(".guest-inbox-status")).toHaveText("Delivered");
  await expect.poll(() => ackActions).toEqual(["delivered"]);

  await inboxItem.getByRole("button", { name: "Mark as read" }).click();
  await expect(inboxItem.locator(".guest-inbox-status")).toHaveText("Read");
  await expect.poll(() => ackActions).toEqual(["delivered", "read"]);

  const promotionalPreference = dialog.locator('[data-notification-category="promotional"]');
  await expect(promotionalPreference).not.toBeChecked();

  for (const category of [
    "location_services", "proactive_notifications", "promotional_messages", "external_data_processing",
  ]) {
    await expect(dialog.locator(`[data-consent-category="${category}"]`)).not.toBeChecked();
  }
  await expect(dialog).toContainText("This screen does not request device GPS.");
  await dialog.locator('[data-consent-category="proactive_notifications"]').check();
  await dialog.locator('[data-consent-category="promotional_messages"]').check();
  await dialog.getByRole("button", { name: "Save privacy choices" }).click();
  await expect.poll(() => privacyUpdates.length).toBe(1);
  expect(privacyUpdates[0]).toMatchObject({
    consents: {
      location_services: false,
      proactive_notifications: true,
      promotional_messages: true,
      external_data_processing: false,
    },
  });
  expect(privacyUpdates[0].session_id).toBeTruthy();
  await promotionalPreference.check();
  await expect.poll(() => preferenceUpdates).toEqual([{ category: "promotional", enabled: true }]);
  await expect.poll(() => page.evaluate(() => window.__gpsCalls)).toBe(0);
  await expect(page.evaluate(() => window.__inboxXss)).resolves.toBeUndefined();
});
