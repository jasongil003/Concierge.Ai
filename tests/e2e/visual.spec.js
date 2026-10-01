import { expect, test } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { ensureTestProperty } from "./support.js";

async function loginAdmin(page) {
  const response = await page.request.post("/api/admin/auth/login", {
    data: { username: "admin", password: "PlaywrightOnly-Admin-123!", remember_me: false },
  });
  expect(response.ok()).toBeTruthy();
  const csrf = (await response.json()).user.csrf_token;
  await ensureTestProperty(page.request, csrf);
  return csrf;
}

test.beforeEach(async ({ page }) => {
  const csrf = await loginAdmin(page);
  const existing = await (await page.request.get("/api/admin/properties")).json();
  for (const property of existing.properties || []) {
    const removed = await page.request.delete(`/api/admin/properties/${property.property_id}`, {
      headers: { "X-CSRF-Token": csrf },
    });
    expect(removed.ok()).toBeTruthy();
  }
  // Hospitality tables are property-scoped and intentionally outlive property profiles.
  // Use a fresh ID so prior E2E data cannot appear in a visual snapshot.
  const propertyId = `visual-${randomUUID()}`;
  const created = await page.request.put(`/api/admin/properties/${propertyId}`, {
    headers: { "X-CSRF-Token": csrf },
    data: { property_id: propertyId, hotel_name: "E2E Property", timezone: "Asia/Manila" },
  });
  expect(created.ok()).toBeTruthy();
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "light" });
  await page.addInitScript(() => {
    localStorage.setItem("concierge-intro-seen", "1");
    localStorage.removeItem("concierge-draft");
    localStorage.removeItem("concierge-accessibility");
  });
});

test("guest home visual baseline", async ({ page }) => {
  await page.route("**/api/hotel", async (route) => {
    const response = await route.fetch();
    const profile = await response.json();
    profile.design = {
      ...(profile.design || {}),
      welcome: {
        ...(profile.design?.welcome || {}),
        greeting: "Welcome back",
        headline: "How can I help with your stay today?",
        description: "Your personal concierge is here to make your stay more comfortable.",
      },
      theme: { ...(profile.design?.theme || {}), backgroundImageUrl: "/test-home-hero.svg" },
      suggestions: [
        { label: "Dining", prompt: "Show property dining options", enabled: true, order: 0 },
        { label: "Room Service", prompt: "Show available room service", enabled: true, order: 1 },
        { label: "Housekeeping", prompt: "Request housekeeping service", enabled: true, order: 2 },
        { label: "Transportation", prompt: "Show configured transport options", enabled: true, order: 3 },
      ],
    };
    await route.fulfill({ response, json: profile });
  });
  await page.route("**/api/guest/home", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      greeting: "Welcome back", stay: { status: "checked_in" }, primary_card: null,
      cards: [
        { type: "restaurant", title: "Property dining", subtitle: "Seasonal cuisine", description: "A dining recommendation from this property's published content.", restaurant_id: "visual-dining", reservation_available: true },
        { type: "recommendation", title: "Featured property experience", subtitle: "Wellness", description: "An experience from this property's published recommendations.", recommendation_id: "visual-wellness", map_url: "https://maps.example/visual-experience" },
      ],
      active_requests: [],
      quick_actions: [
        { label: "My Stay", view: "stay" },
        { label: "Requests", view: "requests" },
        { label: "Explore", view: "explore" },
      ],
      suggested_prompts: [],
      inventory: {
        restaurants: [{ restaurant_id: "visual-dining", name: "Property dining", cuisine: "Seasonal cuisine", images: ["/test-home-dining.svg"], reservation_available: true, external_reservation_url: "https://reservations.example/property-dining" }],
        facilities: [], events: [], promotions: [],
        recommendations: [
          { recommendation_id: "visual-dining", name: "Property dining", category: "Dining", images: ["/test-home-dining.svg"], map_url: "https://maps.example/visual-dining" },
          { recommendation_id: "visual-wellness", name: "Featured property experience", category: "Wellness", images: ["/test-home-wellness.svg"], map_url: "https://maps.example/visual-experience" },
        ],
        menu_items: [],
      },
    }),
  }));
  const syntheticArt = {
    "/test-home-hero.svg": `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 500"><defs><linearGradient id="sky" x2="0" y2="1"><stop stop-color="#e4b68a"/><stop offset=".58" stop-color="#eed7ba"/><stop offset="1" stop-color="#8ca3a1"/></linearGradient><linearGradient id="room" x2="0" y2="1"><stop stop-color="#eedbc1"/><stop offset="1" stop-color="#9b7957"/></linearGradient></defs><rect width="1200" height="500" fill="url(#room)"/><path d="M480 0h720v500H480z" fill="url(#sky)"/><path d="M480 330q150-68 280 0t440 0v170H480z" fill="#647e7b"/><path d="M540 0v500M1110 0v500" stroke="#fff0d9" stroke-width="26"/><path d="M515 30h620M515 465h620" stroke="#fff0d9" stroke-width="16"/><path d="M410 0h115v400h-115zM470 0q0 210 90 230" fill="#e7cfb1"/><path d="M740 365h250v26H740zM780 391v77m170-77v77" stroke="#6d5140" stroke-width="16" stroke-linecap="round"/><ellipse cx="865" cy="364" rx="145" ry="20" fill="#b89161"/><path d="M1040 323q20-145 0-190m0 92q-64-43-79-91m80 65q64-47 78-93m-78 42q-4-67 15-105" fill="none" stroke="#57644a" stroke-width="10" stroke-linecap="round"/><path d="M985 500v-97h110v97" fill="#916e4e"/></svg>`,
    "/test-home-dining.svg": `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 420"><defs><linearGradient id="d" x2="0" y2="1"><stop stop-color="#d89a67"/><stop offset=".45" stop-color="#553d30"/><stop offset="1" stop-color="#201a17"/></linearGradient></defs><rect width="800" height="420" fill="url(#d)"/><path d="M45 0h240v250H45z" fill="#e9b782"/><path d="M62 10h206v230H62z" fill="#687c7a"/><path d="M63 155q70-75 205-5v90H63z" fill="#394e4b"/><path d="M0 302q400-60 800 0v118H0z" fill="#241a15"/><ellipse cx="445" cy="296" rx="235" ry="45" fill="#9a6841"/><path d="M210 296h470l-68 112H265z" fill="#69442f"/><path d="M408 220v50m-12-50h24m-12 50v18" stroke="#f5d59f" stroke-width="8"/><circle cx="410" cy="214" r="10" fill="#f5d59f"/><path d="M572 262v-38m0 0q-18-18-22 0m22 0q18-18 22 0" fill="none" stroke="#e7d6bc" stroke-width="7"/><path d="M322 270v-42m0 0q-18-18-22 0m22 0q18-18 22 0" fill="none" stroke="#e7d6bc" stroke-width="7"/></svg>`,
    "/test-home-wellness.svg": `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 420"><defs><linearGradient id="p" x2="0" y2="1"><stop stop-color="#cbb18d"/><stop offset=".42" stop-color="#806d58"/><stop offset="1" stop-color="#1d3434"/></linearGradient><linearGradient id="w" x2="1" y2="1"><stop stop-color="#91aaa5"/><stop offset="1" stop-color="#284a4c"/></linearGradient></defs><rect width="800" height="420" fill="url(#p)"/><path d="M0 248q190-62 395 2t405-4v174H0z" fill="url(#w)"/><path d="M0 278q190-53 398 4t402-5" fill="none" stroke="#d4c3a7" stroke-width="8" opacity=".75"/><path d="M60 0h20v276H60zm10 66q-65-39-52-79m53 115q65-48 72-107m-72 173q-48-26-58-72" fill="none" stroke="#4b5941" stroke-width="10"/><path d="M510 92q80-74 170 0v13H510z" fill="#e6d4b8"/><rect x="523" y="105" width="144" height="12" rx="6" fill="#b89a73"/><path d="M565 254q50-65 104 0v30H565z" fill="#f3e9d8"/><path d="M550 276h150v40H550z" rx="18" fill="#e8dac4"/><path d="M549 317h152" stroke="#fff7e8" stroke-width="12" stroke-linecap="round"/></svg>`,
  };
  await page.route("**/test-home-*.svg", (route) => route.fulfill({
    status: 200,
    contentType: "image/svg+xml",
    body: syntheticArt[new URL(route.request().url()).pathname],
  }));
  const homeLoaded = page.waitForResponse((response) =>
    response.url().includes("/api/guest/home") && response.status() === 200,
  );
  await page.goto("/");
  await homeLoaded;
  if ((page.viewportSize()?.width || 0) > 700) await page.setViewportSize({ width: 1280, height: 1254 });
  await expect(page.locator(".experience-hero")).toHaveClass(/experience-hero-has-image/);
  await expect(page.locator(".experience-quick_actions .experience-action-card")).toHaveCount(4);
  await expect(page.locator(".experience-card-grid > .guest-content-card")).toHaveCount(2);
  await expect(page.locator("#legacy-home-content")).toBeHidden();

  await expect(page).toHaveScreenshot("guest-home.png", {
    animations: "disabled",
    caret: "hide",
    fullPage: true,
    maxDiffPixelRatio: 0.01,
  });
});

test("admin design panel visual baseline", async ({ page }) => {
  await loginAdmin(page);
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
  if ((page.viewportSize()?.width || 1200) <= 620) {
    await page.locator("#sidebar-toggle").click();
  }
  const designButton = page.locator(".nav-item").filter({ hasText: "Design" }).first();
  await designButton.evaluate((element) => {
    const group = element.closest("details");
    if (group) group.open = true;
  });
  await designButton.click();
  await expect(page.locator("#appearance")).toBeVisible();

  await expect(page.locator("#appearance")).toHaveScreenshot("admin-design.png", {
    animations: "disabled",
    caret: "hide",
    maxDiffPixelRatio: 0.01,
  });
});
