import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { prepareGuestFixture } from "./support.js";

const EMPTY_HOME = {
  greeting: "Welcome",
  stay: { status: "unverified" },
  primary_card: null,
  cards: [],
  active_requests: [],
  quick_actions: [],
  suggested_prompts: [],
  inventory: { restaurants: [], facilities: [], events: [], promotions: [], recommendations: [], menu_items: [] },
};

const THEMES = [
  {
    name: "warm",
    accent: "#6c5433",
    background: "#f4eee3",
    surface: "#fffdf8",
    textPrimary: "#29251e",
    textSecondary: "#62594b",
  },
  {
    name: "coastal",
    accent: "#345f64",
    background: "#eff5f4",
    surface: "#fbfdfc",
    textPrimary: "#1d292a",
    textSecondary: "#455758",
  },
];

function enableGuestHeader(profile) {
  profile.design.header = { ...(profile.design.header || {}), enabled: true };
  for (const page of profile.design.pages || []) {
    for (const section of page.sections || []) {
      if (section.type === "header") {
        section.enabled = true;
        section.properties = { ...(section.properties || {}), enabled: true };
      }
    }
  }
}

test.beforeEach(async ({ request }) => prepareGuestFixture(request));

async function installEmptyProperty(page, themeSource = THEMES[0], configureProfile = null) {
  await page.addInitScript(() => {
    localStorage.setItem("concierge-intro-seen", "1");
    localStorage.removeItem("concierge-draft");
  });
  await page.route("**/api/guest/intro**", (route) => route.fulfill({
    json: { mode: "none", first_visit_only: true, allow_skip: true },
  }));
  await page.route("**/api/guest/home", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(EMPTY_HOME),
  }));
  await page.route("**/api/guest/service-catalog", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ services: [] }),
  }));
  await page.route("**/api/hotel", async (route) => {
    const response = await route.fetch();
    const profile = await response.json();
    const theme = typeof themeSource === "function" ? themeSource() : themeSource;
    profile.name = "Synthetic House";
    profile.concierge_name = "Guest Relations";
    profile.design = {
      ...(profile.design || {}),
      branding: {
        ...(profile.design?.branding || {}),
        hotelName: "Synthetic House",
        conciergeName: "Guest Relations",
      },
      theme: { ...(profile.design?.theme || {}), ...theme, backgroundImageUrl: "" },
    };
    configureProfile?.(profile);
    await route.fulfill({ response, json: profile });
  });
}

async function openGuestView(page, view) {
  const configuredNavigation = page.locator(".experience-configured-navigation");
  if (await configuredNavigation.isVisible()) {
    await configuredNavigation.locator(`[data-page-id="${view}"]`).click();
    return configuredNavigation.locator(`[data-page-id="${view}"]`);
  }
  const navigation = page.locator(`#guest-bottom-nav [data-view="${view}"]`);
  await navigation.click();
  return navigation;
}

test("empty property keeps an honest home, a direct concierge action, and all five guest views", async ({ page }, testInfo) => {
  await installEmptyProperty(page);
  const emptyCaptureRoot = process.env.GUEST_UI_AUDIT_DIR && testInfo.project.name === "chromium"
    ? resolve(process.env.GUEST_UI_AUDIT_DIR, "empty-property")
    : null;
  if (emptyCaptureRoot) await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  const captureEmptyView = async (view) => {
    if (!emptyCaptureRoot) return;
    mkdirSync(join(emptyCaptureRoot, view), { recursive: true });
    await page.screenshot({ path: join(emptyCaptureRoot, view, "390.png"), fullPage: true });
  };

  await expect(page.locator("#home-view")).toBeVisible();
  await expect(page.locator(".home-discovery-empty")).toContainText("There are no published highlights to show yet");
  await expect(page.locator(".experience-hero button")).toHaveText("Ask your concierge");
  await expect(page.locator(".experience-card-grid")).toHaveCount(0);
  await captureEmptyView("home");

  await page.locator(".experience-hero button").click();
  await expect(page.locator("#concierge-view")).toBeVisible();
  await expect(page.locator("#composer-input")).toBeFocused();
  await expect(page.locator("#suggestion-list button")).toHaveCount(3);
  await captureEmptyView("concierge");

  const stayNavigation = await openGuestView(page, "stay");
  await expect(stayNavigation).toHaveAttribute("aria-current", "page");
  await expect(page.locator("#stay-summary-card")).toContainText("No verified stay linked");
  await captureEmptyView("stay");

  await openGuestView(page, "explore");
  await expect(page.locator("#explore-empty")).toBeVisible();
  await expect(page.locator("#recommendation-list > *")).toHaveCount(0);
  await captureEmptyView("explore");

  await openGuestView(page, "requests");
  await expect(page.locator("#requests-empty")).toBeVisible();
  await expect(page.locator("#request-catalog-empty")).toBeVisible();
  await captureEmptyView("requests");

  const conciergeNavigation = await openGuestView(page, "concierge");
  await expect(conciergeNavigation).toHaveAttribute("aria-current", "page");
  await expect(page.locator("#privacy-note, .privacy-note")).toContainText("Authorized hotel staff can review retained conversations");
  const personalize = page.locator("#personalize-cta");
  await personalize.scrollIntoViewIfNeeded();
  await personalize.click();
  const personalizationDialog = page.getByRole("dialog", { name: "Personalization / Memory" });
  await expect(personalizationDialog).toBeVisible();
  await expect(page.locator("#close-memory-button")).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  expect(await page.evaluate(() => Boolean(document.activeElement?.closest("#memory-modal")))).toBe(true);
  await page.keyboard.press("Tab");
  await expect(page.locator("#close-memory-button")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(personalizationDialog).toBeHidden();
  await expect(personalize).toBeFocused();
});

test("guest dialogs contain focus, make the background inert, and restore the menu trigger", async ({ page }) => {
  await installEmptyProperty(page, THEMES[0], enableGuestHeader);
  await page.route("**/api/guest/zones**", (route) => route.fulfill({
    json: {
      maps: [{ map_id: "synthetic-map", url: "" }],
      zones: [{ zone_id: "lobby", name: "Lobby", geometry: { type: "ellipse", sourceCanvas: { width: 100, height: 100 }, x: 40, y: 40, width: 20, height: 20, mapNumber: "1" } }],
    },
  }));
  await page.route("**/api/guest/facilities", (route) => route.fulfill({
    json: { restaurants: [{ restaurant_id: "synthetic-restaurant", name: "Synthetic Dining", status: "active" }] },
  }));
  await page.goto("/");
  await expect(page.locator("#hotel-name")).toHaveText("Synthetic House");

  const menuTrigger = page.locator(".experience-configured-header .experience-configured-menu");
  const expectBackgroundState = async (inert) => {
    await expect.poll(() => page.locator("#home-view").evaluate((element) => element.inert)).toBe(inert);
    await expect.poll(() => page.locator("#guest-bottom-nav").evaluate((element) => element.inert)).toBe(inert);
  };
  const openMenuAction = async (action) => {
    await menuTrigger.click();
    await page.locator(`[data-menu-action="${action}"]`).click();
  };

  await openMenuAction("memory");
  const memoryDialog = page.locator("#memory-modal");
  await expect(memoryDialog).toBeVisible();
  await expectBackgroundState(true);
  await page.keyboard.press("Shift+Tab");
  expect(await page.evaluate(() => document.activeElement?.closest("#memory-modal") != null)).toBe(true);
  await page.keyboard.press("Escape");
  await expect(memoryDialog).toBeHidden();
  await expect(menuTrigger).toBeFocused();
  await expectBackgroundState(false);

  await openMenuAction("property-map");
  const mapDialog = page.locator("#property-map-modal");
  await expect(mapDialog).toBeVisible();
  await expectBackgroundState(true);
  await page.keyboard.press("Shift+Tab");
  expect(await page.evaluate(() => document.activeElement?.closest("#property-map-modal") != null)).toBe(true);
  await page.keyboard.press("Escape");
  await expect(mapDialog).toBeHidden();
  await expect(menuTrigger).toBeFocused();
  await expectBackgroundState(false);

  await openMenuAction("restaurant-staff");
  const staffDialog = page.locator("#restaurant-staff-dialog");
  await expect(staffDialog).toBeVisible();
  await expect(page.getByRole("dialog", { name: "Talk to Restaurant Staff" })).toBeVisible();
  await expect.poll(() => staffDialog.evaluate((element) => element.matches(":modal"))).toBe(true);
  for (let index = 0; index < 8; index += 1) {
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => document.activeElement?.closest("#restaurant-staff-dialog") != null)).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(staffDialog).toBeHidden();
  await expect(menuTrigger).toBeFocused();
  await expectBackgroundState(false);
});

test("guest dialog load errors stay readable and do not leave the page inert", async ({ page }) => {
  await installEmptyProperty(page, THEMES[0], enableGuestHeader);
  await page.route("**/api/guest/zones**", (route) => {
    const url = new URL(route.request().url());
    return url.searchParams.has("property_id")
      ? route.fulfill({ status: 503, json: { detail: "Synthetic map outage" } })
      : route.fulfill({ json: { maps: [{ map_id: "synthetic-map", url: "" }], zones: [] } });
  });
  await page.route("**/api/guest/facilities", (route) => route.fulfill({
    json: { restaurants: [{ restaurant_id: "synthetic-restaurant", name: "Synthetic Dining", status: "active" }] },
  }));
  await page.route("**/api/guest/personalization", (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Synthetic personalization outage" }),
  }));
  await page.goto("/");
  await expect(page.locator("#hotel-name")).toHaveText("Synthetic House");
  const menuTrigger = page.locator(".experience-configured-header .experience-configured-menu");

  await menuTrigger.click();
  await page.locator('[data-menu-action="memory"]').click();
  await expect(page.locator("#memory-modal")).toBeVisible();
  await expect(page.locator("#memory-status")).toContainText("couldn't load your personalization settings");
  await expect(page.locator("#memory-status")).toHaveAttribute("role", "status");
  await expect.poll(() => page.locator("#home-view").evaluate((element) => element.inert)).toBe(true);
  await page.locator("#close-memory-button").click();
  await expect(page.locator("#memory-modal")).toBeHidden();
  await expect(menuTrigger).toBeFocused();
  await expect.poll(() => page.locator("#home-view").evaluate((element) => element.inert)).toBe(false);

  await menuTrigger.click();
  await page.locator('[data-menu-action="property-map"]').click();
  await expect(page.locator("#property-map-modal")).toBeHidden();
  await expect(page.locator("#toast")).toContainText("Synthetic map outage");
  await expect.poll(() => page.locator("#home-view").evaluate((element) => element.inert)).toBe(false);
});

test("guest session resumes on reload within the current property", async ({ page }) => {
  await installEmptyProperty(page);
  let resumeRequestCount = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/session/resume") resumeRequestCount += 1;
  });
  const sessionStarted = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/session/start" && response.request().method() === "POST"
  );
  await page.goto("/");
  await expect(page.locator("#hotel-name")).toHaveText("Synthetic House");
  expect((await sessionStarted).ok()).toBeTruthy();
  const firstSessionId = await page.evaluate(() => sessionStorage.getItem("concierge-session-id"));
  expect(firstSessionId).toBeTruthy();

  const sessionResumed = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/session/resume" && response.request().method() === "POST"
  );
  await page.reload();
  await expect(page.locator("#hotel-name")).toHaveText("Synthetic House");
  expect((await sessionResumed).ok()).toBeTruthy();
  await expect.poll(() => resumeRequestCount).toBe(1);
  expect(await page.evaluate(() => sessionStorage.getItem("concierge-session-id"))).toBe(firstSessionId);
});

test("guest session from one property is rejected and restarted on another property hostname", async ({ page, request }) => {
  const login = await request.post("/api/admin/auth/login", {
    data: { username: "admin", password: "PlaywrightOnly-Admin-123!", remember_me: false },
  });
  expect(login.ok()).toBeTruthy();
  const csrf = (await login.json()).user.csrf_token;
  const headers = { "X-CSRF-Token": csrf };
  const propertiesResponse = await request.get("/api/admin/properties");
  expect(propertiesResponse.ok()).toBeTruthy();
  const propertyAId = (await propertiesResponse.json()).properties[0].property_id;
  const propertyAResponse = await request.get(`/api/admin/properties/${propertyAId}`);
  expect(propertyAResponse.ok()).toBeTruthy();
  const propertyA = await propertyAResponse.json();
  const originalDomain = propertyA.domain || "";
  const propertyBId = `guest-boundary-${Date.now().toString(36)}`;
  const propertyADomain = `guest-a-${Date.now().toString(36)}.test`;
  const propertyBDomain = `guest-b-${Date.now().toString(36)}.test`;
  const updatePropertyA = await request.put(`/api/admin/properties/${propertyAId}`, {
    headers,
    data: { property_id: propertyAId, hotel_name: propertyA.hotel_name, domain: propertyADomain },
  });
  expect(updatePropertyA.ok(), await updatePropertyA.text()).toBeTruthy();
  let propertyBCreated = false;
  try {
    const createPropertyB = await request.put(`/api/admin/properties/${propertyBId}`, {
      headers,
      data: { property_id: propertyBId, hotel_name: "Synthetic Boundary Bravo", domain: propertyBDomain, timezone: "Asia/Manila" },
    });
    expect(createPropertyB.ok(), await createPropertyB.text()).toBeTruthy();
    propertyBCreated = true;

    const guestDomains = new Set([propertyADomain, propertyBDomain]);
    await page.route("**/*", async (route) => {
      const requestedUrl = new URL(route.request().url());
      if (!guestDomains.has(requestedUrl.hostname)) return route.continue();
      const serverUrl = new URL(requestedUrl);
      serverUrl.hostname = "127.0.0.1";
      const response = await route.fetch({
        url: serverUrl.href,
        headers: { ...(await route.request().allHeaders()), host: `${requestedUrl.hostname}:8092` },
      });
      await route.fulfill({ response });
    });
    await page.goto(`http://${propertyADomain}:8092/`);
    await expect(page.locator("#hotel-name")).toHaveText(propertyA.hotel_name);
    await expect.poll(() => page.evaluate(() => sessionStorage.getItem("concierge-session-id"))).toBeTruthy();
    const propertyASession = await page.evaluate(() => sessionStorage.getItem("concierge-session-id"));
    expect(propertyASession).toBeTruthy();
    const resumeStatuses = [];
    page.on("response", (response) => {
      if (new URL(response.url()).pathname === "/api/session/resume") resumeStatuses.push(response.status());
    });

    const propertyACookies = await page.context().cookies(page.url());
    await page.context().addCookies(propertyACookies.map((cookie) => ({
      name: cookie.name,
      value: cookie.value,
      domain: propertyBDomain,
      path: cookie.path,
      httpOnly: cookie.httpOnly,
      secure: cookie.secure,
      sameSite: cookie.sameSite,
    })));
    await page.addInitScript(({ host, sessionId }) => {
      if (window.location.hostname === host && !sessionStorage.getItem("concierge-session-id")) {
        sessionStorage.setItem("concierge-session-id", sessionId);
      }
    }, { host: propertyBDomain, sessionId: propertyASession });
    await page.goto(`http://${propertyBDomain}:8092/`);
    await expect(page.locator("#hotel-name")).toHaveText("Synthetic Boundary Bravo");
    await expect.poll(() => page.evaluate(() => sessionStorage.getItem("concierge-session-id"))).not.toBe(propertyASession);
    expect(resumeStatuses.some((status) => status === 401 || status === 403)).toBe(true);
  } finally {
    const restoreA = await request.put(`/api/admin/properties/${propertyAId}`, {
      headers,
      data: { property_id: propertyAId, hotel_name: propertyA.hotel_name, domain: originalDomain },
    });
    expect(restoreA.ok(), await restoreA.text()).toBeTruthy();
    if (propertyBCreated) {
      const removeB = await request.delete(`/api/admin/properties/${propertyBId}`, { headers });
      expect(removeB.ok(), await removeB.text()).toBeTruthy();
    }
  }
});

test("configured home keeps a direct concierge action beside property-specific actions", async ({ page }) => {
  await installEmptyProperty(page, THEMES[0], (profile) => {
    const home = profile.design.pages.find((item) => item.id === "home");
    const hero = home.sections.find((section) => section.type === "hero");
    hero.properties.buttons = [{ label: "Browse experiences", style: "secondary", action: { type: "internal_page", page_id: "explore" } }];
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Browse experiences" })).toBeVisible();
  const conciergeAction = page.getByRole("button", { name: "Ask your concierge" });
  await expect(conciergeAction).toBeVisible();
  await conciergeAction.click();
  await expect(page.locator("#concierge-view")).toBeVisible();
});

test("guest layout, touch targets, and privacy text remain usable across requested widths", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The viewport audit runs once in Chromium.");
  await installEmptyProperty(page);
  await page.goto("/");
  await expect(page.locator(".home-discovery-empty")).toBeVisible();

  await page.keyboard.press("Tab");
  const keyboardFocus = await page.evaluate(() => ({
    tag: document.activeElement?.tagName,
    outlineStyle: getComputedStyle(document.activeElement).outlineStyle,
    outlineWidth: getComputedStyle(document.activeElement).outlineWidth,
  }));
  expect(keyboardFocus.tag).not.toBe("BODY");
  expect(keyboardFocus.outlineStyle).not.toBe("none");
  expect(Number.parseFloat(keyboardFocus.outlineWidth)).toBeGreaterThan(0);

  for (const viewport of [
    { width: 320, height: 720 },
    { width: 375, height: 812 },
    { width: 390, height: 844 },
    { width: 430, height: 932 },
    { width: 768, height: 1024 },
    { width: 1024, height: 768 },
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 },
  ]) {
    await page.setViewportSize(viewport);
    const nav = await openGuestView(page, "concierge");
    await expect(nav).toHaveAttribute("aria-current", "page");
    const geometry = await page.evaluate(() => {
      const rect = (element) => {
        const value = element.getBoundingClientRect();
        return { x: value.x, y: value.y, right: value.right, bottom: value.bottom, width: value.width, height: value.height };
      };
      const visible = (element) => {
        const style = getComputedStyle(element);
        const value = element.getBoundingClientRect();
        return style.display !== "none" && style.visibility !== "hidden" && value.width > 0 && value.height > 0;
      };
      const targets = [...document.querySelectorAll("#concierge-view button, #composer-region button, .experience-configured-navigation button, #guest-bottom-nav button")]
        .filter(visible)
        .map((element) => ({ label: element.innerText || element.getAttribute("aria-label") || element.id, ...rect(element) }));
      const rgb = (color) => {
        const srgb = color.match(/color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)/);
        return srgb ? srgb.slice(1, 4).map((channel) => Number(channel) * 255) : color.match(/[\d.]+/g).slice(0, 3).map(Number);
      };
      const luminance = (values) => {
        const linear = values.map((value) => {
          const channel = value / 255;
          return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
        });
        return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
      };
      const note = document.querySelector(".privacy-note");
      const foreground = luminance(rgb(getComputedStyle(note).color));
      const background = luminance(rgb(getComputedStyle(document.querySelector("#concierge-card")).backgroundColor));
      const contrast = (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05);
      const composer = rect(document.querySelector("#composer-region"));
      const navigation = rect(document.querySelector(".experience-configured-navigation") || document.querySelector("#guest-bottom-nav"));
      const conversation = rect(document.querySelector("#concierge-view .conversation-column"));
      const composerInput = rect(document.querySelector("#composer-input"));
      const headerTitle = rect(document.querySelector("#concierge-view .conversation-card-header h2"));
      const headerSubtitle = rect(document.querySelector("#concierge-view .conversation-card-header span"));
      const headerOverlaps = !(headerTitle.right <= headerSubtitle.x || headerSubtitle.right <= headerTitle.x || headerTitle.bottom <= headerSubtitle.y || headerSubtitle.bottom <= headerTitle.y);
      return {
        viewport: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        composer,
        navigation,
        conversation,
        composerInput,
        headerOverlaps,
        targets,
        privacyContrast: contrast,
        privacyColors: { foreground: getComputedStyle(note).color, background: getComputedStyle(document.querySelector("#concierge-card")).backgroundColor, secondaryToken: getComputedStyle(document.documentElement).getPropertyValue("--text-secondary"), link: document.querySelector('link[rel="stylesheet"]')?.href },
      };
    });

    expect(geometry.documentWidth, JSON.stringify(geometry)).toBeLessThanOrEqual(viewport.width + 1);
    expect(geometry.bodyWidth, JSON.stringify(geometry)).toBeLessThanOrEqual(viewport.width + 1);
    expect(geometry.conversation.bottom, `conversation must end before the composer at ${viewport.width}px`).toBeLessThanOrEqual(geometry.composer.y + 1);
    expect(geometry.composer.bottom, `composer must stay above navigation at ${viewport.width}px`).toBeLessThanOrEqual(geometry.navigation.y + 1);
    expect(geometry.composerInput.width, `composer input width at ${viewport.width}px`).toBeGreaterThanOrEqual(140);
    expect(geometry.headerOverlaps, `concierge heading and subtitle must not collide at ${viewport.width}px`).toBe(false);
    expect(geometry.privacyContrast, `privacy disclosure contrast at ${viewport.width}px ${JSON.stringify(geometry)}`).toBeGreaterThanOrEqual(4.5);
    for (const target of geometry.targets) {
      expect(target.width, `${target.label} width at ${viewport.width}px`).toBeGreaterThanOrEqual(24);
      expect(target.height, `${target.label} height at ${viewport.width}px`).toBeGreaterThanOrEqual(24);
    }
  }
});

test("published property themes apply without changing guest navigation or content", async ({ page }) => {
  let activeTheme = THEMES[0];
  await installEmptyProperty(page, () => activeTheme);
  await page.goto("/");
  await expect(page.locator(".home-discovery-empty")).toBeVisible();

  for (const theme of THEMES) {
    activeTheme = theme;
    if (theme !== THEMES[0]) await page.reload();
    await expect.poll(() => page.locator("html").evaluate((element) => getComputedStyle(element).getPropertyValue("--accent").trim())).toBe(theme.accent);
    await expect(page.locator(".experience-configured-navigation button")).toHaveCount(5);
    await expect(page.locator(".home-discovery-empty")).toBeVisible();
  }
});
