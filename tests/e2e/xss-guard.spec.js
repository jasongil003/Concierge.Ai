import { expect, test } from "@playwright/test";
import { ensureTestProperty } from "./support.js";

const csrfByRequest = new WeakMap();

async function loginAdmin(api) {
  const response = await api.post("/api/admin/auth/login", {
    data: { username: "admin", password: "ChangeMe123!", remember_me: false },
  });
  expect(response.ok()).toBeTruthy();
  const csrf = (await response.json()).user.csrf_token;
  csrfByRequest.set(api, csrf);
  await ensureTestProperty(api, csrf);
  return csrf;
}

test.beforeEach(async ({ page, request }) => {
  await loginAdmin(request);
  await loginAdmin(page.request);
});

test("guest-supplied service request text is rendered as inert text (stored XSS guard)", async ({ page, request }) => {
  const properties = (await (await request.get("/api/admin/properties")).json()).properties;
  expect(properties.length).toBeGreaterThan(0);
  const propertyId = properties[0].property_id;

  const started = await request.post("/api/session/start", { data: { client_id: "xss-guard-e2e" } });
  expect(started.ok()).toBeTruthy();
  const sessionId = (await started.json()).session_id;

  const catalog = await (await request.get(`/api/admin/properties/${propertyId}/service-catalog`)).json();
  const service = catalog.services?.[0];
  expect(service, "catalog must contain at least one service").toBeTruthy();

  const payload = '<img src=x onerror="window.__xss_proof=1"> <script>window.__xss_proof=2</script>';
  const created = await request.post("/api/guest/service-requests", {
    data: {
      session_id: sessionId,
      service_id: service.service_id,
      description: payload,
      room: '<svg onload=window.__xss_proof=3>',
      confirmed: true,
    },
  });
  expect(created.ok(), `service request creation failed: ${await created.text()}`).toBeTruthy();

  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
  if ((page.viewportSize()?.width || 1440) <= 620) {
    await page.locator("#sidebar-toggle").click();
    await expect(page.locator(".platform-shell")).toHaveClass(/mobile-nav-open/);
  }
  const button = page.locator(".nav-item").filter({ hasText: "Guest Requests" }).first();
  await button.evaluate((element) => {
    const group = element.closest("details");
    if (group) group.open = true;
  });
  await button.click();
  await expect(page.locator("#service-request-list")).toBeVisible();

  const row = page.locator("#service-request-list .compact-row").filter({ hasText: payload }).first();
  await expect(row).toContainText(payload);

  await expect.poll(async () => page.evaluate(() => window.__xss_proof)).toBeUndefined();
  expect(await page.locator("#service-request-list script").count()).toBe(0);
  expect(await page.locator("#service-request-list img[onerror]").count()).toBe(0);
});
