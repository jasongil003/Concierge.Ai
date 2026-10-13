import { expect } from "@playwright/test";

export async function ensureTestProperty(api, csrf) {
  const response = await api.get("/api/admin/properties");
  expect(response.ok()).toBeTruthy();
  const properties = (await response.json()).properties || [];
  if (properties.length) return properties[0].property_id;

  const created = await api.put("/api/admin/properties/e2e-property", {
    headers: { "X-CSRF-Token": csrf },
    data: { property_id: "e2e-property", hotel_name: "E2E Property", timezone: "Asia/Manila" },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  return "e2e-property";
}

// Standalone guest regressions must seed their own isolated Playwright app;
// relying on a preceding admin test masks missing fixtures and causes CI races.
export async function prepareGuestFixture(api) {
  const login = await api.post("/api/admin/auth/login", {
    data: { username: "admin", password: "PlaywrightOnly-Admin-123!", remember_me: false },
  });
  expect(login.ok()).toBeTruthy();
  const csrf = (await login.json()).user.csrf_token;
  const propertyId = await ensureTestProperty(api, csrf);
  const response = await api.get("/api/admin/properties");
  for (const property of (await response.json()).properties || []) {
    if (property.property_id === propertyId) continue;
    const removed = await api.delete(`/api/admin/properties/${property.property_id}`, {
      headers: { "X-CSRF-Token": csrf },
    });
    expect(removed.ok()).toBeTruthy();
  }
}
