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
