import { expect, test } from "@playwright/test";

const csrfByRequest = new WeakMap();

async function guestNavigation(page) {
  const configured = page.locator(".experience-configured-navigation");
  await expect(configured).toBeVisible();
  return configured;
}

async function openHotelMenu(page) {
  await page.locator('button[aria-label="Open hotel menu"]:visible').first().click();
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
  const recommendations = await (await request.get(`/api/admin/properties/${propertyId}/recommendations`)).json();
  if (!recommendations.recommendations.some((item) => item.name === "Fixture Bistro")) {
    await request.put(`/api/admin/properties/${propertyId}/recommendations`, {
      headers: { "X-CSRF-Token": csrf },
      data: { data: { name: "Fixture Bistro", category: "Dining", address: "1 Example Road", map_url: "https://maps.example/fixture", description: "Synthetic test recommendation.", enabled: true } },
    });
  }
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

  const detailsBtn = page.locator(".recommendation-card").first().getByRole("button", { name: "Details" });
  await detailsBtn.click();
  const details = page.locator(".recommendation-card").first().locator("p");
  await expect(details).toBeVisible();
  await expect(details).toHaveText("Synthetic test recommendation.");
  await expect(detailsBtn).toHaveText("Hide details");
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
  ["Privacy", "Chat context stays in this open session"],
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
