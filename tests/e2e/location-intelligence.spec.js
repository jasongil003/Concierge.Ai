import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";

const outputDirectory = "test-results/location-intelligence";
mkdirSync(outputDirectory, { recursive: true });

async function loginAdmin(api) {
  const response = await api.post("/api/admin/auth/login", {
    data: { username: "admin", password: "PlaywrightOnly-Admin-123!", remember_me: false },
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).user.csrf_token;
}

async function openLocation(page) {
  await page.locator('body[data-admin-ready="true"]').waitFor();
  if ((page.viewportSize()?.width || 1440) <= 620) {
    await page.locator("#sidebar-toggle").click();
  }
  const nav = page.locator(".nav-item").filter({ hasText: "Location" }).first();
  await nav.evaluate((element) => { if (element.closest("details")) element.closest("details").open = true; });
  await nav.click();
  await expect(page.locator("#location")).toBeVisible();
}

test("location intelligence drawer, permissions-aware dashboard, and responsive views", async ({ page }, testInfo) => {
  // Use the page context's request client so the login cookie is shared with
  // the browser session used by the UI below.
  const api = page.request;
  const csrf = await loginAdmin(api);
  const propertyId = `e2e-location-${Date.now().toString(36)}`;
  const created = await api.put(`/api/admin/properties/${propertyId}`, {
    headers: { "X-CSRF-Token": csrf },
    data: { property_id: propertyId, hotel_name: "Location Intelligence QA", timezone: "Asia/Manila" },
  });
  expect(created.ok(), await created.text()).toBeTruthy();

  try {
    await page.goto("/admin");
    await page.locator("#property-switcher").selectOption(propertyId);
    await openLocation(page);
    const pageBounds = await page.evaluate(() => ({
      windowScrollY: window.scrollY,
      mainTop: document.querySelector(".platform-main")?.getBoundingClientRect().top,
      locationTop: document.querySelector("#location")?.getBoundingClientRect().top,
      locationInsideMain: document.querySelector("#location")?.parentElement?.classList.contains("platform-main"),
    }));
    expect(pageBounds.windowScrollY).toBe(0);
    expect(pageBounds.locationInsideMain).toBe(true);
    expect(pageBounds.locationTop - pageBounds.mainTop).toBeLessThan(100);
    await expect(page.getByRole("heading", { name: "Property Location & Navigation" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Floor plans and guest routes" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Guest-facing directory" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Observed activity by zone" })).toBeVisible();
    await expect(page.locator("#location-map-publication")).toContainText("No map revision is published");

    await page.getByRole("button", { name: "Add location" }).click();
    await expect(page.locator("#location-editor-drawer")).toBeVisible();
    await page.locator("#location-name").fill("QA Main Entrance");
    await page.locator("#location-type").selectOption("entrance");
    await page.locator("#location-description").fill("North entrance near the covered drop-off.");
    await page.locator("#location-latitude").fill("14.5547");
    await page.locator("#location-longitude").fill("121.0244");
    expect(await page.locator("#location-name").inputValue()).toBe("QA Main Entrance");
    expect(await page.locator("#location-description").inputValue()).toBe("North entrance near the covered drop-off.");
    const auditDirectory = process.env.PLAYWRIGHT_AUDIT_DIR;
    if (auditDirectory) {
      const afterDirectory = join(auditDirectory, "screenshots", "after");
      mkdirSync(afterDirectory, { recursive: true });
      const device = testInfo.project.name === "mobile-chrome" ? "mobile" : "desktop";
      await page.screenshot({ path: join(afterDirectory, `location-editor-form-${device}.png`) });
    }
    const propertyWrites = [];
    page.on("request", (request) => {
      if (request.method() === "PUT" && request.url().endsWith(`/api/admin/properties/${propertyId}`)) {
        propertyWrites.push(request.postDataJSON());
      }
    });
    await page.getByRole("button", { name: "Save location" }).click();
    await expect(page.locator("#location-editor-drawer")).toBeHidden();
    expect(propertyWrites.at(-1)?.app_settings?.locations).toEqual(expect.arrayContaining([
      expect.objectContaining({ name: "QA Main Entrance", description: "North entrance near the covered drop-off." }),
    ]));
    await expect(page.locator("#managed-location-list")).toContainText("QA Main Entrance");
    const savedProperty = await api.get(`/api/admin/properties/${propertyId}`).then((response) => response.json());
    expect(savedProperty.app_settings.locations).toEqual(expect.arrayContaining([
      expect.objectContaining({ name: "QA Main Entrance", latitude: 14.5547, longitude: 121.0244, guest_visible: true }),
    ]));

    const mapData = await api.get(`/api/admin/properties/${propertyId}/zones`).then((response) => response.json());
    expect(mapData.map_validation).toMatchObject({ status: "review", building_count: 0, floor_count: 0 });
    expect(mapData.map_validation.issues.map((issue) => issue.code)).toContain("building_missing");
    expect(mapData.location_collection_enabled).toBe(false);
    await expect(page.locator("#toast")).not.toHaveClass(/show/);
    await expect.poll(() => page.locator("#toast").evaluate((toast) => getComputedStyle(toast).opacity)).toBe("0");

    const width = page.viewportSize()?.width || 1440;
    if (width > 700) {
      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.screenshot({ path: `${outputDirectory}/desktop.png` });
      await page.setViewportSize({ width: 768, height: 1024 });
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
      await page.screenshot({ path: `${outputDirectory}/tablet.png` });
    } else {
      await page.setViewportSize({ width: 390, height: 844 });
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
      await page.screenshot({ path: `${outputDirectory}/mobile.png` });
    }

    await page.locator('[data-location-panel="zones"]').first().click();
    await expect(page.locator("#zones")).toBeVisible();
    await expect(page.locator("#floor-map-canvas")).toBeVisible();
    expect(testInfo.project.name).toMatch(/chromium|mobile-chrome/);
  } finally {
    const removed = await api.delete(`/api/admin/properties/${propertyId}`, { headers: { "X-CSRF-Token": csrf } });
    expect(removed.ok(), await removed.text()).toBeTruthy();
  }
});
