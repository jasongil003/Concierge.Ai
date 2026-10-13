import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { prepareGuestFixture } from "./support.js";

const VIEWPORTS = [
  { width: 320, height: 720 },
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
];

const VIEWS = [
  ["home", "#home-view"],
  ["explore", "#explore-view"],
  ["requests", "#requests-view"],
  ["stay", "#stay-view"],
  ["concierge", "#concierge-view"],
];

test.beforeEach(async ({ request }) => prepareGuestFixture(request));

async function publishSyntheticGuestPage(request) {
  const login = await request.post("/api/admin/auth/login", {
    data: { username: "admin", password: "PlaywrightOnly-Admin-123!", remember_me: false },
  });
  expect(login.ok()).toBeTruthy();
  const csrf = (await login.json()).user.csrf_token;
  const propertiesResponse = await request.get("/api/admin/properties");
  expect(propertiesResponse.ok()).toBeTruthy();
  const propertyId = (await propertiesResponse.json()).properties[0].property_id;
  const designResponse = await request.get(`/api/admin/properties/${propertyId}/design`);
  expect(designResponse.ok()).toBeTruthy();
  const current = await designResponse.json();
  const config = structuredClone(current.published);
  const corePages = [
    {
      id: "home",
      type: "guest_home",
      version: 1,
      name: "Home",
      slug: "/",
      enabled: true,
      navigation: true,
      sections: [
        {
          id: "synthetic-home-hero",
          type: "hero",
          title: "Welcome",
          enabled: true,
          order: 0,
          properties: {},
        },
        {
          id: "synthetic-home-actions",
          type: "quick_actions",
          title: "A good place to begin",
          enabled: true,
          order: 1,
          properties: {},
        },
        {
          id: "synthetic-home-dining",
          type: "restaurant",
          title: "Dining at the property",
          enabled: true,
          order: 2,
          properties: { source: "restaurants", limit: 2, columns: 2 },
        },
        {
          id: "synthetic-home-facilities",
          type: "amenities",
          title: "Places to pause",
          enabled: true,
          order: 3,
          properties: { source: "facilities", limit: 2, columns: 2 },
        },
      ],
    },
    ...[
      ["explore", "Explore"],
      ["requests", "Requests"],
      ["stay", "My Stay"],
      ["concierge", "Concierge"],
    ].map(([id, name]) => ({
      id,
      type: "guest_page",
      version: 1,
      name,
      slug: `/${id}`,
      enabled: true,
      navigation: true,
      sections: [],
    })),
  ];
  config.pages = [
    ...corePages,
    {
    id: "page-guest-guide",
    type: "guest_page",
    version: 1,
    name: "Guest Guide",
    slug: "/guest-guide",
    enabled: true,
    navigation: false,
    sections: [
      {
        id: "synthetic-guide-hero",
        type: "hero",
        enabled: true,
        order: 0,
        properties: {
          eyebrow: "Guest guide",
          headline: "A thoughtful stay, at your own pace.",
          description: "This synthetic page verifies a published, property-configured guest view.",
          buttons: [],
        },
      },
      {
        id: "synthetic-guide-copy",
        type: "text",
        enabled: true,
        order: 1,
        properties: { content: "Only synthetic review content appears on this page." },
      },
    ],
    },
  ];
  config.navigation = [
    ["home", "Home", "home"],
    ["explore", "Explore", "explore"],
    ["requests", "Requests", "requests"],
    ["stay", "My Stay", "stay"],
    ["concierge", "Concierge", "concierge"],
  ].map(([page_id, label, icon]) => ({ page_id, label, icon, enabled: true }));
  const headers = { "X-CSRF-Token": csrf };
  const save = await request.put(`/api/admin/properties/${propertyId}/design/draft`, {
    headers,
    data: { config, expected_revision: current.revision },
  });
  expect(save.ok(), await save.text()).toBeTruthy();
  const saved = await save.json();
  const publish = await request.post(`/api/admin/properties/${propertyId}/design/publish`, {
    headers,
    data: { expected_revision: saved.revision },
  });
  expect(publish.ok(), await publish.text()).toBeTruthy();

  return async () => {
    const latestResponse = await request.get(`/api/admin/properties/${propertyId}/design`);
    expect(latestResponse.ok()).toBeTruthy();
    const latest = await latestResponse.json();
    const restoreDraft = await request.put(`/api/admin/properties/${propertyId}/design/draft`, {
      headers,
      data: { config: current.published, expected_revision: latest.revision },
    });
    expect(restoreDraft.ok(), await restoreDraft.text()).toBeTruthy();
    const restored = await restoreDraft.json();
    const restorePublish = await request.post(`/api/admin/properties/${propertyId}/design/publish`, {
      headers,
      data: { expected_revision: restored.revision },
    });
    expect(restorePublish.ok(), await restorePublish.text()).toBeTruthy();
  };
}

async function waitForGuestNavigation(page) {
  await expect.poll(async () => (
    await page.locator(".experience-configured-navigation").isVisible()
      || await page.locator("#guest-bottom-nav").isVisible()
  )).toBe(true);
}

async function waitForSyntheticHomeContent(page) {
  await expect(page.locator("#guest-experience-page .experience-restaurant")).toContainText("The Courtyard");
  await expect(page.locator("#guest-experience-page .experience-amenities")).toContainText("Wellness facilities");
}

test("capture configured synthetic guest views across the responsive matrix", async ({ page, request }, testInfo) => {
  const outputDirectory = process.env.GUEST_UI_AUDIT_DIR;
  test.skip(!outputDirectory, "Set GUEST_UI_AUDIT_DIR to retain a before/after screenshot matrix.");
  test.skip(testInfo.project.name !== "chromium", "The width matrix runs once in Chromium.");
  test.setTimeout(180_000);
  const restoreDesign = await publishSyntheticGuestPage(request);
  try {

  await page.addInitScript(() => {
    localStorage.setItem("concierge-intro-seen", "1");
    localStorage.removeItem("concierge-draft");
    localStorage.removeItem("concierge-accessibility");
  });
  await page.route("**/api/guest/intro**", (route) => route.fulfill({
    json: { mode: "none", first_visit_only: true, allow_skip: true },
  }));
  await page.route("**/api/hotel", async (route) => {
    const response = await route.fetch();
    const profile = await response.json();
    profile.name = "Synthetic House";
    profile.concierge_name = "Guest Relations";
    profile.design = {
      ...(profile.design || {}),
      branding: {
        ...(profile.design?.branding || {}),
        hotelName: "Synthetic House",
        conciergeName: "Guest Relations",
      },
      welcome: {
        greeting: "Welcome back",
        headline: "A considered stay, from the moment you arrive.",
        description: "Discover what this property has shared, or ask your concierge for help.",
      },
      theme: {
        ...(profile.design?.theme || {}),
        background: "#f6f3ed",
        surface: "#fffefa",
        accent: "#796343",
        textPrimary: "#292720",
        textSecondary: "#625f56",
        backgroundImageUrl: "/guest-audit-hero.svg",
      },
      suggestions: [
        { label: "Explore property information", prompt: "What information is available about this property?", enabled: true, order: 0 },
        { label: "Browse guest services", prompt: "What guest services are currently available?", enabled: true, order: 1 },
        { label: "Ask about my stay", prompt: "What information is available about my stay?", enabled: true, order: 2 },
      ],
    };
    await route.fulfill({ response, json: profile });
  });
  await page.route("**/api/guest/home", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      greeting: "Welcome back",
      stay: { status: "checked_in" },
      primary_card: null,
      cards: [
        { type: "facility", title: "Wellness facilities", subtitle: "Published property information", description: "A synthetic facility record used only for this browser review." },
        { type: "restaurant", title: "The Courtyard", subtitle: "Property dining", description: "A synthetic dining record used only for this browser review.", restaurant_id: "audit-courtyard" },
      ],
      active_requests: [],
      quick_actions: [
        { label: "Explore", view: "explore" },
        { label: "Requests", view: "requests" },
        { label: "My Stay", view: "stay" },
      ],
      suggested_prompts: [],
      inventory: {
        restaurants: [{ restaurant_id: "audit-courtyard", name: "The Courtyard", cuisine: "Property dining", description: "A synthetic dining record used only for this browser review." }],
        facilities: [{ facility_id: "audit-wellness", name: "Wellness facilities", facility_type: "Facility", description: "A synthetic facility record used only for this browser review." }],
        events: [],
        promotions: [],
        recommendations: [],
        menu_items: [],
      },
    }),
  }));
  await page.route("**/api/guest/service-catalog", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ services: [] }),
  }));
  await page.route("**/api/guest/requests", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ requests: [] }),
  }));
  await page.route("**/guest-audit-hero.svg", (route) => route.fulfill({
    status: 200,
    contentType: "image/svg+xml",
    body: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 560"><defs><linearGradient id="a" x2="0" y2="1"><stop stop-color="#d8c6a8"/><stop offset="1" stop-color="#697970"/></linearGradient></defs><rect width="1200" height="560" fill="url(#a)"/><rect x="520" y="50" width="600" height="420" rx="4" fill="#e8decd"/><rect x="565" y="90" width="510" height="300" fill="#8ca49d"/><path d="M565 310q140-110 265 2t245-4v82H565z" fill="#566f67"/><path d="M520 430h600v40H520z" fill="#b79d78"/><path d="M250 560q25-190 110-230 35 100 15 230m45 0q20-145 94-187 33 86 20 187" fill="#4b5945"/></svg>',
  }));

  const pageErrors = [];
  const failedRequests = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => failedRequests.push(`${request.method()} ${request.url()}`));

  const outputRoot = resolve(outputDirectory);
  mkdirSync(outputRoot, { recursive: true });
  await page.goto("/");
  await expect(page.locator("#home-hero")).toBeVisible();
  await expect(page.locator("#hotel-name")).toHaveText("Synthetic House");
  await waitForGuestNavigation(page);
  await waitForSyntheticHomeContent(page);

  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.locator("#home-view")).toBeVisible();
    await waitForGuestNavigation(page);
    await waitForSyntheticHomeContent(page);
    for (const [view, selector] of VIEWS) {
      await expect(page.locator(selector)).toBeVisible();
      if (view === "explore" && viewport.width > 620) {
        const singleCardLayout = await page.locator("#dining-list").evaluate((list) => ({
          card: list.firstElementChild?.getBoundingClientRect().width || 0,
          list: list.getBoundingClientRect().width,
        }));
        expect(singleCardLayout.card, `single Explore card at ${viewport.width}px`).toBeGreaterThanOrEqual(singleCardLayout.list - 1);
      }
      const dimensions = await page.evaluate(() => ({
        viewport: window.innerWidth,
        document: document.documentElement.scrollWidth,
        body: document.body.scrollWidth,
      }));
      expect(dimensions.document, `${view} at ${viewport.width}px`).toBeLessThanOrEqual(dimensions.viewport + 1);
      expect(dimensions.body, `${view} at ${viewport.width}px`).toBeLessThanOrEqual(dimensions.viewport + 1);
      const viewDirectory = resolve(outputRoot, view);
      mkdirSync(viewDirectory, { recursive: true });
      await page.screenshot({
        path: resolve(viewDirectory, `${viewport.width}.png`),
        fullPage: true,
        animations: "disabled",
        caret: "hide",
      });
      const next = VIEWS[VIEWS.findIndex(([name]) => name === view) + 1];
      if (next) {
        const configuredNav = page.locator(".experience-configured-navigation");
        if (await configuredNav.isVisible()) {
          await configuredNav.locator(`[data-page-id="${next[0]}"]`).click();
        } else {
          await page.locator(`#guest-bottom-nav [data-view="${next[0]}"]`).click();
        }
        await expect(page.locator(next[1])).toBeVisible();
      }
    }

  }

  const publicProfileResponse = await request.get("/api/hotel");
  expect(publicProfileResponse.ok()).toBeTruthy();
  const publicProfile = await publicProfileResponse.json();
  expect(publicProfile.design.pages).toEqual(expect.arrayContaining([
    expect.objectContaining({ id: "page-guest-guide", slug: "/guest-guide", enabled: true }),
  ]));

  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    const directPageResponse = await page.goto("/guest-guide");
    expect(directPageResponse?.status()).toBe(200);
    await expect(page).toHaveURL(/\/guest-guide$/);
    await expect(page.locator("#custom-page-view")).toBeVisible();
    await expect(page.locator("#custom-experience-page h1")).toHaveText("A thoughtful stay, at your own pace.");
    const customPageDimensions = await page.evaluate(() => ({
      viewport: window.innerWidth,
      document: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
    }));
    expect(customPageDimensions.document, `published custom page at ${viewport.width}px`).toBeLessThanOrEqual(viewport.width + 1);
    expect(customPageDimensions.body, `published custom page at ${viewport.width}px`).toBeLessThanOrEqual(viewport.width + 1);
    const customPageDirectory = resolve(outputRoot, "custom-page");
    mkdirSync(customPageDirectory, { recursive: true });
    await page.screenshot({
      path: resolve(customPageDirectory, `${viewport.width}.png`),
      fullPage: true,
      animations: "disabled",
      caret: "hide",
    });
  }

  expect(pageErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
  } finally {
    await restoreDesign();
  }
});
