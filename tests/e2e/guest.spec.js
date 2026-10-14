import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join, resolve } from "node:path";

const csrfByRequest = new WeakMap();

async function guestNavigation(page) {
  const configured = page.locator(".experience-configured-navigation");
  await expect(configured).toBeVisible();
  return configured;
}

async function openHotelMenu(page) {
  const configuredMenu = page.locator(".experience-configured-header .experience-configured-menu");
  await expect(configuredMenu).toBeVisible();
  await configuredMenu.click();
}

async function loginAdmin(request) {
  if (csrfByRequest.has(request)) return csrfByRequest.get(request);
  const response = await request.post("/api/admin/auth/login", {
    data: { username: "admin", password: "PlaywrightOnly-Admin-123!", remember_me: false },
  });
  expect(response.ok()).toBeTruthy();
  const csrf = (await response.json()).user.csrf_token;
  csrfByRequest.set(request, csrf);
  const properties = await request.get("/api/admin/properties");
  expect(properties.ok()).toBeTruthy();
  if (!(await properties.json()).properties.length) {
    const created = await request.put("/api/admin/properties/e2e-property", {
      headers: { "X-CSRF-Token": csrf },
      data: { property_id: "e2e-property", hotel_name: "E2E Property", timezone: "Asia/Manila" },
    });
    expect(created.ok()).toBeTruthy();
  }
  return csrf;
}

test.beforeEach(async ({ page, request }) => {
  const csrf = await loginAdmin(request);
  // The preceding admin onboarding flow intentionally leaves its newly created
  // property behind. Keep guest smoke tests on one synthetic localhost property
  // so localhost does not have to guess which property a guest should see.
  const propertiesResponse = await request.get("/api/admin/properties");
  expect(propertiesResponse.ok()).toBeTruthy();
  const properties = (await propertiesResponse.json()).properties || [];
  let guestProperty = properties.find((property) => property.property_id === "e2e-property");
  if (!guestProperty) {
    const created = await request.put("/api/admin/properties/e2e-property", {
      headers: { "X-CSRF-Token": csrf },
      data: { property_id: "e2e-property", hotel_name: "E2E Property", timezone: "Asia/Manila" },
    });
    expect(created.ok(), await created.text()).toBeTruthy();
    guestProperty = { property_id: "e2e-property" };
  }
  for (const property of properties) {
    if (property.property_id === guestProperty.property_id) continue;
    const removed = await request.delete(`/api/admin/properties/${property.property_id}`, {
      headers: { "X-CSRF-Token": csrf },
    });
    expect(removed.ok(), await removed.text()).toBeTruthy();
  }
  // Guest workflow checks should not inherit branding-test intro settings.
  await page.route("**/api/guest/intro**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ mode: "none", first_visit_only: true, allow_skip: true }),
  }));
});

async function setAuthTypes(request, enabledIds) {
  const csrf = await loginAdmin(request);
  const propertyId = (await (await request.get("/api/admin/properties")).json()).properties[0].property_id;
  const prop = await (await request.get(`/api/admin/properties/${propertyId}`)).json();
  const labels = {
    complimentary: "Complimentary",
    local: "Local",
    radius: "RADIUS",
    pms: "PMS / Room Login",
    credit_card: "Credit Card",
    access_code: "Access Code",
    global_account: "Global Account",
    global_code: "Global Code",
    user_form: "User Form",
    social_network: "Social Network",
  };
  prop.antlabs_config = {
    ...(prop.antlabs_config || {}),
    authentication_enabled: true,
    authentication_types: Object.fromEntries(
      Object.entries(labels).map(([id, label]) => [id, { label, enabled: enabledIds.includes(id) }])
    ),
  };
  const response = await request.put(`/api/admin/properties/${propertyId}`, {
    headers: { "X-CSRF-Token": csrf },
    data: prop,
  });
  expect(response.ok()).toBeTruthy();
}

async function setAuthenticationEnabled(request, enabled) {
  const csrf = await loginAdmin(request);
  const propertyId = (await (await request.get("/api/admin/properties")).json()).properties[0].property_id;
  const prop = await (await request.get(`/api/admin/properties/${propertyId}`)).json();
  prop.antlabs_config = { ...(prop.antlabs_config || {}), authentication_enabled: enabled };
  const response = await request.put(`/api/admin/properties/${propertyId}`, {
    headers: { "X-CSRF-Token": csrf },
    data: prop,
  });
  expect(response.ok()).toBeTruthy();
}

async function ensureGuestData(request) {
  const csrf = await loginAdmin(request);
  const propertyId = (await (await request.get("/api/admin/properties")).json()).properties[0].property_id;
  let catalog = await (await request.get(`/api/admin/properties/${propertyId}/service-catalog`)).json();
  let department = catalog.departments.find((item) => item.name === "Housekeeping");
  if (!department) {
    department = await (await request.put(`/api/admin/properties/${propertyId}/departments`, {
      headers: { "X-CSRF-Token": csrf }, data: { data: { name: "Housekeeping", default_sla_minutes: 15 } },
    })).json();
  }
  if (!catalog.services.some((item) => item.name === "Towels")) {
    await request.put(`/api/admin/properties/${propertyId}/service-catalog`, {
      headers: { "X-CSRF-Token": csrf },
      data: { data: { name: "Towels", department_id: department.department_id, keywords: ["towel", "towels"], sla_minutes: 15 } },
    });
  }
  for (const service of [
    { name: "Extra Pillow", keywords: ["extra pillow", "pillow"] },
    { name: "Housekeeping Visit", keywords: ["housekeeping", "clean my room"] },
  ]) {
    if (!catalog.services.some((item) => item.name === service.name)) {
      const response = await request.put(`/api/admin/properties/${propertyId}/service-catalog`, {
        headers: { "X-CSRF-Token": csrf },
        data: { data: { ...service, department_id: department.department_id, sla_minutes: 15 } },
      });
      expect(response.ok(), await response.text()).toBeTruthy();
    }
  }
  const recommendations = await (await request.get(`/api/admin/properties/${propertyId}/recommendations`)).json();
  if (!recommendations.recommendations.some((item) => item.name === "Fixture Bistro")) {
    await request.put(`/api/admin/properties/${propertyId}/recommendations`, {
      headers: { "X-CSRF-Token": csrf },
      data: { data: { name: "Fixture Bistro", category: "Dining", address: "1 Example Road", map_url: "https://maps.example/fixture", description: "Synthetic test recommendation.", enabled: true } },
    });
  }
}

async function setIntelligentUi(request, enabled, { welcome = "", prompts = [], pool } = {}) {
  const csrf = await loginAdmin(request);
  const propertyId = "e2e-property";
  const propertyResponse = await request.get(`/api/admin/properties/${propertyId}`);
  expect(propertyResponse.ok()).toBeTruthy();
  const property = await propertyResponse.json();
  property.app_settings = {
    ...(property.app_settings || {}),
    guest_experience: {
      ...(property.app_settings?.guest_experience || {}),
      intelligent_ui: { enabled },
      welcome_message: welcome,
      suggested_prompts: prompts,
    },
  };
  if (pool) property.pool = pool;
  const saved = await request.put(`/api/admin/properties/${propertyId}`, {
    headers: { "X-CSRF-Token": csrf },
    data: property,
  });
  expect(saved.ok(), await saved.text()).toBeTruthy();
}

function streamEvents(payload, blocks, textDelta = null) {
  const conversationId = payload.session_id;
  const response = { schema_version: "1.0", conversation_id: conversationId, turn_id: payload.turn_id, blocks };
  const events = [["turn.started", { schema_version: "1.0", conversation_id: conversationId, turn_id: payload.turn_id }]];
  if (textDelta) events.push(["text.delta", { text: textDelta }]);
  for (const block of blocks.filter((item) => item.type !== "text")) events.push(["component.ready", { block }]);
  if (!textDelta) {
    const finalText = blocks.filter((item) => item.type === "text").map((item) => item.content).join("\n");
    if (finalText) events.push(["text.completed", { streamed: false, text: finalText }]);
  }
  events.push(["turn.completed", { response }]);
  return events.map(([type, data], index) =>
    `id: ${payload.turn_id}:${index + 1}\nevent: ${type}\ndata: ${JSON.stringify(data)}\n\n`,
  ).join("");
}

async function updateGuestSessionClock(page, sessionId, mode) {
  const result = await page.evaluate(async ({ id, clockMode }) => {
    const response = await fetch("/__e2e__/guest-session-clock", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-E2E-Control": "playwright-local-session-clock-control" },
      body: JSON.stringify({ session_id: id, mode: clockMode }),
    });
    return { status: response.status, body: await response.json() };
  }, { id: sessionId, clockMode: mode });
  if (result.status !== 200) throw new Error(`Session clock control failed (${result.status}).`);
  return result.body;
}

async function waitForGuestSession(page) {
  await page.waitForFunction(() => {
    const startupError = document.querySelector("#startup-error");
    return Boolean(sessionStorage.getItem("concierge-v2-session-id")) || Boolean(startupError && !startupError.hidden);
  }, undefined, { timeout: 10000 });
  const sessionId = await page.evaluate(() => sessionStorage.getItem("concierge-v2-session-id"));
  if (!sessionId) {
    const message = await page.locator("#startup-error-copy").innerText().catch(() => "Guest UI could not start.");
    throw new Error(`Guest UI startup failed: ${message}`);
  }
  return sessionId;
}

// --- 1. Guest initial load ---

test("guest: opens on the personal stay home, with chat available separately", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("#home-view")).toBeVisible();
  await expect(page.locator(".experience-hero h1")).toBeVisible();
  await expect(page.locator(".experience-hero h1")).not.toHaveText("");
  await expect(page.locator("#concierge-view")).toBeHidden();
  await expect(page.getByLabel("Ask your concierge")).toBeVisible();
  await expect(page.locator("#send-button")).toBeDisabled();
});

test("guest: empty property home hides empty sections and unsupported routes", async ({ page }) => {
  // Absence assertions can pass before the intercepted startup requests finish.
  // Wait for both fixtures so teardown cannot dispose an in-flight route.fetch().
  const homeLoaded = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/guest/home" && response.status() === 200);
  const hotelLoaded = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/hotel" && response.status() === 200);
  await page.route("**/api/hotel", async (route) => {
    const response = await route.fetch();
    const profile = await response.json();
    profile.design = { ...(profile.design || {}), suggestions: [] };
    await route.fulfill({ response, json: profile });
  });
  await page.route("**/api/guest/home", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      greeting: "Welcome", stay: { status: "unverified" }, cards: [], active_requests: [],
      quick_actions: [{ label: "Internal action", view: "internal" }], suggested_prompts: [],
      inventory: { restaurants: [], facilities: [], events: [], promotions: [], recommendations: [], menu_items: [] },
    }),
  }));
  await page.goto("/");
  await Promise.all([homeLoaded, hotelLoaded]);
  await expect(page.locator(".experience-hero")).toBeVisible();

  await expect(page.locator(".experience-quick_actions")).toHaveCount(0);
  await expect(page.locator(".experience-card-grid")).toHaveCount(0);
  await expect(page.locator("#home-actions-section")).toBeHidden();
  await expect(page.locator("#home-cards-section")).toBeHidden();
  await expect(page.locator("#home-cards > article")).toHaveCount(0);
  await expect(page.locator("#quick-actions > button")).toHaveCount(0);
});

test("guest: optional catalog outages do not prevent a concierge session from starting", async ({ page }) => {
  await page.route("**/api/guest/service-catalog", (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Catalog temporarily unavailable" }),
  }));
  await page.route("**/api/guest/recommendations", (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Recommendations temporarily unavailable" }),
  }));
  const sessionStarted = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/session/start" && response.request().method() === "POST",
  );
  await page.goto("/");
  const response = await sessionStarted;

  expect(response.ok()).toBeTruthy();
  await expect(page.locator("#home-view")).toBeVisible();
  await expect(page.locator(".message-row.error")).toHaveCount(0);
});

test("guest: bottom navigation switches between stay, explore, requests, and concierge", async ({ page }) => {
  await page.goto("/");
  const navigation = await guestNavigation(page);
  await navigation.getByRole("button", { name: "Explore" }).click();
  await expect(page.locator("#explore-view")).toBeVisible();
  await navigation.getByRole("button", { name: "Requests" }).click();
  await expect(page.locator("#requests-view")).toBeVisible();
  await navigation.getByRole("button", { name: "My Stay" }).click();
  await expect(page.locator("#stay-view")).toBeVisible();
  await navigation.getByRole("button", { name: "Concierge", exact: true }).click();
  await expect(page.locator("#concierge-view")).toBeVisible();
  await navigation.getByRole("button", { name: "Home" }).click();
  await expect(page.locator("#home-view")).toBeVisible();
});

test("guest: Explore and My Stay use configured property content", async ({ page, request }) => {
  await ensureGuestData(request);
  await page.goto("/");
  const navigation = await guestNavigation(page);
  await navigation.getByRole("button", { name: "Explore" }).click();
  await expect(page.locator("#recommendation-list")).toContainText("Fixture Bistro");
  await navigation.getByRole("button", { name: "My Stay" }).click();
  await expect(page.locator("#stay-property-name")).toBeVisible();
  await expect(page.locator("#stay-summary-card")).toContainText("Active requests");
});

test("guest: hotel name and concierge name are displayed", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#hotel-name")).toBeVisible();
  await expect(page.locator("#concierge-name")).toBeVisible();
});

test("guest: property branding and home prompts use the published property design", async ({ page }) => {
  await page.route("**/api/hotel", async (route) => {
    const response = await route.fetch();
    const profile = await response.json();
    profile.design = {
      ...(profile.design || {}),
      branding: { ...(profile.design?.branding || {}), hotelName: "The Linden House by the Quiet Sea" },
      welcome: {
        ...(profile.design?.welcome || {}),
        greeting: "Welcome back",
        headline: "A stay shaped around you",
        description: "Property-configured welcome copy.",
      },
      suggestions: [
        { label: "Explore dining", prompt: "Show dining options", enabled: true, order: 0 },
        { label: "My stay details", prompt: "Tell me about my stay", enabled: true, order: 1 },
        { label: "Disabled action", prompt: "Unavailable prompt", enabled: false, order: 2 },
      ],
      pages: (profile.design?.pages || []).map((page) => page.id !== "home" ? page : {
        ...page,
        sections: page.sections.map((section) => section.type !== "hero" ? section : {
          ...section,
          properties: {
            ...(section.properties || {}),
            eyebrow: "Welcome back",
            headline: "A stay shaped around you",
            description: "Property-configured welcome copy.",
          },
        }),
      }),
    };
    await route.fulfill({ response, json: profile });
  });
  await page.route("**/api/chat", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ answer: "Here are the configured dining options.", source: "knowledge" }),
  }));
  await page.route("**/api/guest/home", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      greeting: "Good evening", preferred_name: "Jordan Sample", stay: { status: "checked_in" },
      primary_action: { label: "Explore dining", view: "explore" },
      primary_card: { type: "restaurant", title: "Configured Dining", subtitle: "Seasonal cuisine · Lobby level", description: "A property-configured dining option.", restaurant_id: "visual-dining" },
      cards: [
        { type: "event", title: "Guest activity", subtitle: "Today", description: "A configured property activity.", event_id: "visual-event" },
        { type: "recommendation", title: "Nearby dining", subtitle: "Dining", description: "A configured local recommendation.", recommendation_id: "visual-recommendation" },
        { type: "promotion", title: "Seasonal offer", subtitle: "Available today", description: "A configured property offer." },
      ],
      active_requests: [], quick_actions: [], suggested_prompts: ["Unconfigured fallback"],
      inventory: {
        restaurants: [{ restaurant_id: "visual-dining", name: "Configured Dining", cuisine: "Seasonal cuisine", location: "Lobby level", images: [] }],
        facilities: [], events: [{ event_id: "visual-event", title: "Guest activity" }],
        promotions: [], recommendations: [{ recommendation_id: "visual-recommendation", name: "Nearby dining", images: [] }], menu_items: [],
      },
    }),
  }));
  await page.goto("/");

  await expect(page.locator("#hotel-name")).toHaveText("The Linden House by the Quiet Sea");
  await expect(page.locator("#hotel-initial")).toHaveText("T");
  await expect(page.locator(".experience-hero h1")).toHaveText("A stay shaped around you");
  await expect(page.locator(".experience-hero")).toContainText("Property-configured welcome copy.");
  await expect(page.locator(".experience-hero .experience-eyebrow")).toHaveText("Welcome back");
  const quickActions = page.locator(".experience-quick_actions");
  await expect(quickActions).toContainText("Explore dining");
  await expect(quickActions).not.toContainText("Disabled action");
  await expect(quickActions).not.toContainText("Unconfigured fallback");
  await expect(quickActions.locator(".experience-action-card")).toHaveCount(2);
  await expect(page.locator(".experience-card-grid")).toContainText("Nearby dining");
  await page.screenshot({
    path: test.info().outputPath(`guest-home-redesign-${test.info().project.name}.png`),
    fullPage: true,
    animations: "disabled",
  });
  await quickActions.getByRole("button", { name: /Explore dining/ }).click();
  await expect(page.locator("#home-view")).toBeVisible();
  await expect(page.locator("#home-conversation")).toContainText("Here are the configured dining options.");
  await expect(page.locator("#concierge-view")).toBeHidden();
  await expect(page.locator("#home-conversation .message-row.user")).toHaveCount(1);
});

test("guest: home shows four configured actions first, then real supported routes in See all", async ({ page }) => {
  await page.route("**/api/hotel", async (route) => {
    const response = await route.fetch();
    const profile = await response.json();
    profile.design = {
      ...(profile.design || {}),
      suggestions: [
        { label: "Dining", prompt: "Show dining options", enabled: true, order: 0 },
        { label: "Room Service", prompt: "Show available room service", enabled: true, order: 1 },
        { label: "Housekeeping", prompt: "Request housekeeping service", enabled: true, order: 2 },
        { label: "Transportation", prompt: "Show configured transport options", enabled: true, order: 3 },
        { label: "Disabled action", prompt: "Unavailable action", enabled: false, order: 4 },
      ],
    };
    await route.fulfill({ response, json: profile });
  });
  await page.route("**/api/guest/home", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      greeting: "Welcome", stay: { status: "unverified" }, cards: [], active_requests: [], suggested_prompts: [],
      quick_actions: [
        { label: "My Stay", view: "stay" },
        { label: "Requests", view: "requests" },
        { label: "Explore", view: "explore" },
      ],
      inventory: { restaurants: [], facilities: [], events: [], promotions: [], recommendations: [], menu_items: [] },
    }),
  }));
  await page.goto("/");

  const actions = page.locator(".experience-quick_actions");
  await expect(actions.locator(".experience-action-card")).toHaveCount(4);
  await expect(actions).toContainText("Dining");
  await expect(actions).toContainText("Room Service");
  await expect(actions).toContainText("Housekeeping");
  await expect(actions).toContainText("Transportation");
  await expect(actions).not.toContainText("Disabled action");
  const more = actions.getByRole("button", { name: "See all" });
  await expect(more).toBeVisible();
  await more.click();
  await expect(actions.locator(".experience-see-all")).toHaveAttribute("aria-expanded", "true");
  await expect(actions.locator(".experience-action-card")).toHaveCount(7);
  await actions.getByRole("button", { name: /My Stay/ }).click();
  await expect(page.locator("#stay-view")).toBeVisible();
});

test("guest: home suggestion cards use property images and gracefully fall back for unsafe images", async ({ page }) => {
  await page.addInitScript(() => {
    window.open = (url) => {
      window.__capturedGuestUrl = String(url);
      return null;
    };
  });
  await page.route("**/api/guest/home", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      greeting: "Welcome", stay: { status: "unverified" }, primary_card: null,
      cards: [
        { type: "recommendation", title: "Featured property", subtitle: "Dining", description: "A safe image from property data.", recommendation_id: "safe-image", map_url: "https://maps.example/safe" },
        { type: "recommendation", title: "Text recommendation", subtitle: "Dining", description: "Still available without a valid image.", recommendation_id: "unsafe-image", map_url: "http://maps.example/property" },
      ],
      active_requests: [], quick_actions: [], suggested_prompts: [],
      inventory: {
        restaurants: [],
        facilities: [],
        events: [], promotions: [],
        recommendations: [
          { recommendation_id: "safe-image", name: "Featured property", images: ["/test-featured.svg"], map_url: "https://maps.example/safe" },
          { recommendation_id: "unsafe-image", name: "Text recommendation", images: ["javascript:alert(1)"], map_url: "http://maps.example/property" },
        ],
        menu_items: [],
      },
    }),
  }));
  await page.route("**/test-featured.svg", (route) => route.fulfill({
    status: 200,
    contentType: "image/svg+xml",
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="16"><rect width="24" height="16" fill="#c8a873"/></svg>',
  }));
  await page.route("**/missing-featured.svg", (route) => route.fulfill({ status: 404, body: "missing" }));
  await page.goto("/");

  const grid = page.locator(".experience-card-grid");
  await expect(grid).toBeVisible();
  await expect(grid.locator(".guest-card-has-image")).toHaveCount(1);
  await expect(grid).toContainText("Text recommendation");
  await expect(grid.locator("article").nth(1).locator(".guest-card-media")).toHaveCount(0);
  await grid.locator("article").first().getByRole("button", { name: "Directions" }).click();
  await expect.poll(() => page.evaluate(() => window.__capturedGuestUrl)).toBe("https://maps.example/safe");
  await grid.locator("article").nth(1).getByRole("button", { name: "Directions" }).click();
  await expect.poll(() => page.evaluate(() => window.__capturedGuestUrl)).toBe("http://maps.example/property");
});

test("guest: missing suggestion image falls back to its property content", async ({ page }) => {
  await page.route("**/api/hotel", async (route) => {
    const response = await route.fetch();
    const profile = await response.json();
    profile.design = {
      ...(profile.design || {}),
      pages: (profile.design?.pages || []).map((page) => page.id !== "home" ? page : {
        ...page,
        sections: page.sections.map((section) => section.type !== "card_grid" ? section : {
          ...section, properties: { ...(section.properties || {}), source: "facilities" },
        }),
      }),
    };
    await route.fulfill({ response, json: profile });
  });
  await page.route("**/api/guest/home", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      greeting: "Welcome", stay: { status: "unverified" }, primary_card: null,
      cards: [{ type: "facility", title: "Property facility", description: "Available property details.", facility_id: "missing-image" }],
      active_requests: [], quick_actions: [], suggested_prompts: [],
      inventory: { restaurants: [], facilities: [{ facility_id: "missing-image", name: "Property facility", description: "Available property details.", images: ["/missing-featured.svg"] }], events: [], promotions: [], recommendations: [], menu_items: [] },
    }),
  }));
  await page.route("**/missing-featured.svg", (route) => route.fulfill({ status: 404, body: "missing" }));
  await page.goto("/");

  const grid = page.locator(".experience-card-grid");
  await expect(grid).toContainText("Property facility");
  await expect(grid.locator(".guest-card-has-image")).toHaveCount(0);
  await expect(grid.locator("article")).toContainText("Available property details.");
});

test("guest: composer shortcuts open a supported guest view", async ({ page }) => {
  await page.route("**/api/hotel", async (route) => {
    const response = await route.fetch();
    const profile = await response.json();
    const pages = [
      {
        id: "home", type: "guest_home", version: 2, name: "Home", slug: "/", enabled: true,
        sections: [
          { id: "welcome", type: "hero", order: 0, enabled: true, properties: { headline: "Welcome" } },
          { id: "composer", type: "concierge_composer", order: 1, enabled: true, properties: { enabled: true, placeholder: "Ask your concierge..." } },
          { id: "bottom-navigation", type: "bottom_navigation", order: 2, enabled: true, properties: {
            show_labels: true, position: "fixed", height: "medium", icon_size: "medium", safe_area_padding: true,
            items: [
              { id: "nav-home", label: "Home", icon: "⌂", enabled: true, action: { type: "internal_page", page_id: "home" } },
              { id: "nav-explore", label: "Explore", icon: "◇", enabled: true, action: { type: "internal_page", page_id: "explore" } },
            ],
          } },
        ],
      },
      ...["explore", "requests", "stay", "concierge"].map((id) => ({ id, type: "guest_page", version: 1, name: id, slug: `/${id}`, enabled: true, sections: [] })),
    ];
    profile.design = { ...(profile.design || {}), pages, composer: { ...(profile.design?.composer || {}), enabled: true } };
    await route.fulfill({ response, json: profile });
  });
  await page.goto("/");
  const configuredNavigation = page.locator(".experience-configured-navigation");
  await expect(configuredNavigation).toBeVisible();
  if (await configuredNavigation.count()) {
    const composerBounds = await page.locator("#composer-region").boundingBox();
    const navigationBounds = await configuredNavigation.boundingBox();
    expect(composerBounds.y + composerBounds.height).toBeLessThanOrEqual(navigationBounds.y + 1);
  }
  await page.locator("#composer-actions-toggle").click();
  const shortcuts = page.locator("#composer-action-sheet");
  await expect(shortcuts).toBeVisible();
  await shortcuts.getByRole("button", { name: "Explore" }).click();
  await expect(page.locator("#explore-view")).toBeVisible();
  await expect(page.locator("#composer-action-sheet")).toBeHidden();
});

test("guest: unsafe configured hero image URLs fall back without loading", async ({ page }) => {
  await page.route("**/api/hotel", async (route) => {
    const response = await route.fetch();
    const profile = await response.json();
    profile.design = {
      ...(profile.design || {}),
      theme: { ...(profile.design?.theme || {}), backgroundImageUrl: "javascript:alert(document.domain)" },
    };
    await route.fulfill({ response, json: profile });
  });
  await page.goto("/");

  await expect(page.locator(".experience-hero img")).toHaveCount(0);
  await expect(page.locator(".experience-hero")).not.toHaveClass(/experience-hero-has-image/);
});

test("guest: property-configured hero image loads inside the home hero", async ({ page }) => {
  await page.route("**/api/hotel", async (route) => {
    const response = await route.fetch();
    const profile = await response.json();
    profile.design = {
      ...(profile.design || {}),
      theme: { ...(profile.design?.theme || {}), backgroundImageUrl: "/test-hero.svg" },
    };
    await route.fulfill({ response, json: profile });
  });
  await page.route("**/test-hero.svg", (route) => route.fulfill({
    status: 200,
    contentType: "image/svg+xml",
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"><rect width="2" height="2" fill="#b38a4a"/></svg>',
  }));
  await page.goto("/");

  await expect(page.locator(".experience-hero-image")).toBeVisible();
  await expect(page.locator(".experience-hero")).toHaveClass(/experience-hero-has-image/);
});

// --- 2. Chat submit and multiline composer ---

test("guest: chat submit works with direct input", async ({ page }) => {
  await page.goto("/");
  const input = page.getByLabel("Ask your concierge");
  await input.fill("What time is breakfast?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".message-row.user")).toContainText("What time is breakfast?");
  await expect(input).toHaveValue("");
});

test("guest: responsive shell keeps the concierge composer attached without horizontal overflow", async ({ page }) => {
  await page.route("**/api/chat", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ answer: "Your concierge is ready to help." }),
  }));
  await page.goto("/");
  const input = page.getByLabel("Ask your concierge");
  await input.fill("Hi");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator("#home-message-list .message-row.user .message-text")).toHaveText("Hi");
  await expect(page.locator("#home-conversation")).toBeVisible();
  await expect(page.locator(".experience-configured-navigation, #guest-bottom-nav").filter({ visible: true }).first()).toBeVisible();
  expect(await page.locator("#composer-region").evaluate((element) => element.parentElement.id)).toBe("home-conversation");

  const sizes = [375, 768, 1024, 1440, 1920];
  for (const width of sizes) {
    await page.setViewportSize({ width, height: 900 });
    const home = await page.evaluate(() => {
      const rect = (selector) => {
        const candidates = [...document.querySelectorAll(selector)];
        const element = candidates.find((candidate) => candidate.getClientRects().length) || candidates[0];
        if (!element) return null;
        const box = element.getBoundingClientRect();
        return { x: box.x, right: box.right, width: box.width, y: box.y, bottom: box.bottom };
      };
      const bubble = document.querySelector("#home-message-list .message-row.user .message-text");
      const bubbleStyle = bubble ? getComputedStyle(bubble) : null;
      const navigation = [...document.querySelectorAll(".experience-configured-navigation, .guest-bottom-nav")]
        .find((element) => element.getClientRects().length);
      return {
        viewport: document.documentElement.clientWidth,
        documentWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
        shell: rect(".concierge-shell"),
        headerMenu: rect(".experience-configured-menu, #menu-button"),
        brand: rect(".experience-configured-identity, .hotel-identity"),
        hero: rect(".experience-hero, .home-hero"),
        actions: rect(".experience-quick_actions, #home-actions-section"),
        conversation: rect("#home-conversation"),
        navigation: rect(".experience-configured-navigation, .guest-bottom-nav"),
        navigationPosition: getComputedStyle(navigation).position,
        composerPosition: getComputedStyle(document.querySelector("#composer-region")).position,
        composerParent: document.querySelector("#composer-region").parentElement.id,
        bubble: bubble ? {
          width: bubble.getBoundingClientRect().width,
          contentHeight: bubble.getBoundingClientRect().height
            - parseFloat(bubbleStyle.paddingTop || "0")
            - parseFloat(bubbleStyle.paddingBottom || "0"),
          lineHeight: parseFloat(bubbleStyle.lineHeight),
        } : null,
      };
    });

    expect(home.documentWidth).toBeLessThanOrEqual(home.viewport + 1);
    expect(home.shell.width).toBeLessThanOrEqual(Math.min(width, 1180) + 1);
    expect(home.shell.x).toBeGreaterThanOrEqual(-1);
    expect(home.shell.right).toBeLessThanOrEqual(width + 1);
    if (width > 1180) expect(Math.abs(home.shell.x - (width - home.shell.width) / 2)).toBeLessThanOrEqual(1);
    expect(home.headerMenu.x).toBeGreaterThanOrEqual(home.shell.x - 1);
    expect(home.headerMenu.right).toBeLessThanOrEqual(home.shell.right + 1);
    expect(home.brand.x).toBeGreaterThanOrEqual(home.shell.x - 1);
    expect(home.brand.right).toBeLessThanOrEqual(home.shell.right + 1);
    expect(home.actions.x).toBeCloseTo(home.conversation.x, 0);
    expect(home.hero.x).toBeCloseTo(home.conversation.x, 0);
    expect(home.navigation.x).toBeGreaterThanOrEqual(home.shell.x - 1);
    expect(home.navigation.right).toBeLessThanOrEqual(home.shell.right + 1);
    expect(home.composerParent).toBe("home-conversation");
    expect(home.composerPosition).not.toBe("fixed");
    expect(home.bubble.width).toBeGreaterThan(20);
    expect(home.bubble.contentHeight).toBeLessThanOrEqual(home.bubble.lineHeight * 1.5);

    await page.locator("#home-conversation [data-open-view='concierge']").click();
    await expect(page.locator("#concierge-card")).toBeVisible();
    await expect(page.locator("#concierge-card > #composer-region")).toBeVisible();
    const chat = await page.evaluate(() => {
      const rect = (element) => {
        const box = element.getBoundingClientRect();
        return { x: box.x, right: box.right, width: box.width, bottom: box.bottom };
      };
      const shell = document.querySelector(".concierge-shell");
      const card = document.querySelector("#concierge-card");
      const composer = document.querySelector("#composer-region");
      const nav = [...document.querySelectorAll(".experience-configured-navigation, .guest-bottom-nav")]
        .find((element) => element.getClientRects().length);
      return {
        documentWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
        viewport: document.documentElement.clientWidth,
        shell: rect(shell),
        card: rect(card),
        composer: rect(composer),
        composerParent: composer.parentElement.id,
        composerPosition: getComputedStyle(composer).position,
        navigation: rect(nav),
        navigationPosition: getComputedStyle(nav).position,
      };
    });
    expect(chat.documentWidth).toBeLessThanOrEqual(chat.viewport + 1);
    expect(home.hero.x).toBeCloseTo(chat.card.x, 0);
    expect(chat.card.x).toBeGreaterThanOrEqual(chat.shell.x - 1);
    expect(chat.card.right).toBeLessThanOrEqual(chat.shell.right + 1);
    expect(chat.composerParent).toBe("concierge-card");
    expect(chat.composerPosition).not.toBe("fixed");
    expect(chat.composer.bottom).toBeLessThanOrEqual(chat.card.bottom + 1);
    expect(chat.navigation.x).toBeGreaterThanOrEqual(chat.shell.x - 1);
    expect(chat.navigation.right).toBeLessThanOrEqual(chat.shell.right + 1);
    if (width >= 761) expect(chat.navigationPosition).not.toBe("fixed");
    await page.locator(".experience-configured-navigation [data-page-id='home']:visible, #guest-bottom-nav [data-view='home']:visible").first().click();
  }
});

test("guest: submitted message stays in the composer when session startup fails", async ({ page }) => {
  await page.route("**/api/session/start", (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Session service unavailable" }),
  }));
  await page.goto("/");
  await expect(page.locator(".message-row.error")).toHaveCount(1);

  const input = page.getByLabel("Ask your concierge");
  await input.fill("Hello concierge");
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.locator(".message-row.user")).toContainText("Hello concierge");
  await expect(input).toHaveValue("Hello concierge");
  await expect(page.locator(".message-row.error")).toHaveCount(1);
  await expect(page.locator(".message-row.error").first()).toContainText("Session service unavailable");
});

test("guest: failed chat request keeps the submitted draft", async ({ page }) => {
  await page.route("**/api/chat", (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Chat service unavailable" }),
  }));
  await page.goto("/");
  const input = page.getByLabel("Ask your concierge");
  await input.fill("What time is breakfast?");
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.locator(".message-row.concierge-contact")).toContainText("can't reach the concierge service right now");
  await expect(input).toHaveValue("What time is breakfast?");
  await expect(page.locator("#send-button")).toBeEnabled();
});

test("guest: empty submit is prevented", async ({ page }) => {
  await page.goto("/");
  const input = page.getByLabel("Ask your concierge");
  await input.fill("");
  await expect(page.locator("#send-button")).toBeDisabled();
  await page.locator("#composer-form").evaluate((form) => form.requestSubmit());
  expect(await page.locator(".message-row.user").count()).toBe(0);
});

test("guest: multiline composer with shift+enter", async ({ page }) => {
  await page.goto("/");
  const input = page.getByLabel("Ask your concierge");
  await input.fill("Line 1");
  await input.press("Shift+Enter");
  await input.type("Line 2");
  const value = await input.inputValue();
  expect(value).toContain("Line 1\n");
  expect(value).toContain("Line 2");
});

test("guest: Enter submits message", async ({ page }) => {
  await page.goto("/");
  const input = page.getByLabel("Ask your concierge");
  await input.fill("Hello");
  await input.press("Enter");
  await expect(page.locator(".message-row.user")).toContainText("Hello");
});

// --- 3. Wi-Fi authentication flow ---

test.describe("wi-fi authentication flow", () => {
test.describe.configure({ mode: "serial" });

test("guest: wi-fi flow shows only the enabled authentication type and its fields", async ({ page, request }) => {
  await setAuthTypes(request, ["pms"]);
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Connect me to Wi-Fi");
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.getByLabel("Login method")).toHaveValue("pms");
  await expect(page.getByLabel("Room number")).toBeVisible();
  await expect(page.getByLabel("Last name or PMS password")).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue" })).toBeVisible();
});

test("guest: wi-fi flow validates empty fields", async ({ page, request }) => {
  await setAuthTypes(request, ["pms"]);
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Connect me to Wi-Fi");
  await page.getByRole("button", { name: "Send message" }).click();

  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("status")).toContainText("Enter room number and last name.");
});

test("guest: wi-fi flow authenticates successfully in mock mode", async ({ page, request }) => {
  await setAuthTypes(request, ["pms"]);
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Connect me to Wi-Fi");
  await page.getByRole("button", { name: "Send message" }).click();

  await page.getByLabel("Room number").fill("412");
  await page.getByLabel("Last name or PMS password").fill("Smith");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByText("Demo authentication accepted. Internet access is simulated in mock mode.")).toBeVisible();
});

test("guest: wi-fi flow only lists enabled non-PMS methods", async ({ page, request }) => {
  await setAuthTypes(request, ["access_code"]);
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Connect me to Wi-Fi");
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.getByText("Choose an enabled Wi-Fi login method: Access Code.")).toBeVisible();
  await expect(page.getByLabel("Room number")).toHaveCount(0);
  await expect(page.getByLabel("Login method")).toHaveValue("access_code");
  await expect(page.getByRole("textbox", { name: "Access code" })).toBeVisible();
});

test("guest API rejects an authentication type disabled for the property", async ({ request }) => {
  await setAuthTypes(request, ["pms"]);
  const sessionResponse = await request.post("/api/session/start", {
    data: { client_id: "disabled-auth-method-test" },
  });
  expect(sessionResponse.ok()).toBeTruthy();
  const session = await sessionResponse.json();
  const response = await request.post("/api/authenticate", {
    data: { session_id: session.session_id, auth_type: "access_code", credentials: { access_code: "test-code" } },
  });
  expect(response.status()).toBe(403);
  await expect(response.json()).resolves.toMatchObject({ detail: "This authentication method is disabled for this hotel." });
});

test("master switch hides guest sign-in and rejects direct authentication requests", async ({ page, request }) => {
  await setAuthTypes(request, ["pms"]);
  await setAuthenticationEnabled(request, false);

  const hotel = await (await request.get("/api/hotel")).json();
  expect(hotel.authentication).toEqual({ enabled: false, enabled_types: [] });

  const sessionResponse = await request.post("/api/session/start", {
    data: { client_id: "master-auth-off-test" },
  });
  expect(sessionResponse.ok()).toBeTruthy();
  const session = await sessionResponse.json();
  const response = await request.post("/api/authenticate", {
    data: { session_id: session.session_id, auth_type: "pms", credentials: { room: "412", last_name: "Guest" } },
  });
  expect(response.status()).toBe(403);
  await expect(response.json()).resolves.toMatchObject({ detail: "Guest Wi-Fi authentication is turned off for this hotel." });

  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Connect me to Wi-Fi");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText(/sign-in through Concierge is turned off/i)).toBeVisible();
});

test("guest login selector contains every enabled authentication type and no disabled type", async ({ page, request }) => {
  await setAuthTypes(request, ["pms", "access_code", "global_code"]);
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Connect me to Wi-Fi");
  await page.getByRole("button", { name: "Send message" }).click();
  const method = page.getByLabel("Login method");
  await expect(method.locator("option")).toHaveCount(3);
  await expect(method.locator("option[value='pms']")).toHaveCount(1);
  await expect(method.locator("option[value='access_code']")).toHaveCount(1);
  await expect(method.locator("option[value='global_code']")).toHaveCount(1);
  await expect(method.locator("option[value='local']")).toHaveCount(0);
});

test("guest mock flow accepts each enabled authentication type", async ({ request }) => {
  const authTypes = ["complimentary", "local", "radius", "pms", "credit_card", "access_code", "global_account", "global_code", "user_form", "social_network"];
  await setAuthTypes(request, authTypes);
  const sessionResponse = await request.post("/api/session/start", {
    data: { client_id: "all-auth-methods-test" },
  });
  expect(sessionResponse.ok()).toBeTruthy();
  const session = await sessionResponse.json();
  const credentialsByType = {
    complimentary: { code: "free" },
    local: { username: "guest", password: "secret" },
    radius: { username: "guest", password: "secret" },
    pms: { room: "412", last_name: "Smith" },
    credit_card: {},
    access_code: { access_code: "hotel-code" },
    global_account: { username: "guest", password: "secret" },
    global_code: { global_code: "global-code" },
    user_form: { name: "Guest Example", email: "guest@example.test" },
    social_network: { social_provider: "facebook" },
  };
  for (const authType of authTypes) {
    const response = await request.post("/api/authenticate", {
      data: { session_id: session.session_id, auth_type: authType, credentials: credentialsByType[authType] },
    });
    expect(response.ok(), `${authType} was not accepted by the mock flow`).toBeTruthy();
    expect(await response.json()).toMatchObject({ status: "authenticated" });
  }
});
});

// --- 5. Nearby dining / restaurant cards ---

test("guest: nearby dining shows persisted recommendation cards", async ({ page, request }) => {
  await ensureGuestData(request);
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Recommend somewhere nearby to eat");
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.locator(".recommendation-card")).toHaveCount(1);
  await expect(page.locator(".recommendation-card").first()).toContainText("Fixture Bistro");
});

test("guest: local attraction answers render details and working map links", async ({ page }) => {
  let openedUrl = null;
  await page.exposeFunction("__testCaptureUrl", (url) => { openedUrl = url; });
  await page.addInitScript(() => {
    window.open = (url) => { window.__testCaptureUrl(String(url)); return null; };
  });
  await page.route("**/api/chat", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      answer: "Here is one nearby place from current local search.",
      source: "ai",
      places: [{
        place_id: "synthetic-art-walk",
        name: "Synthetic Art Walk",
        category: "Attraction",
        address: "1 Example Road",
        description: "A synthetic place used only for this browser test.",
        maps_url: "https://maps.example.test/synthetic-art-walk",
        open_now: true,
      }],
    }),
  }));
  await page.goto("/");
  await expect(page.locator("#hotel-name")).toContainText("E2E Property");
  await page.locator("#composer-input").fill("What local attractions are nearby?");
  await page.locator("#send-button").click();

  const card = page.locator(".recommendation-card").filter({ hasText: "Synthetic Art Walk" });
  await expect(card).toBeVisible();
  await expect(card).toContainText("Open now");
  await card.getByRole("button", { name: "Details" }).click();
  await expect(card).toContainText("A synthetic place used only for this browser test.");
  await card.getByRole("button", { name: "Directions" }).click();
  expect(openedUrl).toBe("https://maps.example.test/synthetic-art-walk");
});

test("guest: restaurant card directions button opens configured map", async ({ page, request }) => {
  await ensureGuestData(request);
  let openedUrl = null;
  await page.exposeFunction("__testCaptureUrl", (url) => { openedUrl = url; });
  await page.addInitScript(() => {
    const realOpen = window.open.bind(window);
    window.open = (url, ...args) => { window.__testCaptureUrl(String(url)); return realOpen(url, ...args); };
  });
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Recommend somewhere nearby to eat");
  await page.getByRole("button", { name: "Send message" }).click();

  const directionsBtn = page.locator(".recommendation-card").first().getByRole("button", { name: "Directions" });
  await directionsBtn.click();
  expect(openedUrl).toContain("maps.example/fixture");
});

test("guest: restaurant card details button toggles verified details", async ({ page, request }) => {
  await ensureGuestData(request);
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Recommend somewhere nearby to eat");
  await page.getByRole("button", { name: "Send message" }).click();

  const recommendation = page.locator(".recommendation-card").first();
  const detailsBtn = recommendation.getByRole("button", { name: "Details", exact: true });
  await detailsBtn.click();
  const details = recommendation.locator("p");
  await expect(details).toBeVisible();
  await expect(details).toHaveText("Synthetic test recommendation.");
  const hideDetailsBtn = recommendation.getByRole("button", { name: "Hide details", exact: true });
  await expect(hideDetailsBtn).toHaveAttribute("aria-expanded", "true");
  await hideDetailsBtn.click();
  const showDetailsBtn = recommendation.getByRole("button", { name: "Details", exact: true });
  await expect(details).toBeHidden();
  await expect(showDetailsBtn).toHaveAttribute("aria-expanded", "false");
  await showDetailsBtn.click();
  await expect(details).toBeVisible();
  await expect(recommendation.getByRole("button", { name: "Hide details", exact: true })).toHaveAttribute("aria-expanded", "true");
});

test("guest: expanded restaurant details survive a chat response rerender", async ({ page, request }) => {
  await ensureGuestData(request);
  let resumeChat;
  let markChatStarted;
  const chatGate = new Promise((resolve) => { resumeChat = resolve; });
  const chatStarted = new Promise((resolve) => { markChatStarted = resolve; });
  await page.route("**/api/chat", async (route) => {
    markChatStarted();
    await chatGate;
    await route.continue();
  });

  try {
    await page.goto("/");
    await page.getByLabel("Ask your concierge").fill("Recommend somewhere nearby to eat");
    const chatResponse = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/chat");
    await page.getByRole("button", { name: "Send message" }).click();
    await chatStarted;

    const recommendation = page.locator(".recommendation-card").first();
    const detailsBtn = recommendation.getByRole("button", { name: "Details", exact: true });
    await expect(recommendation).toBeVisible();
    await detailsBtn.click();
    await expect(recommendation.locator("p")).toBeVisible();
    await expect(recommendation.getByRole("button", { name: "Hide details", exact: true })).toHaveAttribute("aria-expanded", "true");

    resumeChat();
    await chatResponse;
    const expandedDetailsBtn = recommendation.getByRole("button", { name: "Hide details", exact: true });
    await expect(recommendation).toHaveCount(1);
    await expect(recommendation.locator("p")).toBeVisible();
    await expect(expandedDetailsBtn).toHaveAttribute("aria-expanded", "true");
    await expect(expandedDetailsBtn).toBeFocused();

    await expandedDetailsBtn.click();
    const collapsedDetailsBtn = recommendation.getByRole("button", { name: "Details", exact: true });
    await expect(recommendation.locator("p")).toBeHidden();
    await expect(collapsedDetailsBtn).toHaveAttribute("aria-expanded", "false");
    await collapsedDetailsBtn.click();
    await expect(recommendation.locator("p")).toBeVisible();
    await expect(recommendation.getByRole("button", { name: "Hide details", exact: true })).toHaveAttribute("aria-expanded", "true");
  } finally {
    resumeChat();
  }
});

test("guest can request restaurant staff from the hotel menu", async ({ page, request }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The escalation creates persistent conversation state.");
  const csrf = await loginAdmin(request);
  const properties = await (await request.get("/api/admin/properties")).json();
  const propertyId = properties.properties[0].property_id;
  const restaurantName = `Guest Staff ${Date.now().toString(36)}`;
  const created = await request.post(`/api/admin/properties/${propertyId}/restaurants`, {
    headers: { "X-CSRF-Token": csrf },
    data: { data: { name: restaurantName, opening_hours: { monday: "06:30-22:00" }, internal_notes: "Never shown to guests." } },
  });
  expect(created.ok()).toBeTruthy();
  const restaurant = await created.json();

  const facilitiesLoaded = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/guest/facilities");
  const sessionStarted = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/session/start" && response.request().method() === "POST");
  await page.goto("/");
  expect((await facilitiesLoaded).ok()).toBeTruthy();
  expect((await sessionStarted).ok()).toBeTruthy();
  await openHotelMenu(page);
  await page.getByRole("button", { name: "Talk to Restaurant Staff" }).click();
  await expect(page.locator("#restaurant-staff-dialog")).toBeVisible();
  await page.locator("#restaurant-staff-select").selectOption({ label: restaurantName });
  await expect(page.locator("#restaurant-staff-select")).toHaveValue(restaurant.restaurant_id);
  await page.locator("#restaurant-staff-reason").fill("Please confirm the dinner menu.");

  const escalation = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/escalate") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Request staff" }).click();
  const response = await escalation;
  expect(response.ok()).toBeTruthy();
  await expect(page.locator("#restaurant-staff-dialog")).not.toBeVisible();
  await expect(page.locator("#message-list")).toContainText("Your request is with the restaurant team");
});

// --- 6. Service request confirmation ---

test("guest: configured service request shows confirmation card", async ({ page, request }) => {
  await ensureGuestData(request);
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Send two towels to my room");
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.locator(".guest-action-card")).toContainText("Towels");
  await expect(page.getByRole("button", { name: "Send request" })).toBeVisible();
});

test("guest: a configured service can be requested directly without opening chat", async ({ page, request }) => {
  await ensureGuestData(request);
  await page.goto("/");
  await (await guestNavigation(page)).getByRole("button", { name: "Requests" }).click();
  await expect(page.locator("#request-catalog-list")).toContainText("Towels");
  await page.locator(".service-action-row").filter({ has: page.getByText("Towels", { exact: true }) }).getByRole("button", { name: "Request" }).click();
  await expect(page.locator("#request-action-confirmation")).toContainText("Send this request to the hotel team?");
  await page.locator("#request-action-confirmation").getByRole("button", { name: "Send request" }).click();
  await expect(page.locator("#request-list")).toContainText("Towels");
  await expect(page.locator("#concierge-view")).toBeHidden();
  await expect(page.locator("#message-list")).toBeEmpty();
});

test("guest: confirm request persists and returns a request id", async ({ page, request }) => {
  await ensureGuestData(request);
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Send two towels to my room");
  await page.getByRole("button", { name: "Send message" }).click();

  await page.getByRole("button", { name: "Send request" }).click();
  await expect(page.locator(".request-created-card")).toContainText("Towels");
  await expect(page.locator(".guest-action-card").getByRole("button", { name: "Request sent" })).toBeDisabled();
});

test("guest: confirmed service request appears in My Requests", async ({ page, request }) => {
  await ensureGuestData(request);
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Send two towels to my room");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".guest-action-card")).toContainText("Housekeeping");
  await page.getByRole("button", { name: "Send request" }).click();
  await expect(page.locator(".request-created-card")).toContainText("Towels");
  await page.getByRole("button", { name: "Track request" }).click();
  await expect(page.locator("#requests-view")).toBeVisible();
  await expect(page.locator("#request-list")).toContainText("Towels");
  await expect(page.locator("#request-list")).toContainText("Housekeeping");
});

test("guest: can cancel an active request from My Requests", async ({ page, request }) => {
  await ensureGuestData(request);
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Send two towels to my room");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".guest-action-card")).toContainText("Towels");
  await page.getByRole("button", { name: "Send request" }).click();
  await expect(page.locator(".request-created-card")).toContainText("Towels");
  await page.getByRole("button", { name: "Track request" }).click();

  const requestCard = page.locator("#request-list .request-status-card").filter({ hasText: "Towels" });
  await expect(requestCard).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await requestCard.getByRole("button", { name: "Cancel request" }).click();
  await expect(page.locator("#toast")).toContainText("Request cancelled.");
  await expect(requestCard).toContainText("Cancelled");
  await expect(requestCard.getByRole("button", { name: "Cancel request" })).toHaveCount(0);
});

// --- 7. Hotel menu ---

test("guest: menu opens and closes", async ({ page }) => {
  await page.goto("/");
  await openHotelMenu(page);
  await expect(page.locator("#hotel-menu")).toHaveClass(/open/);

  await page.getByRole("button", { name: "Close menu" }).click();
  await expect(page.locator("#hotel-menu")).not.toHaveClass(/open/);
});

test("guest: options button opens the same working menu", async ({ page }) => {
  await page.goto("/");
  await openHotelMenu(page);
  await expect(page.locator("#hotel-menu")).toHaveClass(/open/);
  await page.getByRole("button", { name: "Close menu" }).click();
  await expect(page.locator("#hotel-menu")).not.toHaveClass(/open/);
});

test("guest: hotel information menu action responds with configured property details", async ({ page, request }) => {
  const hotel = await (await request.get("/api/hotel")).json();
  await page.goto("/");
  await openHotelMenu(page);
  await page.getByRole("button", { name: /Hotel information/ }).click();
  await expect(page.locator(".message-row.assistant").last()).toContainText(hotel.description || hotel.name);
  await expect(page.locator("#hotel-menu")).not.toHaveClass(/open/);
});

for (const [label, expectedText] of [
  ["Language", "Language preference set"],
  ["Accessibility", "Accessibility display mode"],
  ["Privacy", "Authorized hotel staff can review conversation history"],
  ["Help", "Ask a question about this property"],
]) {
  test(`guest: ${label.toLowerCase()} menu action responds`, async ({ page }) => {
    await page.goto("/");
    await openHotelMenu(page);
    await page.getByRole("button", { name: new RegExp(label, "i") }).click();
    await expect(page.locator(".message-row.assistant").last()).toContainText(expectedText);
    await expect(page.locator("#hotel-menu")).not.toHaveClass(/open/);
  });
}

test("guest: new conversation resets messages", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Hello");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".message-row.user")).toBeVisible();

  await openHotelMenu(page);
  await page.getByRole("button", { name: "New conversation" }).click();
  await expect(page.locator(".message-row")).toHaveCount(0);
});

test("Intelligent UI: property opt-in answers from verified hotel data and keeps AI text inert", async ({ page, request }, testInfo) => {
  await setIntelligentUi(request, true, {
    welcome: "A quieter welcome for your stay.",
    prompts: ["What time is the pool open?", "Where can I have dinner?"],
    pool: { name: "Pool", location: "Level 3", opening_hours: { display: "6:00 AM to 10:00 PM" } },
  });
  try {
    await page.goto("/?experience=legacy");
    await expect(page.locator("#app-shell")).toBeVisible();
    await expect(page.locator("#welcome-description")).toHaveText("A quieter welcome for your stay.");
    await expect(page.locator("#welcome-suggestions button")).toHaveCount(2);
    await expect(page.locator("link[rel='stylesheet']")).toHaveAttribute("href", "/intelligent-ui/styles.css");

    const screenshotDirectory = testInfo.outputPath("screenshots");
    mkdirSync(screenshotDirectory, { recursive: true });
    await page.screenshot({ path: join(screenshotDirectory, `welcome-${testInfo.project.name}.png`), fullPage: true });

    for (const width of [320, 375, 390, 430, 768, 1024, 1440, 1920]) {
      await page.setViewportSize({ width, height: 850 });
      const metrics = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
        composerBottom: document.querySelector("#composer-form").getBoundingClientRect().bottom,
      }));
      expect(metrics.scrollWidth, `Intelligent UI overflowed at ${width}px`).toBeLessThanOrEqual(width);
      expect(metrics.composerBottom, `Intelligent UI composer escaped the viewport at ${width}px`).toBeLessThanOrEqual(851);
    }

    await page.setViewportSize({ width: 1280, height: 900 });
    await page.getByLabel("Message your concierge").fill("What time is the pool open?");
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.locator(".message-row.assistant .message-text").last()).toContainText("6:00 AM");
    await expect(page.locator(".message-row.assistant .message-text").last()).toContainText("Level 3");
    await page.screenshot({ path: join(screenshotDirectory, `conversation-${testInfo.project.name}.png`), fullPage: true });

    const conversationId = await page.evaluate(() => sessionStorage.getItem("concierge-v2-session-id"));
    await page.route("**/api/guest/intelligent-chat/stream", async (route) => {
      const requestBody = route.request().postDataJSON();
      const response = {
        schema_version: "1.0", conversation_id: conversationId, turn_id: requestBody.turn_id,
        blocks: [{ id: "inert-text", type: "text", content: '<img src=x onerror="window.__guestUiXss = true">' }],
      };
      const events = [
        ["turn.started", { schema_version: "1.0", conversation_id: conversationId, turn_id: requestBody.turn_id }],
        ["text.completed", { streamed: false, text: response.blocks[0].content }],
        ["turn.completed", { response }],
      ];
      await route.fulfill({
        status: 200,
        headers: { "content-type": "text/event-stream" },
        body: events.map(([type, data], index) =>
          `id: ${requestBody.turn_id}:${index + 1}\nevent: ${type}\ndata: ${JSON.stringify(data)}\n\n`,
        ).join(""),
      });
    });
    await page.getByLabel("Message your concierge").fill("Show me a text example");
    await page.getByRole("button", { name: "Send message" }).click();
    const untrustedMessage = page.locator(".message-row.assistant .message-text").last();
    await expect(untrustedMessage).toContainText("<img src=x");
    await expect(untrustedMessage.locator("img")).toHaveCount(0);
    expect(await page.evaluate(() => window.__guestUiXss || false)).toBe(false);
  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI: greeting, empty request status, confirmed request tracking, and responsive evidence", async ({ page, request }, testInfo) => {
  await ensureGuestData(request);
  await setIntelligentUi(request, true);
  const captureRoot = process.env.GUEST_UI_AUDIT_DIR
    ? resolve(process.env.GUEST_UI_AUDIT_DIR)
    : testInfo.outputPath("redesign-screenshots");
  const capture = testInfo.project.name === "chromium";
  if (capture) mkdirSync(captureRoot, { recursive: true });

  try {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await expect(page.locator("#app-shell")).toBeVisible();
    await expect(page.locator("#welcome-suggestions button")).toHaveCount(4);
    if (capture) await page.screenshot({ path: join(captureRoot, "welcome-1440x900.png"), fullPage: true });

    for (const viewport of [
      { width: 390, height: 844, label: "390x844" },
      { width: 768, height: 1024, label: "768x1024" },
      { width: 1440, height: 900, label: "1440x900" },
    ]) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      const metrics = await page.evaluate(() => ({
        document: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
        suggestionHeight: Math.min(...[...document.querySelectorAll(".suggestion-chip")].map((item) => item.getBoundingClientRect().height)),
      }));
      expect(metrics.document, `Guest welcome overflowed at ${viewport.label}`).toBeLessThanOrEqual(viewport.width);
      expect(metrics.suggestionHeight, `Suggestion touch target is too short at ${viewport.label}`).toBeGreaterThanOrEqual(44);
      if (capture) await page.screenshot({ path: join(captureRoot, `welcome-${viewport.label}.png`), fullPage: true });
    }

    await page.setViewportSize({ width: 1440, height: 900 });
    const composer = page.getByLabel("Message your concierge");
    await expect(composer).toBeFocused();
    await composer.fill("Hi");
    await page.keyboard.press("Enter");
    const greeting = page.locator(".message-row.assistant .message-text").last();
    await expect(greeting).toContainText("Hello!");
    await expect(greeting).not.toContainText("verified answer");

    if (capture) {
      for (const viewport of [
        { width: 390, height: 844, label: "390x844" },
        { width: 768, height: 1024, label: "768x1024" },
        { width: 1440, height: 900, label: "1440x900" },
      ]) {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        const metrics = await page.evaluate(() => ({ document: document.documentElement.scrollWidth, viewport: window.innerWidth }));
        expect(metrics.document, `Conversation overflowed at ${viewport.label}`).toBeLessThanOrEqual(viewport.width);
        await page.screenshot({ path: join(captureRoot, `greeting-${viewport.label}.png`) });
      }
    }

    await composer.fill("Where are my requests?");
    await page.keyboard.press("Enter");
    await expect(page.locator(".message-row.assistant .message-text").last()).toContainText("I don’t see a service request linked to this guest session");
    await expect(page.locator(".request-status-panel")).toHaveCount(0);

    await composer.fill("Please send two towels to my room");
    await page.keyboard.press("Enter");
    const review = page.locator(".request-review");
    await expect(review).toContainText("Towels");
    await review.getByRole("button", { name: "Confirm request" }).click();
    await expect(page.locator(".verified-confirmation").last()).toContainText("Your request has been sent");

    await composer.fill("What is the status of my request?");
    await page.keyboard.press("Enter");
    const status = page.locator(".request-status-panel");
    await expect(status).toBeVisible();
    await expect(status).toContainText("Towels");
    await expect(status).toContainText("Received");
    expect(await status.locator(".request-status-card").count()).toBeGreaterThan(0);
    if (capture) {
      for (const viewport of [
        { width: 390, height: 844, label: "390x844" },
        { width: 768, height: 1024, label: "768x1024" },
        { width: 1440, height: 900, label: "1440x900" },
      ]) {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await expect(status).toBeVisible();
        await status.scrollIntoViewIfNeeded();
        const metrics = await page.evaluate(() => ({ document: document.documentElement.scrollWidth, viewport: window.innerWidth }));
        expect(metrics.document, `Request status overflowed at ${viewport.label}`).toBeLessThanOrEqual(viewport.width);
        const geometry = await page.evaluate(() => ({
          messageBottom: document.querySelector(".request-status-panel").getBoundingClientRect().bottom,
          composerTop: document.querySelector(".composer-dock").getBoundingClientRect().top,
        }));
        expect(geometry.messageBottom, `Request status is covered by the composer at ${viewport.label}`).toBeLessThanOrEqual(geometry.composerTop);
        await page.screenshot({ path: join(captureRoot, `request-status-${viewport.label}.png`) });
      }
    }
  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI: indoor directions follow configured guest-visible map nodes", async ({ page, request }) => {
  const csrf = await loginAdmin(request);
  const propertyId = "e2e-property";
  const create = async (path, data) => {
    const response = await request.post(`/api/admin/properties/${propertyId}/${path}`, {
      headers: { "X-CSRF-Token": csrf }, data: { data },
    });
    expect(response.ok(), await response.text()).toBeTruthy();
    return response.json();
  };
  const existing = await (await request.get(`/api/admin/properties/${propertyId}/zones`)).json();
  const building = existing.buildings.find((item) => item.name === "Synthetic Test Tower")
    || await create("buildings", { name: "Synthetic Test Tower" });
  const floor = existing.floors.find((item) => item.building_id === building.building_id && item.name === "Ground floor")
    || await create("floors", { building_id: building.building_id, name: "Ground floor", level: 0 });
  const lobby = existing.navigation_nodes.find((item) => item.floor_id === floor.floor_id && item.label === "Lobby")
    || await create("navigation/nodes", { floor_id: floor.floor_id, label: "Lobby", x: 20, y: 50, guest_visible: true });
  const pool = existing.navigation_nodes.find((item) => item.floor_id === floor.floor_id && item.label === "Rooftop Pool")
    || await create("navigation/nodes", { floor_id: floor.floor_id, label: "Rooftop Pool", x: 180, y: 50, guest_visible: true });
  if (!existing.navigation_nodes.some((item) => item.floor_id === floor.floor_id && item.label === "Staff Office")) {
    await create("navigation/nodes", { floor_id: floor.floor_id, label: "Staff Office", x: 100, y: 80, guest_visible: false });
  }
  if (!existing.navigation_edges.some((item) => item.from_node_id === lobby.node_id && item.to_node_id === pool.node_id && item.guest_visible)) {
    await create("navigation/edges", { from_node_id: lobby.node_id, to_node_id: pool.node_id, distance: 42, guest_visible: true });
  }
  if (!existing.maps.some((item) => item.floor_id === floor.floor_id)) {
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><rect width="200" height="100" fill="#eee"/><path d="M20 50h160" stroke="#777" stroke-width="3"/></svg>';
    const uploadedMap = await request.post(`/api/admin/properties/${propertyId}/floors/${floor.floor_id}/maps`, {
      headers: { "X-CSRF-Token": csrf },
      data: { filename: "synthetic-test-map.svg", content_type: "image/svg+xml", content_base64: Buffer.from(svg).toString("base64"), width: 200, height: 100 },
    });
    expect(uploadedMap.ok(), await uploadedMap.text()).toBeTruthy();
  }
  await setIntelligentUi(request, true);
  try {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await expect(page.locator("#welcome-suggestions button")).toHaveCount(4);
    await page.waitForFunction(() => Boolean(sessionStorage.getItem("concierge-v2-session-id")));
    await page.getByLabel("Message your concierge").fill("Directions from Lobby to Rooftop Pool");
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.locator(".directions-panel")).toBeVisible();
    await expect(page.locator(".directions-panel")).toContainText("Lobby");
    await expect(page.locator(".directions-panel")).toContainText("Rooftop Pool");
    await expect(page.locator(".directions-panel")).not.toContainText("Staff Office");
    const map = page.locator(".map-panel");
    await expect(map).toBeVisible();
    await expect(map.locator(".floor-map-location-list")).toContainText("Lobby");
    await expect(map.locator(".floor-map-location-list")).toContainText("Rooftop Pool");
    await expect(map.getByRole("button", { name: "Show location: Rooftop Pool, Ground floor" })).toBeVisible();
  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI: synthetic hotel map supports selection, floors, safe routes, zoom, and admin updates", async ({ page, request }, testInfo) => {
  const csrf = await loginAdmin(request);
  const propertyId = "e2e-property";
  const create = async (path, data) => {
    const response = await request.post(`/api/admin/properties/${propertyId}/${path}`, {
      headers: { "X-CSRF-Token": csrf }, data: { data },
    });
    expect(response.ok(), await response.text()).toBeTruthy();
    return response.json();
  };
  const existing = await (await request.get(`/api/admin/properties/${propertyId}/zones`)).json();
  const building = existing.buildings.find((item) => item.name === "Hotel De Luna Conceptual Demo")
    || await create("buildings", { name: "Hotel De Luna Conceptual Demo" });
  const ensureFloor = async (name, level) => existing.floors.find((item) => item.building_id === building.building_id && item.name === name)
    || create("floors", { building_id: building.building_id, name, level });
  const level5 = await ensureFloor("Level 5 · conceptual demo", 5);
  const lobbyFloor = await ensureFloor("Ground Floor · conceptual demo", 0);
  const level16 = await ensureFloor("Level 16 · conceptual demo", 16);
  const ensureMap = async (floor, filename) => {
    if (existing.maps.some((item) => item.floor_id === floor.floor_id)) return;
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="620"><rect width="960" height="620" fill="#f7f4ec"/></svg>';
    const uploaded = await request.post(`/api/admin/properties/${propertyId}/floors/${floor.floor_id}/maps`, {
      headers: { "X-CSRF-Token": csrf },
      data: { filename, content_type: "image/svg+xml", content_base64: Buffer.from(svg).toString("base64"), width: 960, height: 620 },
    });
    expect(uploaded.ok(), await uploaded.text()).toBeTruthy();
  };
  await ensureMap(level5, "hotel-de-luna-level-5-conceptual.svg");
  await ensureMap(lobbyFloor, "hotel-de-luna-ground-floor-conceptual.svg");
  await ensureMap(level16, "hotel-de-luna-level-16-conceptual.svg");
  const ensureNode = async (floor, label, x, y) => existing.navigation_nodes.find((item) => item.floor_id === floor.floor_id && item.label === label)
    || create("navigation/nodes", { floor_id: floor.floor_id, label, x, y, node_type: "facility", guest_visible: true });
  const pool = await ensureNode(level5, "Infinity Pool", 153, 167);
  let fitness = existing.navigation_nodes.find((item) => item.floor_id === level5.floor_id && item.label === "Fitness Center");
  if (!fitness) {
    fitness = existing.navigation_nodes.find((item) => item.floor_id === level5.floor_id && item.label === "Fitness Studio");
    if (fitness) {
      const reset = await request.put(`/api/admin/properties/${propertyId}/navigation/nodes/${fitness.node_id}`, {
        headers: { "X-CSRF-Token": csrf },
        data: { data: { label: "Fitness Center", floor_id: level5.floor_id, x: 451, y: 167, guest_visible: true } },
      });
      expect(reset.ok(), await reset.text()).toBeTruthy();
    } else {
      fitness = await create("navigation/nodes", { floor_id: level5.floor_id, label: "Fitness Center", x: 451, y: 167, node_type: "facility", guest_visible: true });
    }
  }
  await ensureNode(level5, "Kids Club", 749, 167);
  const elevator = await ensureNode(level5, "Elevator Lobby", 153, 415);
  await ensureNode(lobbyFloor, "Main Lobby", 480, 310);
  await ensureNode(level16, "Guest Rooms", 153, 167);
  await ensureNode(level16, "Elevator Lobby", 451, 167);
  for (const edge of existing.navigation_edges.filter((item) =>
    [
      [elevator.node_id, pool.node_id], [pool.node_id, elevator.node_id],
    ].some(([from, to]) => item.from_node_id === from && item.to_node_id === to)
  )) {
    const removed = await request.delete(`/api/admin/properties/${propertyId}/navigation/edges/${edge.edge_id}`, {
      headers: { "X-CSRF-Token": csrf },
    });
    expect(removed.ok(), await removed.text()).toBeTruthy();
  }
  const profile = async (payload) => {
    const response = await request.put(`/api/admin/properties/${propertyId}/hospitality/facilities`, {
      headers: { "X-CSRF-Token": csrf }, data: { data: payload },
    });
    expect(response.ok(), await response.text()).toBeTruthy();
  };
  await profile({
    facility_id: "demo-map-pool", name: "Infinity Pool", facility_type: "pool", floor_id: level5.floor_id,
    description: "Pool access for registered guests.", opening_hours: { display: "06:00–21:00" },
    status_note: "DEMO artwork is an illustration, not a property photograph.",
    images: ["/api/guest/hotel-assets/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa?property_id=e2e-property"],
    policies: ["Children must be supervised."], location: "Pool deck",
  });
  await profile({
    facility_id: "demo-map-fitness", name: "Fitness Center", facility_type: "fitness", floor_id: level5.floor_id,
    description: "Fitness facilities for registered guests.", opening_hours: { display: "05:00–23:00" },
    status_note: "Demo schedule.", location: "Fitness room",
  });
  await profile({
    facility_id: "demo-map-guest-rooms", name: "Guest Rooms", facility_type: "guest_rooms", floor_id: level16.floor_id,
    description: "Guest accommodation on Level 16.", opening_hours: {}, status_note: "Demo location.", location: "Level 16",
  });

  await page.route("**/api/guest/hotel-assets/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 220"><rect width="480" height="220" fill="#1d514b"/><text x="24" y="120" fill="#fff" font-family="sans-serif" font-size="30">Infinity Pool · Demo Illustration</text></svg>',
    });
  });
  await setIntelligentUi(request, true);
  try {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await page.waitForFunction(() => Boolean(sessionStorage.getItem("concierge-v2-session-id")));
    await page.getByLabel("Message your concierge").fill("How do I get to Infinity Pool?");
    await page.getByRole("button", { name: "Send message" }).click();
    const map = page.locator(".map-panel");
    await expect(map).toBeVisible();
    await expect(map.locator(".floor-map-demo-note")).toHaveText("Demo map — illustrative layout");
    await expect(map.locator(".floor-map-room")).toHaveCount(4);
    await expect(map.locator(".floor-map-directions")).toContainText("Where are you starting from?");
    await expect(map.locator(".floor-map-facility-detail h4")).toHaveText("Infinity Pool");
    await expect(map.locator(".entity-card-image-caption")).toContainText("not a property photo");
    const facilityImage = map.locator(".floor-map-facility-image");
    await facilityImage.scrollIntoViewIfNeeded();
    await expect(facilityImage).toBeVisible();
    await expect.poll(() => facilityImage.evaluate((image) => image.naturalWidth)).toBeGreaterThan(0);
    await expect(page.locator(".directions-panel")).toHaveCount(0);

    await map.getByRole("button", { name: "Show location: Fitness Center, Level 5" }).click();
    await expect(map.locator(".floor-map-facility-detail h4")).toHaveText("Fitness Center");
    const keyboardTarget = map.getByRole("button", { name: "Show location: Kids Club, Level 5" });
    await keyboardTarget.focus();
    await keyboardTarget.press("Enter");
    await expect(map.locator(".floor-map-facility-detail h4")).toHaveText("Kids Club");
    await map.getByLabel("Choose a floor").selectOption({ label: "Ground Floor" });
    await expect(map.locator(".floor-map-room[aria-pressed='true']")).toHaveCount(0);
    await expect(map.locator(".floor-map-facility-detail")).toContainText("Choose a place on this floor");
    await map.getByRole("button", { name: "Show location: Main Lobby, Ground Floor" }).click();
    await expect(map.locator(".floor-map-facility-detail h4")).toHaveText("Main Lobby");
    await map.getByLabel("Choose a floor").selectOption({ label: "Level 5" });
    await expect(map.locator(".floor-map-facility-detail h4")).toHaveText("Infinity Pool");

    const startSelect = map.getByLabel("Starting location");
    await startSelect.selectOption(elevator.node_id);
    await map.getByRole("button", { name: "Check for a route" }).click();
    await expect(page.locator(".assistant .message-text").last()).toContainText("couldn't confirm a walking route");
    await expect(page.locator(".directions-panel")).toHaveCount(0);

    const edge = await create("navigation/edges", {
      from_node_id: elevator.node_id, to_node_id: pool.node_id, distance: 32, guest_visible: true,
    });
    expect(edge.guest_visible).toBeTruthy();
    await page.getByLabel("Message your concierge").fill("Directions from Elevator Lobby to Infinity Pool");
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.locator(".directions-panel")).toContainText("Elevator Lobby");
    await expect(page.locator(".directions-panel")).toContainText("Infinity Pool");
    await expect(page.locator(".map-panel .floor-map-route-overlay").last()).toBeVisible();
    const routeCaptureRoot = testInfo.outputPath("screenshots");
    mkdirSync(routeCaptureRoot, { recursive: true });
    const routeMap = page.locator(".map-panel").last().locator(".floor-map-viewport");
    await routeMap.scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(routeCaptureRoot, "hotel-map-verified-route-mobile-viewport.png") });
    await routeMap.screenshot({ path: join(routeCaptureRoot, "hotel-map-verified-route-map.png") });

    const updatedNode = await request.put(`/api/admin/properties/${propertyId}/navigation/nodes/${fitness.node_id}`, {
      headers: { "X-CSRF-Token": csrf },
      data: { data: { label: "Fitness Studio", floor_id: level5.floor_id, x: 451, y: 167, guest_visible: true } },
    });
    expect(updatedNode.ok(), await updatedNode.text()).toBeTruthy();
    await page.getByLabel("Message your concierge").fill("Where is the Fitness Studio?");
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.locator(".map-panel .floor-map-location-list").last()).toContainText("Fitness Studio");

    const captureRoot = testInfo.outputPath("screenshots");
    mkdirSync(captureRoot, { recursive: true });
    for (const viewport of [
      { width: 390, height: 844, name: "mobile" },
      { width: 820, height: 1180, name: "tablet" },
      { width: 1280, height: 900, name: "desktop" },
    ]) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      const currentMap = page.locator(".map-panel").last();
      await currentMap.locator(".floor-map-viewport").scrollIntoViewIfNeeded();
      await page.screenshot({ path: join(captureRoot, `hotel-map-${viewport.name}-viewport.png`) });
      await currentMap.screenshot({ path: join(captureRoot, `hotel-map-${viewport.name}.png`) });
      const room = currentMap.getByRole("button", { name: "Show location: Infinity Pool, Level 5" });
      if (await room.count()) await room.click();
      await currentMap.getByRole("button", { name: "Zoom in" }).click();
      const mapViewport = currentMap.locator(".floor-map-viewport");
      const scrollable = await mapViewport.evaluate((node) => node.scrollWidth > node.clientWidth || node.scrollHeight > node.clientHeight);
      expect(scrollable, `The ${viewport.name} map must support pan after zooming`).toBeTruthy();
      await mapViewport.evaluate((node) => { node.scrollLeft = node.scrollWidth; node.scrollTop = node.scrollHeight; });
      await expect(currentMap.locator(".floor-map-room").first()).toBeVisible();
      await currentMap.getByRole("button", { name: "Reset map view" }).click();
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator(".floor-map-directions-link").last().scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(captureRoot, "hotel-map-mobile-details-viewport.png") });
    const geometry = await page.evaluate(() => ({
      contentBottom: document.querySelector(".floor-map-directions-link").getBoundingClientRect().bottom,
      composerTop: document.querySelector(".composer-dock").getBoundingClientRect().top,
    }));
    expect(geometry.contentBottom).toBeLessThanOrEqual(geometry.composerTop);

    const screenshotRoot = testInfo.outputPath("screenshots");
    mkdirSync(screenshotRoot, { recursive: true });
    await page.getByLabel("Message your concierge").fill("Where is the Infinity Pool?");
    await page.getByRole("button", { name: "Send message" }).click();
    const previousAssistant = page.locator(".message-row.assistant").last();
    const previousMessageId = await previousAssistant.getAttribute("data-message-id");
    const previousMap = page.locator(`[data-message-id="${previousMessageId}"] .map-panel`);
    await expect(previousAssistant.locator(".message-text")).toContainText("The Infinity Pool is on Level 5");
    await expect(previousMap.getByRole("heading", { name: "Hotel map · Level 5" })).toBeVisible();
    await expect(previousMap.getByRole("button", { name: "Show location: Infinity Pool, Level 5" })).toHaveAttribute("aria-pressed", "true");
    await previousMap.getByLabel("Choose a floor").selectOption({ label: "Level 16" });
    await expect(previousMap.locator(".floor-map-room[aria-pressed='true']")).toHaveCount(0);
    await previousMap.getByRole("button", { name: "Show location: Guest Rooms, Level 16" }).click();
    await expect(previousMap.locator(".floor-map-facility-detail h4")).toHaveText("Guest Rooms");
    await page.screenshot({ path: join(screenshotRoot, "hotel-map-sync-level16-before-pool.png") });

    await page.getByLabel("Message your concierge").fill("Where is the Infinity Pool?");
    await page.getByRole("button", { name: "Send message" }).click();
    const poolMap = page.locator(".map-panel").last();
    await expect(poolMap.getByRole("heading", { name: "Hotel map · Level 5" })).toBeVisible();
    await expect(poolMap.getByRole("button", { name: "Show location: Infinity Pool, Level 5" })).toHaveAttribute("aria-pressed", "true");
    await expect(poolMap.locator(".floor-map-facility-detail h4")).toHaveText("Infinity Pool");
    await expect(page.locator(".message-row.assistant").last().locator(".message-text")).toContainText("The Infinity Pool is on Level 5");
    await expect(previousMap.getByRole("heading", { name: "Hotel map · Level 16" })).toBeVisible();
    await expect(previousMap.locator(".floor-map-facility-detail h4")).toHaveText("Guest Rooms");
    await page.screenshot({ path: join(screenshotRoot, "hotel-map-sync-pool-after.png") });

    const poolMapBeforeReset = await poolMap.screenshot({ path: join(screenshotRoot, "hotel-map-pool-before-reset.png") });
    expect(poolMapBeforeReset.length).toBeGreaterThan(0);
    for (const viewport of [
      { width: 390, height: 844, name: "mobile" },
      { width: 820, height: 1180, name: "tablet" },
      { width: 1280, height: 900, name: "desktop" },
    ]) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      const mapBounds = await poolMap.locator(".floor-map-viewport").boundingBox();
      expect(mapBounds.width / mapBounds.height, `${viewport.name} map should stay compact`).toBeGreaterThan(1.2);
      await page.screenshot({ path: join(screenshotRoot, `hotel-map-sync-pool-${viewport.name}-viewport.png`) });
      await poolMap.screenshot({ path: join(screenshotRoot, `hotel-map-sync-pool-${viewport.name}.png`) });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await poolMap.getByLabel("Choose a floor").selectOption({ label: "Level 16" });
    await expect(poolMap.locator(".floor-map-room[aria-pressed='true']")).toHaveCount(0);
    await poolMap.getByRole("button", { name: "Reset map view" }).click();
    await expect(poolMap.getByRole("heading", { name: "Hotel map · Level 5" })).toBeVisible();
    await expect(poolMap.getByRole("button", { name: "Show location: Infinity Pool, Level 5" })).toHaveAttribute("aria-pressed", "true");
    await page.reload();
    const restoredPoolMap = page.locator(".map-panel").last();
    await expect(restoredPoolMap.getByRole("heading", { name: "Hotel map · Level 5" })).toBeVisible();
    await expect(restoredPoolMap.locator(".floor-map-facility-detail h4")).toHaveText("Infinity Pool");

    const mapCountBeforeUnknown = await page.locator(".map-panel").count();
    await page.getByLabel("Message your concierge").fill("Where is the spa?");
    await page.getByLabel("Message your concierge").press("Enter");
    await expect(page.locator(".message-row.assistant").last().locator(".message-text")).toContainText("I couldn't find a mapped location");
    await expect(page.locator(".map-panel")).toHaveCount(mapCountBeforeUnknown);

    const latestRow = page.locator(".message-row.assistant").last();
    const clipping = await page.evaluate(() => ({
      messageTop: document.querySelector(".message-row.assistant:last-child").getBoundingClientRect().top,
      workspaceTop: document.querySelector("#conversation-workspace").getBoundingClientRect().top,
      headerBottom: document.querySelector(".topbar").getBoundingClientRect().bottom,
    }));
    expect(clipping.messageTop).toBeGreaterThanOrEqual(clipping.workspaceTop - 1);
    expect(clipping.workspaceTop).toBeGreaterThanOrEqual(clipping.headerBottom - 1);
    await expect(latestRow).toBeVisible();
  } finally {
    await setIntelligentUi(request, false);
    for (const facilityId of ["demo-map-pool", "demo-map-fitness", "demo-map-guest-rooms"]) {
      const response = await request.delete(`/api/admin/properties/${propertyId}/hospitality/facilities/${facilityId}`, {
        headers: { "X-CSRF-Token": csrf },
      });
      expect(response.status() === 404 || response.ok(), await response.text()).toBeTruthy();
    }
  }
});

test("Intelligent UI: loading, backend error, and expired-session states offer safe recovery", async ({ page, request }) => {
  await setIntelligentUi(request, true);
  try {
    await page.goto("/");
    await page.waitForFunction(() => Boolean(sessionStorage.getItem("concierge-v2-session-id")));
    await page.route("**/api/guest/intelligent-chat/stream", async (route) => {
      const message = route.request().postDataJSON()?.message || "";
      if (message === "Wait for the concierge") {
        await new Promise((resolve) => setTimeout(resolve, 1200));
        try { await route.abort(); } catch { /* The guest may have stopped the response already. */ }
        return;
      }
      if (message === "Backend error") {
        await route.fulfill({ status: 502, contentType: "application/json", body: JSON.stringify({ detail: "The concierge service is temporarily unavailable." }) });
        return;
      }
      await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Concierge session expired." }) });
    });

    const composer = page.getByLabel("Message your concierge");
    await composer.fill("Wait for the concierge");
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.locator(".loading-line")).toBeVisible();
    await expect(page.getByRole("button", { name: "Stop response" })).toBeVisible();
    await page.getByRole("button", { name: "Stop response" }).click();
    await expect(page.locator(".error-panel")).toContainText("Response stopped");

    await composer.fill("Backend error");
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.locator(".error-panel").last()).toContainText("temporarily unavailable");

    await composer.fill("Expired session");
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.locator(".error-panel").last()).toContainText("session has expired");
    await expect(page.locator(".error-panel").last()).toContainText("Start a new chat");
  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI: sourced restaurant cards show configured status at mobile and desktop widths", async ({ page, request }) => {
  const csrf = await loginAdmin(request);
  const name = `Synthetic Dinner ${Date.now()}`;
  const created = await request.post("/api/admin/properties/e2e-property/restaurants", {
    headers: { "X-CSRF-Token": csrf },
    data: { data: {
      name,
      cuisine: "Synthetic test cuisine",
      meal_periods: ["dinner"],
      opening_hours: { display: "5:00 PM–10:00 PM" },
      location: "Lobby level",
      status: "temporarily_closed",
    } },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  const restaurant = await created.json();
  try {
    await setIntelligentUi(request, true, { welcome: "Welcome to the dining guide." });
    await page.goto("/?experience=legacy");
    await page.setViewportSize({ width: 320, height: 844 });
    await page.getByLabel("Message your concierge").fill("Where can I have dinner?");
    await page.getByRole("button", { name: "Send message" }).click();
    const card = page.locator(".entity-card-restaurant").filter({ hasText: name });
    await expect(card).toBeVisible();
    await expect(card).toContainText("Temporarily closed");
    await expect(card).toHaveAttribute("data-source-ids", `guest:e2e-property:restaurant:${restaurant.restaurant_id}`);

    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
      await expect(card).toBeVisible();
      await expect(card).toContainText("Temporarily closed");
      const dimensions = await page.evaluate(() => ({
        viewport: window.innerWidth,
        document: document.documentElement.scrollWidth,
        card: document.querySelector(".entity-card-restaurant").getBoundingClientRect(),
      }));
      expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport + 1);
      expect(dimensions.card.left).toBeGreaterThanOrEqual(0);
      expect(dimensions.card.right).toBeLessThanOrEqual(dimensions.viewport + 1);
    }
  } finally {
    await setIntelligentUi(request, false);
    const archived = await request.put(`/api/admin/properties/e2e-property/restaurants/${restaurant.restaurant_id}`, {
      headers: { "X-CSRF-Token": csrf },
      data: { data: { status: "archived" } },
    });
    expect(archived.ok(), await archived.text()).toBeTruthy();
  }
});

test("Intelligent UI: dinner menu cards show only published available items and prices", async ({ page, request }) => {
  const csrf = await loginAdmin(request);
  const restaurantName = `Published Dinner ${Date.now()}`;
  const createdRestaurant = await request.post("/api/admin/properties/e2e-property/restaurants", {
    headers: { "X-CSRF-Token": csrf },
    data: { data: { name: restaurantName, meal_periods: ["dinner"], status: "open" } },
  });
  expect(createdRestaurant.ok(), await createdRestaurant.text()).toBeTruthy();
  const restaurant = await createdRestaurant.json();
  let menuId = "";
  try {
    const createdMenu = await request.post(`/api/admin/properties/e2e-property/restaurants/${restaurant.restaurant_id}/menus`, {
      headers: { "X-CSRF-Token": csrf },
      data: { data: { name: "Dinner Menu", meal_period: "dinner" } },
    });
    expect(createdMenu.ok(), await createdMenu.text()).toBeTruthy();
    const menu = await createdMenu.json();
    menuId = menu.menu_id;
    const createdItem = await request.post(`/api/admin/properties/e2e-property/menus/${menuId}/items`, {
      headers: { "X-CSRF-Token": csrf },
      data: { data: {
        name: "Grilled Salmon", description: "Served with local vegetables.", price: "PHP 850",
      } },
    });
    expect(createdItem.ok(), await createdItem.text()).toBeTruthy();
    const createdUnavailableItem = await request.post(`/api/admin/properties/e2e-property/menus/${menuId}/items`, {
      headers: { "X-CSRF-Token": csrf },
      data: { data: { name: "Unavailable Dessert", price: "PHP 1", available: false } },
    });
    expect(createdUnavailableItem.ok(), await createdUnavailableItem.text()).toBeTruthy();
    for (const action of ["approve", "publish"]) {
      const changed = await request.post(`/api/admin/properties/e2e-property/menus/${menuId}/${action}`, {
        headers: { "X-CSRF-Token": csrf },
      });
      expect(changed.ok(), await changed.text()).toBeTruthy();
    }

    await setIntelligentUi(request, true, { welcome: "Welcome to the dining guide." });
    await page.goto("/?experience=legacy");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByLabel("Message your concierge").fill("What is on the dinner menu?");
    await page.getByRole("button", { name: "Send message" }).click();
    const panel = page.locator(".detail-panel");
    await expect(panel).toBeVisible();
    await expect(panel).toContainText("Grilled Salmon");
    await expect(panel).toContainText("Served with local vegetables.");
    await expect(panel).toContainText("PHP 850");
    await expect(panel).not.toContainText("Unavailable Dessert");
    await expect(page.locator(".entity-card-restaurant").filter({ hasText: restaurantName })).toBeVisible();
  } finally {
    await setIntelligentUi(request, false);
    const archived = await request.put(`/api/admin/properties/e2e-property/restaurants/${restaurant.restaurant_id}`, {
      headers: { "X-CSRF-Token": csrf }, data: { data: { status: "archived" } },
    });
    expect(archived.ok(), await archived.text()).toBeTruthy();
  }
});

test("Intelligent UI: breakfast answer uses the current property's configured hours", async ({ page, request }) => {
  const csrf = await loginAdmin(request);
  const propertyResponse = await request.get("/api/admin/properties/e2e-property");
  expect(propertyResponse.ok()).toBeTruthy();
  const property = await propertyResponse.json();
  property.contact_details = {
    ...(property.contact_details || {}),
    breakfast: "Breakfast is served daily from 7:00 to 10:00 in the Atrium.",
  };
  const saved = await request.put("/api/admin/properties/e2e-property", {
    headers: { "X-CSRF-Token": csrf },
    data: property,
  });
  expect(saved.ok(), await saved.text()).toBeTruthy();

  await setIntelligentUi(request, true);
  try {
    await page.goto("/");
    await page.getByLabel("Message your concierge").fill("What time is breakfast?");
    await page.getByRole("button", { name: "Send message" }).click();
    const answer = page.locator(".message-row.assistant .message-text").last();
    await expect(answer).toContainText("Breakfast is served daily from 7:00 to 10:00 in the Atrium.");
    await expect(answer).not.toContainText("Breakfast hours are not available");
  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI: verified floor maps render interactive markers and a text alternative", async ({ page, request }, testInfo) => {
  await setIntelligentUi(request, true);
  try {
    await page.route(/\/api\/guest\/floor-maps\/test-map\/asset/, (route) => route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><rect width="200" height="100" fill="#eee"/><path d="M10 50h180" stroke="#999" stroke-width="4"/></svg>',
    }));
    await page.route("**/api/guest/intelligent-chat/stream", async (route) => {
      const requestBody = route.request().postDataJSON();
      const conversationId = await page.evaluate(() => sessionStorage.getItem("concierge-v2-session-id"));
      const mapBlock = {
        id: "configured-floor-map", type: "map_view", title: "Hotel map · Level 3",
        map_image_url: "/api/guest/floor-maps/test-map/asset?property_id=e2e-property",
        map_alt: "Configured Level 3 floor plan. Marked locations: Rooftop Pool, Elevator.",
        image_width: 200, image_height: 100,
        markers: [
          { id: "pool-node", label: "Rooftop Pool", x_percent: 50, y_percent: 50 },
          { id: "elevator-node", label: "Elevator", x_percent: 10, y_percent: 25 },
        ],
      };
      const response = {
        schema_version: "1.0", conversation_id: conversationId, turn_id: requestBody.turn_id,
        blocks: [
          { id: "map-answer", type: "text", content: "The pool is marked on Level 3." },
          mapBlock,
        ],
      };
      const events = [
        ["turn.started", { schema_version: "1.0", conversation_id: conversationId, turn_id: requestBody.turn_id }],
        ["component.ready", { block: mapBlock }],
        ["text.completed", { streamed: false, text: response.blocks[0].content }],
        ["turn.completed", { response }],
      ];
      await route.fulfill({
        status: 200,
        headers: { "content-type": "text/event-stream" },
        body: events.map(([type, data], index) =>
          `id: ${requestBody.turn_id}:${index + 1}\nevent: ${type}\ndata: ${JSON.stringify(data)}\n\n`,
        ).join(""),
      });
    });
    await page.goto("/");
    await page.getByLabel("Message your concierge").fill("How do I get to the pool?");
    await page.getByRole("button", { name: "Send message" }).click();
    const map = page.locator(".map-panel");
    await expect(map.getByRole("heading", { name: "Hotel map · Level 3" })).toBeVisible();
    await expect(map.locator(".floor-map-image")).toBeVisible();
    await expect(map.locator(".floor-map-alternative")).toContainText("Rooftop Pool, Elevator");
    const poolMarker = map.getByRole("button", { name: "Show location: Rooftop Pool" });
    await poolMarker.click();
    await expect(poolMarker).toHaveAttribute("aria-pressed", "true");
    await expect(map.locator(".floor-map-selection")).toHaveText("Rooftop Pool");

    if (testInfo.project.name === "chromium") {
      const screenshotDirectory = testInfo.outputPath("screenshots");
      mkdirSync(screenshotDirectory, { recursive: true });
      await map.screenshot({ path: join(screenshotDirectory, "map-chromium.png") });
    }
  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI: facility directory searches by building and floor and opens official maps", async ({ page, request }) => {
  await setIntelligentUi(request, true, { prompts: ["Find a location"] });
  try {
    await page.route("**/api/guest/intelligent-chat/stream", async (route) => {
      const payload = route.request().postDataJSON();
      const directory = {
        id: "rwg-directory",
        type: "facility_directory",
        title: "Resorts World Genting locations",
        description: "Reference listings checked 2026-10-14. Outlet hours and live status are not connected.",
        locations: [
          {
            id: "atm-1", title: "ATM", category: "banking", building: "SkyAvenue", floor: "1",
            location: "Near currency exchange", description: "Official directory listing.", listed_hours: "",
            source_url: "https://www.rwgenting.com/en/things-to-do/shopping/skyavenue-complex.html", source_ids: [],
          },
          {
            id: "coffee-1", title: "Coffee Terrace", category: "restaurant", building: "Genting Grand Hotel Complex", floor: "G",
            location: "Lot G/G5.00", description: "", listed_hours: "", source_url: "", source_ids: [],
          },
        ],
        map_links: [{
          id: "skyavenue-directory", title: "SkyAvenue official directory", scope: "SkyAvenue",
          format: "html", url: "https://www.rwgenting.com/en/things-to-do/shopping/skyavenue-complex.html",
          license_status: "not-cleared", source_ids: [],
        }],
        source_ids: [],
      };
      const conversationId = payload.session_id;
      const response = { schema_version: "1.0", conversation_id: conversationId, turn_id: payload.turn_id, blocks: [directory] };
      const events = [
        ["turn.started", { schema_version: "1.0", conversation_id: conversationId, turn_id: payload.turn_id }],
        ["component.ready", { block: directory }],
        ["turn.completed", { response }],
      ];
      await route.fulfill({
        status: 200,
        headers: { "content-type": "text/event-stream" },
        body: events.map(([type, data], index) =>
          `id: ${payload.turn_id}:${index + 1}\nevent: ${type}\ndata: ${JSON.stringify(data)}\n\n`,
        ).join(""),
      });
    });
    await page.goto("/");
    await page.getByLabel("Message your concierge").fill("Find a location");
    await page.getByRole("button", { name: "Send message" }).click();
    const directory = page.locator(".facility-directory");
    await expect(directory.getByRole("heading", { name: "Resorts World Genting locations" })).toBeVisible();
    await expect(directory.getByText("2 locations")).toBeVisible();
    await expect(directory.getByRole("heading", { name: "ATM" })).toBeVisible();

    await directory.getByLabel("Search locations by name, building, floor, or category").fill("coffee");
    await expect(directory.getByText("1 location")).toBeVisible();
    await expect(directory.getByRole("heading", { name: "Coffee Terrace" })).toBeVisible();
    await expect(directory.getByRole("heading", { name: "ATM" })).toHaveCount(0);

    await directory.getByLabel("Search locations by name, building, floor, or category").fill("");
    await directory.getByLabel("Filter by building").selectOption("SkyAvenue");
    await expect(directory.getByRole("heading", { name: "ATM" })).toBeVisible();
    await expect(directory.getByRole("heading", { name: "Coffee Terrace" })).toHaveCount(0);
    await expect(directory.getByRole("link", { name: /Open official directory: SkyAvenue/ })).toHaveAttribute(
      "href", "https://www.rwgenting.com/en/things-to-do/shopping/skyavenue-complex.html",
    );
    await expect(directory).toContainText("does not provide indoor routes");
  } finally {
    await setIntelligentUi(request, false);
  }
});

const typedSelectionBlock = {
  id: "dining-details",
  type: "selection_form",
  title: "Dining details",
  fields: [
    { id: "date", label: "Date", input_type: "date", required: true },
    { id: "time", label: "Time", input_type: "time", required: true },
    { id: "quantity", label: "Quantity", input_type: "quantity", minimum: 1, maximum: 8, required: true },
    { id: "party-size", label: "Party size", input_type: "party_size", minimum: 1, maximum: 10, required: true },
    { id: "service", label: "Dining preference", input_type: "service_option", options: [
      { label: "Indoor", value: "indoor" }, { label: "Patio", value: "patio" },
    ], required: true },
  ],
};

test("Intelligent UI: typed selections validate, support edit and cancel, and do not book", async ({ page, request }, testInfo) => {
  await setIntelligentUi(request, true);
  const messages = [];
  const guestMutations = [];
  page.on("request", (browserRequest) => {
    if (browserRequest.url().includes("/api/guest/") && browserRequest.method() !== "GET") {
      guestMutations.push(browserRequest.url());
    }
  });
  try {
    await page.route("**/api/guest/intelligent-chat/stream", async (route) => {
      const payload = route.request().postDataJSON();
      messages.push(payload.message);
      const conversationId = payload.session_id;
      const block = messages.length === 1 ? typedSelectionBlock : { id: "shared", type: "text", content: "Your preferences were shared with the concierge." };
      const response = { schema_version: "1.0", conversation_id: conversationId, turn_id: payload.turn_id, blocks: [block] };
      const events = [
        ["turn.started", { schema_version: "1.0", conversation_id: conversationId, turn_id: payload.turn_id }],
        ["component.ready", { block }],
        ...(block.type === "text" ? [["text.completed", { streamed: false, text: block.content }]] : []),
        ["turn.completed", { response }],
      ];
      await route.fulfill({
        status: 200,
        headers: { "content-type": "text/event-stream" },
        body: events.map(([type, data], index) =>
          `id: ${payload.turn_id}:${index + 1}\nevent: ${type}\ndata: ${JSON.stringify(data)}\n\n`,
        ).join(""),
      });
    });
    await page.goto("/");
    await page.getByLabel("Message your concierge").fill("I would like to plan dinner");
    await page.getByRole("button", { name: "Send message" }).click();
    const panel = page.locator(".selection-panel");
    await expect(panel.getByRole("heading", { name: "Dining details" })).toBeVisible();
    await expect(panel).toContainText("does not create a booking");
    if (testInfo.project.name === "chromium") {
      const screenshotDirectory = testInfo.outputPath("screenshots");
      mkdirSync(screenshotDirectory, { recursive: true });
      await panel.screenshot({ path: join(screenshotDirectory, "selection-form-chromium.png") });
    }
    const originalViewport = page.viewportSize();
    for (const width of [320, 375, 390, 430, 768, 1024, 1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      const panelBounds = await panel.boundingBox();
      expect(panelBounds, `selection form should remain visible at ${width}px`).not.toBeNull();
      expect(panelBounds.x).toBeGreaterThanOrEqual(0);
      expect(panelBounds.x + panelBounds.width).toBeLessThanOrEqual(width + 1);
    }
    if (originalViewport) await page.setViewportSize(originalViewport);
    const date = panel.getByLabel("Date");
    await panel.getByRole("button", { name: "Review selections" }).click();
    expect(await date.evaluate((input) => input.validity.valueMissing)).toBe(true);
    await date.fill("2027-01-15");
    await panel.getByLabel("Time").fill("18:30");
    await panel.getByLabel("Quantity").fill("2");
    await panel.getByLabel("Party size").fill("4");
    await panel.getByLabel("Dining preference").selectOption("patio");
    await panel.getByRole("button", { name: "Review selections" }).click();
    await expect(panel.locator(".selection-review")).toContainText("2027-01-15");
    await expect(panel.locator(".selection-review")).toContainText("Patio");
    if (testInfo.project.name === "chromium") {
      const screenshotDirectory = testInfo.outputPath("screenshots");
      await panel.screenshot({ path: join(screenshotDirectory, "selection-review-chromium.png") });
    }
    await panel.getByRole("button", { name: "Edit selections" }).click();
    await expect(panel.getByLabel("Party size")).toHaveValue("4");
    await expect(panel.getByLabel("Dining preference")).toHaveValue("patio");
    await panel.getByRole("button", { name: "Review selections" }).click();
    await panel.getByRole("button", { name: "Cancel selections" }).click();
    await expect(panel).toContainText("Selections cleared. Nothing was sent.");
    expect(messages).toHaveLength(1);
    expect(guestMutations.filter((url) => !url.includes("/intelligent-chat/stream"))).toEqual([]);
  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI: sharing reviewed selections sends one concierge turn without creating a reservation", async ({ page, request }) => {
  await setIntelligentUi(request, true);
  const messages = [];
  const guestMutations = [];
  page.on("request", (browserRequest) => {
    if (browserRequest.url().includes("/api/guest/") && browserRequest.method() !== "GET") {
      guestMutations.push(browserRequest.url());
    }
  });
  try {
    await page.route("**/api/guest/intelligent-chat/stream", async (route) => {
      const payload = route.request().postDataJSON();
      messages.push(payload.message);
      const conversationId = payload.session_id;
      const block = messages.length === 1 ? typedSelectionBlock : { id: "shared", type: "text", content: "Your preferences were shared with the concierge." };
      const response = { schema_version: "1.0", conversation_id: conversationId, turn_id: payload.turn_id, blocks: [block] };
      const events = [
        ["turn.started", { schema_version: "1.0", conversation_id: conversationId, turn_id: payload.turn_id }],
        ["component.ready", { block }],
        ...(block.type === "text" ? [["text.completed", { streamed: false, text: block.content }]] : []),
        ["turn.completed", { response }],
      ];
      await route.fulfill({
        status: 200,
        headers: { "content-type": "text/event-stream" },
        body: events.map(([type, data], index) =>
          `id: ${payload.turn_id}:${index + 1}\nevent: ${type}\ndata: ${JSON.stringify(data)}\n\n`,
        ).join(""),
      });
    });
    await page.goto("/");
    await page.getByLabel("Message your concierge").fill("Plan dinner");
    await page.getByRole("button", { name: "Send message" }).click();
    const panel = page.locator(".selection-panel");
    await panel.getByLabel("Date").fill("2027-01-15");
    await panel.getByLabel("Time").fill("18:30");
    await panel.getByLabel("Quantity").fill("2");
    await panel.getByLabel("Party size").fill("4");
    await panel.getByLabel("Dining preference").selectOption("patio");
    await panel.getByRole("button", { name: "Review selections" }).click();
    await panel.getByRole("button", { name: "Share with concierge" }).click();
    await expect(page.locator(".message-row.assistant .message-text").last()).toContainText("shared with the concierge");
    expect(messages).toHaveLength(2);
    expect(messages[1]).toContain("Date: 2027-01-15");
    expect(messages[1]).toContain("Dining preference: Patio");
    expect(messages[1]).toContain("not a booking or service request");
    expect(guestMutations.filter((url) => !url.includes("/intelligent-chat/stream"))).toEqual([]);
  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI: service requests wait for explicit confirmation and backend verification", async ({ page, request }) => {
  await ensureGuestData(request);
  await setIntelligentUi(request, true);
  try {
    await page.goto("/");
    await page.getByLabel("Message your concierge").fill("Please send two towels to my room");
    await page.getByRole("button", { name: "Send message" }).click();
    const review = page.locator(".request-review");
    await expect(review).toContainText("Towels");
    const confirmResponse = page.waitForResponse((response) =>
      new URL(response.url()).pathname === "/api/guest/actions/confirm" && response.request().method() === "POST",
    );
    await review.getByRole("button", { name: "Confirm request" }).click();
    const confirmed = await confirmResponse;
    expect(confirmed.status()).toBe(200);
    expect((await confirmed.json()).status).toBe("created");
    await expect(page.locator(".verified-confirmation")).toContainText("Your request has been sent");

    const confirmationPosts = [];
    page.on("request", (requestEvent) => {
      if (new URL(requestEvent.url()).pathname === "/api/guest/actions/confirm" && requestEvent.method() === "POST") {
        confirmationPosts.push(requestEvent);
      }
    });
    let confirmedServiceRequests = 0;
    for (const [message, expectedService] of [
      ["Can I have two extra pillows?", "Extra Pillow"],
      ["Could you bring an extra pillow?", "Extra Pillow"],
      ["Please arrange housekeeping for my room", "Housekeeping Visit"],
    ]) {
      await page.getByLabel("Message your concierge").fill(message);
      await page.getByRole("button", { name: "Send message" }).click();
      const requestReview = page.locator(".request-review");
      await expect(requestReview).toContainText(expectedService);
      expect(confirmationPosts).toHaveLength(confirmedServiceRequests);
      await expect(page.locator(".verified-confirmation")).toHaveCount(confirmedServiceRequests + 1);
      const serviceConfirmResponse = page.waitForResponse((response) =>
        new URL(response.url()).pathname === "/api/guest/actions/confirm" && response.request().method() === "POST",
      );
      await requestReview.getByRole("button", { name: "Confirm request" }).click();
      const serviceConfirmed = await serviceConfirmResponse;
      expect(serviceConfirmed.status()).toBe(200);
      expect((await serviceConfirmed.json()).status).toBe("created");
      confirmedServiceRequests += 1;
      await expect(page.locator(".verified-confirmation")).toHaveCount(confirmedServiceRequests + 1);
      await expect(page.locator(".verified-confirmation").last()).toContainText("Your request has been sent");
    }

  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI: server-side rollback restores legacy and query parameters cannot enable v2", async ({ page, request }) => {
  await setIntelligentUi(request, true);
  try {
    await page.goto("/");
    await expect(page.locator("#app-shell")).toBeVisible();
    await setIntelligentUi(request, false);
    await page.reload();
    await expect(page.locator("#concierge-shell")).toBeVisible();
    await expect(page.locator("link[rel='stylesheet']")).toHaveAttribute("href", /\/static\/styles\.css/);
    await page.goto("/?intelligent_ui=1");
    await expect(page.locator("#concierge-shell")).toBeVisible();
    await expect(page.locator("#app-shell")).toHaveCount(0);
  } finally {
    await setIntelligentUi(request, false);
  }
});

// --- 8. Mobile layout ---

test("guest: requested desktop, tablet, and mobile widths have no overflow or footer overlap", async ({ page }) => {
  await page.goto("/");
  for (const width of [375, 390, 430, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const metrics = await page.evaluate(() => {
      const composer = document.querySelector("#composer-form").getBoundingClientRect();
      const navElement = document.querySelector(".experience-configured-navigation:not([hidden]), #guest-bottom-nav:not([hidden])");
      const nav = navElement?.getBoundingClientRect() || { top: window.innerHeight, bottom: window.innerHeight };
      return {
        bodyWidth: document.body.scrollWidth,
        viewportWidth: window.innerWidth,
        composerBottom: composer.bottom,
        navTop: nav.top,
        navBottom: nav.bottom,
      };
    });
    expect(metrics.bodyWidth, `body overflowed at ${width}px`).toBeLessThanOrEqual(width);
    expect(metrics.composerBottom, `composer overlaps navigation at ${width}px`).toBeLessThanOrEqual(metrics.navTop + 1);
    expect(metrics.navBottom, `navigation escaped the viewport at ${width}px`).toBeLessThanOrEqual(900);
  }
});

test("guest: mobile layout shows all core elements", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/");

  await expect(page.locator("#home-view")).toBeVisible();
  await expect(page.locator("#home-name")).toHaveText("How can I help with your stay today?");
  await expect(page.getByLabel("Ask your concierge")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
});

test("guest: composer input uses the available width", async ({ page }) => {
  await page.goto("/");
  const sizes = await page.locator("#composer-form").evaluate((form) => {
    const input = form.querySelector("textarea");
    return { form: form.getBoundingClientRect().width, input: input.getBoundingClientRect().width };
  });
  expect(sizes.input).toBeGreaterThan(sizes.form * 0.6);
});

// --- 9. Guest document upload is not exposed ---

test("guest: document upload control is not exposed", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Upload a document" })).toHaveCount(0);
  await expect(page.locator("#upload-input")).toHaveCount(0);
});

// --- 10. Dark mode (if supported) ---

test("guest: dark mode renders without errors", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");

  await expect(page.locator("#home-view")).toBeVisible();
  await expect(page.getByLabel("Ask your concierge")).toBeVisible();
});

// --- 11. No console errors ---

test("guest: no console errors on load", async ({ page }) => {
  const errors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(err.message));

  await page.goto("/");
  await page.waitForLoadState("networkidle");

  expect(errors).toEqual([]);
});

test("admin: no console errors on load", async ({ page }) => {
  const errors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(err.message));

  const login = await page.request.post("/api/admin/auth/login", {
    data: { username: "admin", password: "PlaywrightOnly-Admin-123!", remember_me: false },
  });
  expect(login.ok()).toBeTruthy();
  await page.goto("/admin");
  await page.waitForLoadState("networkidle");

  expect(errors).toEqual([]);
});

test("Intelligent UI regression: composer clears on accepted send and retries do not duplicate messages", async ({ page, request }) => {
  await setIntelligentUi(request, true);
  const sent = [];
  try {
    await page.route("**/api/guest/intelligent-chat/stream", async (route) => {
      const payload = route.request().postDataJSON();
      sent.push(payload);
      if (payload.message === "hi") await new Promise((resolve) => setTimeout(resolve, 250));
      if (payload.message === "retry safely" && sent.filter((item) => item.message === payload.message).length === 1) {
        await route.fulfill({ status: 502, contentType: "application/json", body: JSON.stringify({ detail: "Temporary test outage." }) });
        return;
      }
      const answer = payload.message === "hi" ? "Hello! How can I help with your stay?" : `Received: ${payload.message}`;
      await route.fulfill({ status: 200, headers: { "content-type": "text/event-stream" }, body: streamEvents(payload, [{ id: `answer-${sent.length}`, type: "text", content: answer }], answer) });
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    const failedResponses = [];
    const startupConsole = [];
    page.on("console", (message) => { if (message.type() === "error") startupConsole.push(message.text()); });
    page.on("response", (response) => {
      if (response.status() >= 400) failedResponses.push(`${response.status()} ${new URL(response.url()).pathname}`);
    });
    await page.goto("/");
    try { await waitForGuestSession(page); }
    catch (error) { throw new Error(`${error.message} (${failedResponses.join(", ")})`); }
    await expect(page.locator("#app-shell"), `Guest app startup responses: ${failedResponses.join(", ")}; console: ${startupConsole.join(" | ")}`).toBeVisible();

    const composer = page.getByLabel("Message your concierge");
    await composer.fill("hi");
    await composer.press("Enter");
    await expect(composer).toHaveValue("");
    await composer.fill("second question");
    await expect(page.getByRole("button", { name: "Send message" })).toBeDisabled();
    await expect(page.locator(".message-row.assistant .message-text").last()).toContainText("Hello!");
    await expect(composer).toHaveValue("second question");
    await expect(page.locator(".message-row.guest .message-text", { hasText: "hi" })).toHaveCount(1);

    const aligned = await page.evaluate(() => {
      const workspace = document.querySelector("#conversation-workspace").getBoundingClientRect();
      const assistant = document.querySelector(".message-row.assistant").getBoundingClientRect();
      const guest = document.querySelector(".message-row.guest").getBoundingClientRect();
      return { workspaceLeft: workspace.left, workspaceRight: workspace.right, assistantLeft: assistant.left, guestRight: guest.right };
    });
    expect(Math.abs(aligned.assistantLeft - aligned.workspaceLeft)).toBeLessThanOrEqual(2);
    expect(aligned.guestRight).toBeLessThanOrEqual(aligned.workspaceRight + 1);
    expect(aligned.guestRight).toBeGreaterThan((aligned.workspaceLeft + aligned.workspaceRight) / 2);

    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.locator(".message-row.guest .message-text")).toHaveCount(2);
    await expect(page.locator(".message-row.assistant .message-text")).toHaveCount(2);
    const messageGap = await page.evaluate(() => {
      const rows = [...document.querySelectorAll(".message-row")];
      return rows[1].getBoundingClientRect().top - rows[0].getBoundingClientRect().bottom;
    });
    expect(messageGap).toBeGreaterThanOrEqual(0);
    expect(messageGap).toBeLessThanOrEqual(28);

    await composer.fill("composed text");
    await composer.evaluate((input) => {
      input.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true }));
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", keyCode: 229, isComposing: true, bubbles: true }));
    });
    await expect(composer).toHaveValue("composed text");
    expect(sent).toHaveLength(2);
    await composer.evaluate((input) => input.dispatchEvent(new CompositionEvent("compositionend", { bubbles: true })));

    await composer.fill("retry safely");
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.locator(".error-panel").last()).toContainText("Temporary test outage");
    await expect(composer).toHaveValue("retry safely");
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.locator(".message-row.guest .message-text", { hasText: "retry safely" })).toHaveCount(1);
    const retryTurns = sent.filter((item) => item.message === "retry safely").map((item) => item.turn_id);
    expect(retryTurns).toHaveLength(2);
    expect(retryTurns[0]).toBe(retryTurns[1]);

    await composer.fill("unsent draft");
    await page.getByRole("button", { name: "Start a new private conversation" }).click();
    await expect(page.locator("#welcome")).toBeVisible();
    await expect(composer).toHaveValue("");
  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI keeps the current session usable when a replacement cannot start", async ({ page, request }) => {
  await setIntelligentUi(request, true);
  try {
    await page.goto("/");
    const oldSession = await waitForGuestSession(page);
    let endCalls = 0;
    await page.route("**/api/session/end", async (route) => {
      endCalls += 1;
      await route.continue();
    });
    await page.route("**/api/session/start", (route) => route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Synthetic session-start outage" }),
    }));
    await page.getByRole("button", { name: "Start a new private conversation" }).click();
    await expect(page.locator("#conversation-status-copy")).toContainText("current conversation remains available");
    expect(endCalls).toBe(0);
    expect(await page.evaluate(() => sessionStorage.getItem("concierge-v2-session-id"))).toBe(oldSession);
    const composer = page.getByLabel("Message your concierge");
    await composer.fill("Is my conversation still available?");
    await expect(page.getByRole("button", { name: "Send message" })).toBeEnabled();
    const history = await page.evaluate(async (id) => (await fetch("/api/guest/intelligent-history", {
      headers: { "X-Concierge-Session": id },
    })).status, oldSession);
    expect(history).toBe(200);
  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI does not replace server history with an empty chat during a transient outage", async ({ page, request }) => {
  await setIntelligentUi(request, true);
  try {
    await page.goto("/");
    const sessionId = await waitForGuestSession(page);
    await page.route("**/api/guest/intelligent-history", (route) => route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Synthetic history outage" }),
    }));
    await page.reload();
    await expect(page.locator("#startup-error")).toBeVisible();
    await expect(page.locator("#app-shell")).toBeHidden();
    expect(await page.evaluate(() => sessionStorage.getItem("concierge-v2-session-id"))).toBe(sessionId);
    await page.unroute("**/api/guest/intelligent-history");
    await page.getByRole("button", { name: "Reload" }).click();
    await expect(page.locator("#app-shell")).toBeVisible();
    expect(await page.evaluate(() => sessionStorage.getItem("concierge-v2-session-id"))).toBe(sessionId);
  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI regression: restaurant menu stays above the persistent composer at phone, tablet, and desktop sizes", async ({ page, request }, testInfo) => {
  await setIntelligentUi(request, true);
  const restaurant = {
    id: "regression-restaurant", type: "restaurant", title: "Luna Test Dining", subtitle: "All-day dining",
    description: "A regression restaurant card with a published menu.", resource_id: "regression-restaurant",
    image_url: "https://images.example.test/restaurant.svg", menu_available: true, policies: [], source_ids: [],
  };
  let releaseImage;
  let notifyImageRequest;
  const imageGate = new Promise((resolve) => { releaseImage = resolve; });
  const imageRequested = new Promise((resolve) => { notifyImageRequest = resolve; });
  try {
    await page.route("**/api/guest/intelligent-chat/stream", async (route) => {
      const payload = route.request().postDataJSON();
      const block = { id: "restaurant-cards", type: "card_collection", title: "Dining options", cards: [restaurant] };
      const body = streamEvents(payload, [block]);
      await route.fulfill({ status: 200, headers: { "content-type": "text/event-stream" }, body });
    });
    await page.route("**/api/guest/restaurants/regression-restaurant/menus", (route) => route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ menus: [{ name: "Dinner", meal_period: "Evening", source_ids: [], items: [{ name: "Test noodles", description: "A menu item for layout verification.", source_ids: [] }] }] }),
    }));
    await page.route("https://images.example.test/restaurant.svg", async (route) => {
      notifyImageRequest();
      await imageGate;
      await route.fulfill({
        status: 200, contentType: "image/svg+xml",
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="100"><rect width="160" height="100" fill="#d8e6dc"/><circle cx="80" cy="50" r="24" fill="#315f50"/></svg>',
      });
    });
    await page.goto("/");
    await waitForGuestSession(page);
    await page.getByLabel("Message your concierge").fill("Where can I have dinner?");
    await page.getByRole("button", { name: "Send message" }).click();
    const card = page.locator(".entity-card").filter({ hasText: "Luna Test Dining" });
    await expect(card).toBeVisible();
    await imageRequested;
    const cardTitleTopBeforeImage = await card.locator("h3").evaluate((title) => title.getBoundingClientRect().top);
    releaseImage();
    await expect(card.locator("img")).toHaveJSProperty("naturalWidth", 160);
    const cardTitleTopAfterImage = await card.locator("h3").evaluate((title) => title.getBoundingClientRect().top);
    expect(Math.abs(cardTitleTopAfterImage - cardTitleTopBeforeImage)).toBeLessThanOrEqual(1);
    await card.getByRole("button", { name: "View published menu" }).click();
    await expect(card.locator(".menu-details")).toContainText("Test noodles");

    const screenshots = testInfo.outputPath("chat-regression-screenshots");
    if (testInfo.project.name === "chromium") mkdirSync(screenshots, { recursive: true });
    for (const viewport of [
      { width: 390, height: 844, label: "mobile" },
      { width: 768, height: 1024, label: "tablet" },
      { width: 1440, height: 900, label: "desktop" },
    ]) {
      await page.setViewportSize(viewport);
      await card.locator(".menu-details").scrollIntoViewIfNeeded();
      const geometry = await page.evaluate(() => ({
        width: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
        contentBottom: document.querySelector(".menu-details").getBoundingClientRect().bottom,
        composerTop: document.querySelector(".composer-dock").getBoundingClientRect().top,
        dockBottom: document.querySelector(".composer-dock").getBoundingClientRect().bottom,
        viewportBottom: window.innerHeight,
      }));
      expect(geometry.width).toBeLessThanOrEqual(viewport.width);
      expect(geometry.contentBottom).toBeLessThanOrEqual(geometry.composerTop);
      expect(geometry.dockBottom).toBeLessThanOrEqual(geometry.viewportBottom);
      if (testInfo.project.name === "chromium") await page.screenshot({ path: join(screenshots, `restaurant-${viewport.label}.png`) });
    }
  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI regression: long chat keeps its scroll anchor while a response changes", async ({ page, request }) => {
  await setIntelligentUi(request, true);
  let slowResponseStarted;
  const slowResponse = new Promise((resolve) => { slowResponseStarted = resolve; });
  try {
    await page.route("**/api/guest/intelligent-chat/stream", async (route) => {
      const payload = route.request().postDataJSON();
      const answer = `Answer for ${payload.message}. ${"More hotel information. ".repeat(45)}`;
      if (payload.message === "follow up") {
        slowResponseStarted();
        await new Promise((resolve) => setTimeout(resolve, 450));
      }
      await route.fulfill({ status: 200, headers: { "content-type": "text/event-stream" }, body: streamEvents(payload, [{ id: `answer-${payload.turn_id}`, type: "text", content: answer }]) });
    });
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/");
    const composer = page.getByLabel("Message your concierge");
    for (let index = 1; index <= 8; index += 1) {
      await composer.fill(`question ${index}`);
      await page.getByRole("button", { name: "Send message" }).click();
      await expect(page.locator(".message-row.assistant .message-text").last()).toContainText(`Answer for question ${index}`);
    }
    const workspace = page.locator("#conversation-workspace");
    await expect.poll(() => workspace.evaluate((node) => node.scrollHeight > node.clientHeight)).toBeTruthy();
    await workspace.evaluate((node) => {
      // Make the test's starting anchor exact despite the UI's smooth-scroll styling.
      node.style.scrollBehavior = "auto";
      node.scrollTop = 100;
    });
    await expect.poll(() => workspace.evaluate((node) => node.scrollTop)).toBe(100);
    const previousTop = await workspace.evaluate((node) => node.scrollTop);
    await composer.fill("follow up");
    await page.getByRole("button", { name: "Send message" }).click();
    await slowResponse;
    await expect(workspace).toHaveJSProperty("scrollTop", previousTop);
    await expect(page.locator(".loading-line")).toBeVisible();
  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI regression: expired chat keeps failed text and starts a fresh session only on request", async ({ page, request }) => {
  await setIntelligentUi(request, true);
  let streamCount = 0;
  try {
    await page.route("**/api/guest/intelligent-chat/stream", async (route) => {
      streamCount += 1;
      await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Concierge session expired." }) });
    });
    await page.goto("/");
    await waitForGuestSession(page);
    const oldSession = await page.evaluate(() => sessionStorage.getItem("concierge-v2-session-id"));
    const composer = page.getByLabel("Message your concierge");
    await composer.fill("hi");
    await composer.press("Enter");
    await expect(page.locator(".message-row.guest .message-text", { hasText: "hi" })).toHaveCount(1);
    await expect(page.locator(".error-panel").last()).toContainText("session has expired");
    await expect(page.locator(".error-panel").last().getByRole("button", { name: "Start a new chat" })).toBeVisible();
    await expect(composer).toHaveValue("hi");
    await expect(page.locator("#send-button")).toBeDisabled();

    await page.locator(".error-panel").last().getByRole("button", { name: "Start a new chat" }).click();
    await expect(page.locator("#welcome")).toBeVisible();
    await expect(composer).toHaveValue("");
    const newSession = await page.evaluate(() => sessionStorage.getItem("concierge-v2-session-id"));
    expect(newSession).toBeTruthy();
    expect(newSession).not.toBe(oldSession);
    expect(streamCount).toBe(1);
  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI regression: a stale saved session is not silently resumed as a new session", async ({ page, request }) => {
  await setIntelligentUi(request, true);
  let startCalls = 0;
  try {
    await page.addInitScript(() => {
      sessionStorage.setItem("concierge-v2-session-id", "expired-session-from-old-browser-state");
      sessionStorage.setItem("concierge-v2-property-id", "e2e-property");
    });
    await page.route("**/api/session/resume", (route) => route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Concierge session expired." }) }));
    await page.on("request", (browserRequest) => {
      if (browserRequest.url().endsWith("/api/session/start")) startCalls += 1;
    });
    await page.goto("/");
    await expect(page.locator(".error-panel")).toContainText("session has expired");
    await expect(page.locator(".error-panel").getByRole("button", { name: "Start a new chat" })).toBeVisible();
    expect(startCalls).toBe(0);
    await page.locator(".error-panel").getByRole("button", { name: "Start a new chat" }).click();
    await expect(page.locator("#welcome")).toBeVisible();
    expect(startCalls).toBe(1);
  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI regression: controlled idle expiry preserves the unsent message and explicit recovery works", async ({ page, request }) => {
  await setIntelligentUi(request, true);
  try {
    await page.goto("/");
    await waitForGuestSession(page);
    const oldSession = await page.evaluate(() => sessionStorage.getItem("concierge-v2-session-id"));
    await updateGuestSessionClock(page, oldSession, "idle_expired");
    const composer = page.getByLabel("Message your concierge");
    await composer.fill("hi");
    await composer.press("Enter");
    await expect(page.locator(".error-panel").last()).toContainText("session has expired");
    await expect(composer).toHaveValue("hi");
    await page.locator(".error-panel").last().getByRole("button", { name: "Start a new chat" }).click();
    await expect(page.locator("#welcome")).toBeVisible();
    await expect(composer).toHaveValue("");
    expect(await page.evaluate(() => sessionStorage.getItem("concierge-v2-session-id"))).not.toBe(oldSession);
  } finally {
    await setIntelligentUi(request, false);
  }
});

test("Intelligent UI regression: permitted activity slides credential expiry and revoked sessions cannot renew", async ({ page, request }) => {
  await setIntelligentUi(request, true);
  try {
    await page.goto("/");
    await waitForGuestSession(page);
    const sessionId = await page.evaluate(() => sessionStorage.getItem("concierge-v2-session-id"));
    const nearExpiry = await updateGuestSessionClock(page, sessionId, "near_expiry");
    const historyStatus = await page.evaluate(async (id) => (await fetch("/api/guest/intelligent-history", {
      headers: { "X-Concierge-Session": id },
    })).status, sessionId);
    expect(historyStatus).toBe(200);
    const renewed = await updateGuestSessionClock(page, sessionId, "read");
    expect(renewed.guest_token_expires_at).toBeGreaterThan(nearExpiry.guest_token_expires_at + 60);

    await updateGuestSessionClock(page, sessionId, "revoked");
    const clientId = await page.evaluate(() => localStorage.getItem("concierge-client-id"));
    const resumeStatus = await page.evaluate(async ({ id, client }) => (await fetch("/api/session/resume", {
      method: "POST", headers: { "Content-Type": "application/json", "X-Concierge-Session": id },
      body: JSON.stringify({ session_id: id, client_id: client }),
    })).status, { id: sessionId, client: clientId });
    expect(resumeStatus).toBe(401);
    const stillRevoked = await updateGuestSessionClock(page, sessionId, "read");
    expect(stillRevoked.guest_token_revoked_at).toBeGreaterThan(0);
  } finally {
    await setIntelligentUi(request, false);
  }
});
