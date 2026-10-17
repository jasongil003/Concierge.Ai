import { expect, test } from "@playwright/test";

// --- Helpers ---
const csrfByRequest = new WeakMap();

async function loginAdmin(api) {
  const response = await api.post("/api/admin/auth/login", {
    data: { username: "admin", password: "PlaywrightOnly-Admin-123!", remember_me: false },
  });
  expect(response.ok()).toBeTruthy();
  const csrf = (await response.json()).user.csrf_token;
  csrfByRequest.set(api, csrf);
  const properties = await api.get("/api/admin/properties");
  expect(properties.ok()).toBeTruthy();
  if (!(await properties.json()).properties.length) {
    const created = await api.put("/api/admin/properties/e2e-property", {
      headers: csrfHeaders(api),
      data: { property_id: "e2e-property", hotel_name: "E2E Property", timezone: "Asia/Manila" },
    });
    expect(created.ok()).toBeTruthy();
  }
  return csrf;
}

function csrfHeaders(api) {
  return { "X-CSRF-Token": csrfByRequest.get(api) };
}

async function openPanel(page, label) {
  await page.locator('body[data-admin-ready="true"]').waitFor();
  if ((page.viewportSize()?.width || 1440) <= 620) {
    const shell = page.locator(".platform-shell");
    if (!(await shell.evaluate((element) => element.classList.contains("mobile-nav-open")))) {
      await page.locator("#sidebar-toggle").click();
      await expect(shell).toHaveClass(/mobile-nav-open/);
    }
    await page.locator("details.nav-group").evaluateAll((groups) => {
      for (const group of groups) group.open = false;
    });
  }
  const button = page.locator(".nav-item").filter({ hasText: label }).first();
  await button.evaluate((element) => {
    const group = element.closest("details");
    if (group) group.open = true;
  });
  await button.scrollIntoViewIfNeeded();
  await button.click();
}

async function openLegacyDesignControls(page) {
  await openPanel(page, "Design");
  await expect(page.locator("#builder-page-settings")).toBeVisible();
}

async function openDesignGroup(page, name) {
  const group = page.locator(`[data-inspector-panel="${name}"]`);
  if (!(await group.evaluate((element) => element.open))) await group.locator(":scope > summary").click();
}

test.beforeEach(async ({ page, request }) => {
  await loginAdmin(request);
  await loginAdmin(page.request);
});

test("admin onboarding: create the first property from an empty workspace", async ({ page, request }) => {
  const existingResponse = await request.get("/api/admin/properties");
  expect(existingResponse.ok()).toBeTruthy();
  const existingProperties = (await existingResponse.json()).properties;
  for (const property of existingProperties) {
    const removed = await request.delete("/api/admin/properties/" + encodeURIComponent(property.property_id), { headers: csrfHeaders(request) });
    expect(removed.ok(), await removed.text()).toBeTruthy();
  }

  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
  await expect(page.locator("#property-onboarding")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Property not configured" })).toBeVisible();
  await page.locator("#onboarding-create-property").click();
  await page.locator("#property-create-name").fill("E2E Onboarding Property");
  const propertyId = `e2e-onboarding-${Date.now().toString(36)}`;
  await page.locator("#property-create-id").fill(propertyId);
  await page.locator("#property-create-timezone").selectOption("Asia/Manila");
  await page.locator("#property-create-country").fill("Philippines");
  await page.locator("#property-create-submit").click();

  await expect(page.locator("#property-switcher")).toHaveValue(propertyId);
  const created = await request.get(`/api/admin/properties/${propertyId}`);
  expect(created.ok()).toBeTruthy();
  expect((await created.json())).toMatchObject({ hotel_name: "E2E Onboarding Property", country: "Philippines" });

  const propertyPath = `/api/admin/properties/${propertyId}`;
  const overview = await request.get(`${propertyPath}/hospitality`);
  expect(overview.ok()).toBeTruthy();
  const hospitality = await overview.json();
  for (const key of ["facilities", "restaurants", "promotions", "events", "service_requests", "notification_rules", "departments", "services", "recommendations"]) {
    expect(hospitality[key]).toEqual([]);
  }
  expect(hospitality.menus).toEqual({});
  const serviceCatalog = await request.get(`${propertyPath}/service-catalog`).then((response) => response.json());
  expect(serviceCatalog).toEqual({ departments: [], services: [] });
  const property = await created.json();
  expect(property.rooms).toEqual([]);
  expect(property.domain).toBe("");
  expect(property.antlabs_config).toEqual({});
  const antlabs = await request.get(`${propertyPath}/antlabs/status`).then((response) => response.json());
  expect(antlabs.property_authentication_enabled).toBe(false);
  expect(antlabs.property_authentication_types).toEqual([]);
  const deployment = await request.get(`${propertyPath}/deployment/status`).then((response) => response.json());
  expect(deployment.domain.status).toBe("not_configured");
  expect(deployment.ssl.status).toBe("not_configured");
  const zones = await request.get(`${propertyPath}/zones`).then((response) => response.json());
  for (const key of ["buildings", "floors", "maps", "zones"]) expect(zones[key]).toEqual([]);
  const knowledge = await request.get(`${propertyPath}/knowledge`).then((response) => response.json());
  for (const key of ["items", "documents", "faqs"]) expect(knowledge[key]).toEqual([]);
  const sessions = await request.get(`${propertyPath}/sessions`).then((response) => response.json());
  for (const key of ["sessions", "stays", "guest_sessions", "devices"]) expect(sessions[key]).toEqual([]);

  await openPanel(page, "Rooms");
  await expect(page.locator("#room-list")).toContainText("Your room catalog is ready to build");
  await openPanel(page, "Facilities");
  await expect(page.locator("#facility-empty")).toContainText("No facilities configured yet.");
  await expect(page.locator("#empty-add-facility")).toHaveText(/Add Facility/);
  await openPanel(page, "Restaurants");
  await expect(page.locator("#restaurant-empty")).toContainText("No restaurants configured yet.");
  await openPanel(page, "Service Catalog");
  await expect(page.locator("#department-list")).toContainText("No departments configured.");
  await expect(page.locator("#catalog-service-list")).toContainText("No services configured.");
  await openPanel(page, "FAQs");
  await expect(page.locator("#faq-list")).toContainText("No FAQs configured yet.");
  await openPanel(page, "Documents");
  await expect(page.locator("#document-list")).toContainText("No legacy document records.");
  await expect(page.locator("#knowledge-source-list")).toContainText("No uploaded source files.");

  await page.goto("/");
  await expect(page.locator("#home-view")).toBeVisible();
  await expect(page.locator("#home-cards-section")).toBeHidden();
  for (const section of ["#dining-section", "#facility-section", "#event-section", "#promotion-section", "#recommendation-section"]) {
    await expect(page.locator(section)).toBeHidden();
  }
});

test("facilities panel: empty state, search, and styled CRUD actions work", async ({ page, request }) => {
  await page.goto("/admin");
  await openPanel(page, "Facilities");
  await expect(page.locator("#facility-empty")).toContainText("No facilities configured yet.");
  await expect(page.locator("#facility-table-shell")).toBeHidden();

  await page.locator("#add-facility").click();
  await expect(page.locator("#facility-dialog")).toBeVisible();
  await page.locator("#facility-name").fill("Configured Test Facility");
  await page.locator("#facility-type").fill("amenity");
  await page.locator("#facility-location").fill("Level A");
  await page.locator("#facility-hours").fill("All day");
  await page.locator("#facility-description").fill("Test-only facility details.");
  await page.locator("#facility-images").fill("/uploads/test-facility.webp\nhttps://images.example/facility.webp");
  await page.locator("#facility-policies").fill("Children must be supervised.\nNo glass containers.");
  await page.locator("#save-facility").click();

  const row = page.locator("#facility-list tr").filter({ hasText: "Configured Test Facility" });
  await expect(row).toBeVisible();
  await expect(row.locator("button")).toHaveCount(2);
  await expect(row.locator("button").nth(0)).toHaveClass(/btn-secondary/);
  await expect(row.locator("button").nth(1)).toHaveClass(/btn-danger/);
  const propertyId = await getFirstPropertyId(request);
  const hospitality = await request.get(`/api/admin/properties/${propertyId}/hospitality`).then((response) => response.json());
  const savedFacility = hospitality.facilities.find((item) => item.name === "Configured Test Facility");
  expect(savedFacility.location).toBe("Level A");
  expect(savedFacility.images).toEqual(["/uploads/test-facility.webp", "https://images.example/facility.webp"]);
  expect(savedFacility.policies).toEqual(["Children must be supervised.", "No glass containers."]);
  await page.goto("/");
  await page.getByRole("navigation", { name: "Guest navigation" }).getByRole("button", { name: "Explore" }).click();
  const guestCard = page.locator("#facility-list .guest-card-facility").filter({ hasText: "Configured Test Facility" });
  await expect(guestCard).toContainText("Location: Level A");
  await expect(guestCard).toContainText("Hours: All day");
  await expect(guestCard.locator(".guest-card-policies")).toContainText("No glass containers.");
  await page.goto("/admin");
  await openPanel(page, "Facilities");

  await page.locator("#facility-search").fill("no matching facility");
  await expect(page.locator("#facility-list")).toContainText("No facilities match your search.");
  await page.locator("#facility-search").fill("");

  await row.getByRole("button", { name: "Edit" }).click();
  await expect(page.locator("#facility-policies")).toHaveValue("Children must be supervised.\nNo glass containers.");
  await page.locator("#facility-location").fill("Level B");
  await page.locator("#facility-policies").fill("No glass containers.");
  await page.locator("#facility-status").selectOption("maintenance");
  await page.locator("#save-facility").click();
  await expect(row).toContainText("Level B");
  await expect(row).toContainText("maintenance");
  const updatedHospitality = await request.get(`/api/admin/properties/${propertyId}/hospitality`).then((response) => response.json());
  const updatedFacility = updatedHospitality.facilities.find((item) => item.name === "Configured Test Facility");
  expect(updatedFacility.location).toBe("Level B");
  expect(updatedFacility.policies).toEqual(["No glass containers."]);

  page.once("dialog", (dialog) => dialog.accept());
  await row.getByRole("button", { name: "Delete" }).click();
  await expect(page.locator("#facility-empty")).toBeVisible();
});

async function getFirstPropertyId(request) {
  const res = await request.get("/api/admin/properties");
  expect(res.ok()).toBeTruthy();
  return (await res.json()).properties[0].property_id;
}

async function getOriginalDesign(request, propertyId) {
  const res = await request.get(`/api/admin/properties/${propertyId}/design`);
  expect(res.ok()).toBeTruthy();
  return (await res.json()).published;
}

test("hotel assistant composer keeps its input and helper text in separate rows", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "AI Assistant");
  const composer = page.locator("#assistant-page-form");
  const input = page.locator("#assistant-page-input");
  const row = page.locator(".assistant-compose-row");
  const helper = composer.locator(":scope > small");
  const layout = await page.evaluate(() => {
    const form = document.querySelector("#assistant-page-form");
    const input = document.querySelector("#assistant-page-input");
    const row = document.querySelector(".assistant-compose-row");
    const helper = form.querySelector(":scope > small");
    const formStyle = getComputedStyle(form);
    return {
      columns: formStyle.gridTemplateColumns.trim().split(/\s+/).length,
      inputWidth: input.getBoundingClientRect().width,
      rowBottom: row.getBoundingClientRect().bottom,
      helperTop: helper.getBoundingClientRect().top,
    };
  });

  expect(layout.columns).toBe(1);
  expect(layout.inputWidth).toBeGreaterThan(200);
  expect(layout.helperTop).toBeGreaterThanOrEqual(layout.rowBottom);
  await expect(input).toBeVisible();
  await expect(row).toBeVisible();
  await expect(helper).toBeVisible();
});

test("hotel knowledge composer uses Enter, Shift+Enter, and one in-flight request", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "AI Assistant");
  let requests = 0;
  await page.route("**/assistant/hotel-chat", async (route) => {
    requests += 1;
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ answer: "Pool closes at 10 PM.", provider: "test", model: "test", sources: [] }) });
  });
  await page.locator(".assistant-mode[data-assistant-mode='knowledge']").click();
  const input = page.locator("#assistant-page-input");
  await input.fill("When does the pool close?");
  await input.press("Shift+Enter");
  await expect(input).toHaveValue("When does the pool close?\n");
  expect(requests).toBe(0);
  await input.press("Enter");
  await input.press("Enter");
  await expect(page.locator("#assistant-page-messages .assistant-message.answer")).toContainText("Pool closes at 10 PM.");
  expect(requests).toBe(1);
});

test("document upload creates reviewable knowledge without publishing", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Documents");
  const filename = `Pool-Hours-${Date.now()}.txt`;
  await page.locator("#knowledge-document-upload").setInputFiles({ name: filename, mimeType: "text/plain", buffer: Buffer.from(`Pool hours: 06:00-22:00\nSource: ${filename}`) });
  await expect(page.locator("#knowledge-source-list")).toContainText(filename);
  await openPanel(page, "Knowledge");
  await expect(page.locator("#managed-knowledge-list")).toContainText("Pool hours: 06:00-22:00");
  await expect(page.locator("#managed-knowledge-list")).toContainText("ready review");
});

// --- 1. Admin Controls Audit (read-only, safe to run in parallel) ---

test("topbar: publish state, Save Draft, Publish, Discard, Open guest app", async ({ page }) => {
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
  const viewportWidth = page.viewportSize()?.width || 1440;
  if (viewportWidth > 640) {
    await expect(page.locator("#publish-state")).toBeHidden();
  }
  if (viewportWidth > 900) {
    await expect(page.getByRole("button", { name: "Save Draft", exact: true })).toBeHidden();
    await expect(page.getByRole("button", { name: "Publish" })).toBeHidden();
    await expect(page.getByRole("button", { name: "Discard" })).toBeHidden();
    await openPanel(page, "Design");
    await expect(page.locator("#publish-state")).toBeVisible();
    for (const selector of ["#discard-design", "#save-draft", "#publish-design"]) {
      await expect(page.locator(selector)).toBeHidden();
    }
    await expect(page.locator("#builder-discard-button")).toBeEnabled();
    await expect(page.locator("#builder-save-button")).toBeEnabled();
    await expect(page.locator("#builder-publish-button")).toBeEnabled();
  } else {
    await expect(page.locator("#property-switcher")).toBeVisible();
    await expect(page.locator("#profile-button")).toBeVisible();
  }
  await expect(page.locator('.topbar-status a[href="/"]')).toHaveAttribute("href", "/");
});

test("topbar: sidebar and profile buttons perform their actions", async ({ page }) => {
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();

  const shell = page.locator(".platform-shell");
  await page.locator("#sidebar-toggle").click();
  if ((page.viewportSize()?.width || 1440) <= 620) {
    await expect(shell).toHaveClass(/mobile-nav-open/);
    await expect(page.locator("#sidebar-toggle")).toHaveAttribute("aria-label", "Close navigation");
    await page.locator("#sidebar-toggle").click();
    await expect(shell).not.toHaveClass(/mobile-nav-open/);
  } else {
    await expect(shell).toHaveClass(/sidebar-collapsed/);
    await expect(page.locator("#sidebar-toggle")).toHaveAttribute("aria-label", "Expand sidebar");
    await page.locator("#sidebar-toggle").click();
    await expect(shell).not.toHaveClass(/sidebar-collapsed/);
  }

  await page.locator("#profile-button").click();
  await expect(page.locator("#profile-menu")).toBeVisible();
  await page.getByRole("button", { name: "Profile", exact: true }).click();
  await expect(page.locator("#profile")).toBeVisible();

  await page.locator("#profile-button").click();
  await page.getByRole("button", { name: "Security", exact: true }).click();
  await expect(page.locator("#security")).toBeVisible();

  await page.locator("#profile-button").click();
  await page.getByRole("button", { name: "Switch Property" }).click();
  await expect(page.locator("#property-switcher")).toBeFocused();
});

test.describe("responsive sidebar toggle state", () => {
  test.describe("mobile drawer", () => {
    test.use({ viewport: { width: 375, height: 812 } });

    test("labels, accessibility state, focus, and breakpoint changes stay in sync", async ({ page }, testInfo) => {
      test.skip(testInfo.project.name !== "mobile-chrome", "The drawer state test runs in the mobile browser project.");
      const pageErrors = [];
      page.on("pageerror", (error) => pageErrors.push(error.message));
      await page.goto("/admin");
      await page.locator('body[data-admin-ready="true"]').waitFor();

      const shell = page.locator("#platform-shell");
      const sidebar = page.locator("#platform-sidebar");
      const toggle = page.locator("#sidebar-toggle");
      await expect(toggle).toHaveAttribute("aria-label", "Open navigation");
      await expect(toggle).toHaveAttribute("title", "Open navigation");
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(await sidebar.evaluate((element) => element.inert)).toBe(true);
      await expect(shell).not.toHaveClass(/mobile-nav-open/);

      await toggle.click();
      await expect(shell).toHaveClass(/mobile-nav-open/);
      await expect(toggle).toHaveAttribute("aria-label", "Close navigation");
      await expect(toggle).toHaveAttribute("title", "Close navigation");
      await expect(toggle).toHaveAttribute("aria-expanded", "true");
      expect(await sidebar.evaluate((element) => element.inert)).toBe(false);

      await page.locator('.nav-item[data-nav-id="guest-requests"]').click();
      await expect(page.locator("#requests")).toHaveClass(/active/);
      await expect(shell).not.toHaveClass(/mobile-nav-open/);
      await expect(toggle).toHaveAttribute("aria-label", "Open navigation");
      await expect(toggle).toHaveAttribute("title", "Open navigation");
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      await expect(toggle).toBeFocused();
      expect(await sidebar.evaluate((element) => element.inert)).toBe(true);

      // Native Tab navigation must skip the closed, inert drawer.
      for (let index = 0; index < 24; index += 1) {
        await page.keyboard.press("Tab");
        expect(await page.evaluate(() => Boolean(document.activeElement?.closest(".platform-sidebar")))).toBe(false);
      }

      await page.setViewportSize({ width: 1440, height: 900 });
      await expect(toggle).toHaveAttribute("aria-label", "Collapse sidebar");
      await expect(toggle).toHaveAttribute("title", "Collapse sidebar");
      await expect(toggle).toHaveAttribute("aria-expanded", "true");
      await expect(shell).not.toHaveClass(/mobile-nav-open/);
      await expect(shell).not.toHaveClass(/sidebar-collapsed/);
      expect(await sidebar.evaluate((element) => element.inert)).toBe(false);

      await toggle.click();
      await expect(shell).toHaveClass(/sidebar-collapsed/);
      await expect(toggle).toHaveAttribute("aria-label", "Expand sidebar");
      await expect(toggle).toHaveAttribute("title", "Expand sidebar");
      await expect(toggle).toHaveAttribute("aria-expanded", "false");

      await page.setViewportSize({ width: 375, height: 812 });
      await expect(toggle).toHaveAttribute("aria-label", "Open navigation");
      await expect(toggle).toHaveAttribute("title", "Open navigation");
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      await expect(shell).not.toHaveClass(/sidebar-collapsed/);
      await expect(shell).not.toHaveClass(/mobile-nav-open/);
      expect(await sidebar.evaluate((element) => element.inert)).toBe(true);

      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-label", "Close navigation");
      await expect(toggle).toHaveAttribute("aria-expanded", "true");
      await page.setViewportSize({ width: 1440, height: 900 });
      await expect(toggle).toHaveAttribute("aria-label", "Expand sidebar");
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      await expect(shell).not.toHaveClass(/mobile-nav-open/);
      await expect(shell).toHaveClass(/sidebar-collapsed/);
      expect(await sidebar.evaluate((element) => element.inert)).toBe(false);

      await page.setViewportSize({ width: 620, height: 812 });
      await expect(toggle).toHaveAttribute("aria-label", "Open navigation");
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      await expect(shell).not.toHaveClass(/sidebar-collapsed/);
      expect(await sidebar.evaluate((element) => element.inert)).toBe(true);

      await page.setViewportSize({ width: 621, height: 812 });
      await expect(toggle).toHaveAttribute("aria-label", "Expand sidebar");
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      await expect(shell).toHaveClass(/sidebar-collapsed/);
      expect(await sidebar.evaluate((element) => element.inert)).toBe(false);
      expect(pageErrors).toEqual([]);
    });
  });

  test.describe("desktop sidebar", () => {
    test.use({ viewport: { width: 1440, height: 900 }, isMobile: false, hasTouch: false });

    test("labels match expanded state and the saved preference survives reload", async ({ page }, testInfo) => {
      test.skip(testInfo.project.name !== "chromium", "The desktop sidebar state test runs in standard Chromium.");
      const pageErrors = [];
      page.on("pageerror", (error) => pageErrors.push(error.message));
      await page.addInitScript(() => {
        if (localStorage.getItem("concierge.admin.sidebar") === null) {
          localStorage.setItem("concierge.admin.sidebar", "expanded");
        }
      });
      await page.goto("/admin");
      await page.locator('body[data-admin-ready="true"]').waitFor();

      const shell = page.locator("#platform-shell");
      const sidebar = page.locator("#platform-sidebar");
      const toggle = page.locator("#sidebar-toggle");
      await expect(toggle).toHaveAttribute("aria-label", "Collapse sidebar");
      await expect(toggle).toHaveAttribute("title", "Collapse sidebar");
      await expect(toggle).toHaveAttribute("aria-expanded", "true");
      await expect(shell).not.toHaveClass(/sidebar-collapsed/);
      expect(await sidebar.evaluate((element) => element.inert)).toBe(false);

      await toggle.click();
      await expect(shell).toHaveClass(/sidebar-collapsed/);
      await expect(toggle).toHaveAttribute("aria-label", "Expand sidebar");
      await expect(toggle).toHaveAttribute("title", "Expand sidebar");
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(await page.evaluate(() => localStorage.getItem("concierge.admin.sidebar"))).toBe("collapsed");

      await page.reload();
      await page.locator('body[data-admin-ready="true"]').waitFor();
      await expect(shell).toHaveClass(/sidebar-collapsed/);
      await expect(toggle).toHaveAttribute("aria-label", "Expand sidebar");
      await expect(toggle).toHaveAttribute("title", "Expand sidebar");
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(await sidebar.evaluate((element) => element.inert)).toBe(false);

      await toggle.click();
      await expect(shell).not.toHaveClass(/sidebar-collapsed/);
      await expect(toggle).toHaveAttribute("aria-label", "Collapse sidebar");
      await expect(toggle).toHaveAttribute("title", "Collapse sidebar");
      await expect(toggle).toHaveAttribute("aria-expanded", "true");
      await page.reload();
      await page.locator('body[data-admin-ready="true"]').waitFor();
      await expect(shell).not.toHaveClass(/sidebar-collapsed/);
      await expect(toggle).toHaveAttribute("aria-label", "Collapse sidebar");
      expect(await page.evaluate(() => localStorage.getItem("concierge.admin.sidebar"))).toBe("expanded");
      expect(pageErrors).toEqual([]);
    });
  });
});

test("sidebar: all navigation items are visible and clickable", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.locator('.nav-item[data-nav-id="knowledge-overview"]')).toHaveCount(0);
  const navLabels = [
    ["Dashboard", "overview"],
    ["Guest Requests", "requests"],
    ["Guest Sessions", "sessions"],
    ["Conversation Modules", "guest"],
    ["Hotel Information", "hotel-information"],
    ["Rooms", "rooms"],
    ["Facilities", "facilities"],
    ["Restaurants", "restaurants"],
    ["Zones & Maps", "zones"],
    ["Knowledge", "knowledge"],
    ["Models & Providers", "ai"],
    ["Usage", "ai-usage"],
    ["Integrations", "third-party"],
    ["ANTlabs / Wi-Fi", "wifi"],
    ["Authentication Types", "auth-types"],
    ["Webhooks", "webhooks"],
    ["Analytics", "analytics"],
    ["Reports", "reports"],
    ["Design", "appearance"],
    ["Branding / Intro", "intro"],
    ["Location", "location"],
    ["Users", "users"],
    ["Roles", "roles"],
    ["Permissions", "permissions"],
    ["Network Access", "network-access"],
    ["Audit", "audit"],
    ["Security", "security"],
  ];
  for (const [label, panel] of navLabels) {
    await openPanel(page, label);
    await expect(page.locator(`#${panel}`)).toBeVisible();
  }
});

test("integration directory links open the separate working setup pages", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Integrations");
  await expect(page.locator("#third-party")).toContainText("No external hospitality services are connected");
  await expect(page.locator("#third-party .integration-directory article")).toHaveCount(4);
  await page.getByRole("button", { name: "Open Wi-Fi status" }).click();
  await expect(page.locator("#wifi")).toBeVisible();
  await expect(page.locator('.nav-item[data-nav-id="antlabs-wifi"]')).toHaveClass(/active/);
});

test("webhooks can be created, edited, canceled, and deleted with confirmation", async ({ page }) => {
  let storedWebhook = null;
  await page.route("**/webhooks**", async (route) => {
    const { method } = route.request();
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith("/webhooks") && method === "GET") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ webhooks: storedWebhook ? [storedWebhook] : [], deliveries: [], supported_events: ["guest.session.started", "guest.request.created", "guest.request.updated", "conversation.escalated"] }) });
    }
    if (pathname.endsWith("/webhooks") && method === "PUT") {
      const payload = route.request().postDataJSON();
      storedWebhook = { webhook_id: payload.webhook_id || "webhook_e2e", name: payload.name, endpoint_url: payload.endpoint_url, events: payload.events, enabled: payload.enabled, secret_configured: Boolean(payload.secret) || Boolean(storedWebhook?.secret_configured), last_status: "never_tested", last_error: "" };
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(storedWebhook) });
    }
    if (method === "DELETE") {
      storedWebhook = null;
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "deleted" }) });
    }
    return route.continue();
  });
  await page.goto("/admin");
  await openPanel(page, "Webhooks");
  await page.locator("#webhook-name").fill("Guest Event Relay");
  await page.getByLabel("HTTPS endpoint URL").fill("https://example.com/concierge-events");
  await page.locator("#webhook-events").selectOption("guest.request.created");
  await page.locator("#webhook-secret").fill("test-signing-secret");
  await page.getByRole("button", { name: "Save Webhook" }).click();

  const row = page.locator("#webhook-list .compact-row").filter({ hasText: "Guest Event Relay" });
  await expect(row).toContainText("never tested");
  await row.getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("button", { name: "Cancel edit" })).toBeVisible();
  await expect(page.locator("#webhook-secret")).toHaveAttribute("placeholder", "Saved securely; leave blank to keep");
  await page.locator("#webhook-name").fill("Guest Event Relay Updated");
  await page.getByRole("button", { name: "Update Webhook" }).click();

  const updatedRow = page.locator("#webhook-list .compact-row").filter({ hasText: "Guest Event Relay Updated" });
  await expect(updatedRow).toBeVisible();
  await updatedRow.getByRole("button", { name: "Edit" }).click();
  await page.getByRole("button", { name: "Cancel edit" }).click();
  await expect(page.locator("#webhook-id")).toHaveValue("");

  page.once("dialog", (dialog) => dialog.dismiss());
  await updatedRow.getByRole("button", { name: "Delete" }).click();
  await expect(updatedRow).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await updatedRow.getByRole("button", { name: "Delete" }).click();
  await expect(updatedRow).toHaveCount(0);
});

test("management report download uses the period selected on its page", async ({ page }) => {
  await page.route("**/reports/export.xlsx*", (route) => route.fulfill({
    status: 200,
    headers: { "Content-Type": "application/octet-stream", "Content-Disposition": "attachment; filename=report.xlsx" },
    body: "test workbook",
  }));
  await page.goto("/admin");
  await openPanel(page, "Reports");
  await page.locator("#reports-period").selectOption("30d");
  const request = page.waitForRequest((item) => item.url().includes("/reports/export.xlsx") && item.url().includes("period=30d"));
  await page.getByRole("button", { name: "Download workbook" }).click();
  await request;
});

test("analytics rejects a backwards custom date range", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Analytics");
  await page.locator("#manager-period").selectOption("custom");
  await page.locator("#manager-start").fill("2026-09-28");
  await page.locator("#manager-end").fill("2026-09-27");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByRole("status")).toContainText("The end date must be on or after the start date.");
});

test("system settings use a timezone list and persist the selected zone", async ({ page, request }) => {
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
  const propertyId = await page.locator("#property-switcher").inputValue();
  const response = await request.get(`/api/admin/properties/${propertyId}`);
  expect(response.ok()).toBeTruthy();
  const originalProperty = await response.json();
  await openPanel(page, "Settings");

  const language = page.locator("#setting-language");
  await expect(language).toHaveJSProperty("tagName", "SELECT");
  await expect(language.locator('option[value="en"]')).toHaveText("English");
  const timezone = page.locator("#setting-timezone");
  await expect(timezone).toHaveJSProperty("tagName", "SELECT");
  await expect(timezone.locator('option[value="Asia/Manila"]')).toHaveCount(1);
  const originalForm = {
    language: await language.inputValue(),
    timezone: await timezone.inputValue(),
    maintenance: await page.locator("#setting-maintenance").isChecked(),
    message: await page.locator("#setting-maintenance-message").inputValue(),
  };
  const nextTimezone = originalForm.timezone === "UTC" ? "Asia/Manila" : "UTC";
  const nextLanguage = originalForm.language === "fil" ? "en" : "fil";
  await language.selectOption(nextLanguage);
  await timezone.selectOption(nextTimezone);
  await page.getByRole("button", { name: "Save Application Settings" }).click();
  await expect(page.getByRole("status")).toContainText("Application settings saved");
  const updated = await (await request.get(`/api/admin/properties/${propertyId}`)).json();
  expect(updated.timezone).toBe(nextTimezone);
  expect(updated.languages).toEqual([...new Set([...(originalProperty.languages || []), nextLanguage])]);
  expect(updated.app_settings.application.default_language).toBe(nextLanguage);

  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", nextLanguage);
  await page.goto("/admin");
  await openPanel(page, "Settings");

  await language.selectOption(originalForm.language);
  await timezone.selectOption(originalForm.timezone);
  await page.locator("#setting-maintenance").setChecked(originalForm.maintenance);
  await page.locator("#setting-maintenance-message").fill(originalForm.message);
  await page.getByRole("button", { name: "Save Application Settings" }).click();
  await expect(page.getByRole("status")).toContainText("Application settings saved");
  expect(originalProperty.timezone).toBeTruthy();
});

test("sidebar: each visible navigation item has a feature status", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
  for (const details of await page.locator("details.nav-group").all()) {
    await details.evaluate((el) => { el.open = true; });
  }
  const navItems = page.locator(".nav-item");
  const count = await navItems.count();
  expect(count).toBeGreaterThan(0);
  const labels = new Set();
  for (let i = 0; i < count; i++) {
    const item = navItems.nth(i);
    const label = (await item.locator(".nav-label").innerText()).trim();
    expect(labels.has(label)).toBeFalsy();
    labels.add(label);
    await expect(item).not.toContainText(/\bLive\b/i);
    const status = item.locator(".nav-status");
    if (await status.count()) await expect(status).toHaveText(/Partial|Coming Soon|Configuration Required/);
  }
});

test("guardrails panel exposes security controls and network diagnostics", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The security configuration workflow needs one browser profile.");
  await page.goto("/admin");
  await openPanel(page, "Guardrails");

  await expect(page.locator("#guardrail-diagnostic-property")).not.toHaveText("—");
  await expect(page.locator("#guardrail-antlabs-secret")).toHaveAttribute("type", "password");
  await expect(page.getByLabel("Security audit logging enabled")).toBeVisible();
});

test("Network Access saves exact guest hosts", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The network configuration workflow needs one browser profile.");
  page.on("dialog", (dialog) => dialog.accept());
  await page.route(/\/api\/admin\/properties\/[^/]+\/network-access\/status$/, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 150));
    await route.continue();
  });
  await page.goto("/admin");
  await openPanel(page, "Network Access");
  const hosts = page.locator("#guest-access-hosts");
  await expect(hosts).toBeVisible();
  await expect(hosts).toBeDisabled();
  await expect(hosts).toBeEnabled();
  const original = await hosts.inputValue();
  const configured = [...new Set([...original.split(/\r?\n/).filter(Boolean), "192.168.50.20", "concierge.hotel.local"])].join("\n");
  let collisionPropertyId = "";
  try {
    await hosts.fill(configured);
    await page.getByRole("button", { name: "Save Guest Access" }).click();
    await expect(page.locator("#toast")).toContainText("Guest Access saved");
    await expect(hosts).toHaveValue(configured);

    await page.reload();
    await openPanel(page, "Network Access");
    await expect(page.locator("#guest-access-hosts")).toHaveValue(configured);

    const edited = [...new Set([...configured.split(/\r?\n/).filter(Boolean), "edited.concierge.hotel.local"])].join("\n");
    await page.locator("#guest-access-hosts").fill(edited);
    await page.getByRole("button", { name: "Save Guest Access" }).click();
    await expect(page.locator("#toast")).toContainText("Guest Access saved");
    await page.reload();
    await openPanel(page, "Network Access");
    await expect(page.locator("#guest-access-hosts")).toHaveValue(edited);

    const auth = await page.request.get("/api/admin/auth/me");
    const csrf = (await auth.json()).user.csrf_token;
    collisionPropertyId = `qa-host-collision-${Date.now().toString(36)}`;
    const collisionProperty = await page.request.put(`/api/admin/properties/${collisionPropertyId}`, {
      headers: { "X-CSRF-Token": csrf },
      data: {
        property_id: collisionPropertyId,
        hotel_name: "Guest Host Collision Test",
        timezone: "Asia/Manila",
        guardrails: { guest_access_hosts: ["collision.hotel.local"] },
      },
    });
    expect(collisionProperty.ok(), await collisionProperty.text()).toBeTruthy();

    await page.locator("#guest-access-hosts").fill(`${edited}\ncollision.hotel.local`);
    await page.getByRole("button", { name: "Save Guest Access" }).click();
    await expect(page.locator("#toast")).toContainText("another property");
    await page.reload();
    await openPanel(page, "Network Access");
    await expect(page.locator("#guest-access-hosts")).toHaveValue(edited);

    await page.locator("#guest-access-hosts").fill("https://invalid.hotel.local");
    await page.getByRole("button", { name: "Save Guest Access" }).click();
    await expect(page.locator("#toast")).toContainText("Invalid host");
    await page.reload();
    await openPanel(page, "Network Access");
    await expect(page.locator("#guest-access-hosts")).toHaveValue(edited);
  } finally {
    await page.reload();
    await openPanel(page, "Network Access");
    await page.locator("#guest-access-hosts").fill(original);
    await page.getByRole("button", { name: "Save Guest Access" }).click();
    await expect(page.locator("#toast")).toContainText("Guest Access saved");
    await page.reload();
    await openPanel(page, "Network Access");
    await expect(page.locator("#guest-access-hosts")).toHaveValue(original);
    if (collisionPropertyId) {
      const auth = await page.request.get("/api/admin/auth/me");
      const csrf = (await auth.json()).user.csrf_token;
      const removed = await page.request.delete(`/api/admin/properties/${collisionPropertyId}`, {
        headers: { "X-CSRF-Token": csrf },
      });
      expect(removed.ok(), await removed.text()).toBeTruthy();
    }
  }
});

test("Network Access displays the HTTPS guest URL and QR for printing or NFC", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The network configuration workflow needs one browser profile.");
  const guestUrl = "https://concierge.example.test";
  await page.route(/\/api\/admin\/properties\/[^/]+\/network-access\/status$/, async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.guest = {
      ...data.guest,
      enabled: true,
      https_required: true,
      domain: "concierge.example.test",
      url: guestUrl,
    };
    await route.fulfill({ response, json: data });
  });
  await page.route(/\/api\/admin\/properties\/[^/]+\/guest-entry\/qr\.svg$/, (route) =>
    route.fulfill({ status: 200, contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg"/>' }));

  await page.goto("/admin");
  await openPanel(page, "Network Access");
  await expect(page.locator("#guest-entry-preview")).toBeVisible();
  await expect(page.locator("#guest-entry-qr")).toBeVisible();
  await expect(page.locator("#guest-entry-url")).toHaveAttribute("href", guestUrl);
  await expect(page.locator("#guest-entry-url")).toHaveText(guestUrl);
  await expect(page.locator("#network-access")).toContainText("write the approved guest URL as a URL or URI record");
  await expect(page.locator("#network-access")).toContainText("Do not write a guest session token");
});

test("overview panel: operational health is visible and configuration moved out", async ({ page }) => {
  let dashboardLoads = 0;
  page.on("request", (request) => {
    if (request.url().includes("/operations/dashboard?")) dashboardLoads += 1;
  });
  await page.goto("/admin");
  await expect(page.locator("#overview-title")).not.toBeEmpty();
  await expect(page.locator("#operations-health-banner")).toBeVisible();
  await expect(page.locator("#operations-metrics .operations-metric")).toHaveCount(4);
  await expect(page.locator("#overview-charts .chart-card")).toHaveCount(6);
  const loadsBeforeRefresh = dashboardLoads;
  await page.getByRole("button", { name: "Refresh data" }).click();
  await expect.poll(() => dashboardLoads).toBeGreaterThan(loadsBeforeRefresh);
  await expect(page.getByRole("button", { name: "Refresh data" })).toBeEnabled();
  await openPanel(page, "Hotel Information");
  await expect(page.locator("#hotel-info-name")).toBeEnabled();
  await expect(page.getByRole("button", { name: "Save & Publish" })).toBeEnabled();
});

test("system health shows a fresh status summary and refreshes checks", async ({ page }) => {
  let dashboardLoads = 0;
  page.on("request", (request) => {
    if (request.url().includes("/operations/dashboard?")) dashboardLoads += 1;
  });
  await page.goto("/admin");
  await openPanel(page, "System Health");
  await expect(page.locator("#health-components .component-card")).toHaveCount(7);
  await expect(page.locator("#system-health-summary")).toContainText("24h timeframe");
  await expect(page.locator("#system-health-summary")).toContainText(/healthy or simulated/);
  const loadsBeforeRefresh = dashboardLoads;
  await page.getByRole("button", { name: "Refresh checks" }).click();
  await expect.poll(() => dashboardLoads).toBeGreaterThan(loadsBeforeRefresh);
  await expect(page.getByRole("button", { name: "Refresh checks" })).toBeEnabled();
  const alertsLink = page.getByRole("button", { name: "View alerts" }).first();
  if (await alertsLink.count()) {
    await alertsLink.click();
    await expect(page.locator(".panel.active")).toHaveAttribute("id", "alerts");
  }
});

test("hotel check-in and checkout are time pickers and persist their values", async ({ page, request }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "Property time saving only needs one browser.");
  const propertyId = await getFirstPropertyId(request);
  const propertyUrl = `/api/admin/properties/${propertyId}`;
  const original = await request.get(propertyUrl).then((response) => response.json());
  const originalContactDetails = structuredClone(original.contact_details || {});
  try {
    await page.goto("/admin");
    await openPanel(page, "Hotel Information");
    await expect(page.locator("#hotel-info-checkin")).toHaveAttribute("type", "time");
    await expect(page.locator("#hotel-info-checkout")).toHaveAttribute("type", "time");
    await page.locator("#hotel-info-checkin").fill("15:45");
    await page.locator("#hotel-info-checkout").fill("11:30");
    await page.getByRole("button", { name: "Save & Publish" }).click();
    await expect(page.locator("#toast")).toContainText("Hotel information saved");
    const saved = await request.get(propertyUrl).then((response) => response.json());
    expect(saved.contact_details.check_in).toBe("15:45");
    expect(saved.contact_details.checkout).toBe("11:30");
  } finally {
    const current = await request.get(propertyUrl).then((response) => response.json());
    current.contact_details = originalContactDetails;
    const restored = await request.put(propertyUrl, { headers: csrfHeaders(request), data: current });
    expect(restored.ok()).toBeTruthy();
  }
});

test("Alerts show their evaluated timeframe and refresh the current view", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Alerts");
  await expect(page.locator("#alerts-summary")).toContainText("24h timeframe");

  const dashboardResponseFor = (period) => page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname.endsWith("/operations/dashboard") && url.searchParams.get("period") === period;
  });
  let holdNext24HourResponse = false;
  let releaseStaleResponse;
  let resolveStaleResponseReady;
  let resolveStaleResponseFulfilled;
  const staleResponseReady = new Promise((resolve) => { resolveStaleResponseReady = resolve; });
  const staleResponseFulfilled = new Promise((resolve) => { resolveStaleResponseFulfilled = resolve; });
  await page.route("**/operations/dashboard**", async (route) => {
    const url = new URL(route.request().url());
    if (!holdNext24HourResponse || url.searchParams.get("period") !== "24h") {
      await route.continue();
      return;
    }

    holdNext24HourResponse = false;
    const response = await route.fetch();
    resolveStaleResponseReady();
    await new Promise((resolve) => { releaseStaleResponse = resolve; });
    await route.fulfill({ response });
    resolveStaleResponseFulfilled();
  });

  const firstOneHourResponse = dashboardResponseFor("1h");
  await page.getByRole("combobox", { name: "Alerts timeframe" }).selectOption("1h");
  expect((await firstOneHourResponse).ok()).toBeTruthy();
  await expect(page.locator("#alerts-summary")).toContainText("1h timeframe");

  // A slow earlier request must not replace a newer timeframe after it finishes.
  holdNext24HourResponse = true;
  await page.getByRole("combobox", { name: "Alerts timeframe" }).selectOption("24h");
  await staleResponseReady;
  const latestOneHourResponse = dashboardResponseFor("1h");
  await page.getByRole("combobox", { name: "Alerts timeframe" }).selectOption("1h");
  expect((await latestOneHourResponse).ok()).toBeTruthy();
  await expect(page.locator("#alerts-summary")).toContainText("1h timeframe");
  releaseStaleResponse();
  await staleResponseFulfilled;
  await expect(page.locator("#alerts-summary")).toContainText("1h timeframe");

  const refreshResponse = dashboardResponseFor("1h");
  await page.getByRole("button", { name: "Refresh alerts" }).click();
  expect((await refreshResponse).ok()).toBeTruthy();
  await expect(page.getByRole("button", { name: "Refresh alerts" })).toBeEnabled();
});

test("appearance panel: one builder owns page theme controls and updates the canvas", async ({ page }) => {
  await page.goto("/admin");
  await openLegacyDesignControls(page);

  const selectedPropertyName = (await page.locator("#property-switcher option:checked").innerText()).trim();
  await expect(page.locator("#builder-canvas")).toBeVisible();
  await expect(page.locator(".legacy-design-settings, #chat-preview, .design-stage, .design-workspace")).toHaveCount(0);
  await expect(page.locator("#builder-inspector-title")).toHaveText("Page Settings");

  const inspectorControls = {
    brand: ["design-hotel-name", "logo-display-input", "logo-upload-input", "header-enabled-input", "show-logo-input", "show-name-input"],
    content: ["greeting-input", "welcome-input", "composer-placeholder-input"],
    theme: ["background-input", "text-color-input", "secondary-text-color-input", "background-image-input", "background-overlay-input", "accent-input"],
    layout: ["font-input", "density-input", "content-width-input", "message-width-input", "user-style-input", "assistant-style-input"],
    navigation: ["builder-navigation-settings"],
    prompts: ["add-prompt"],
    versions: ["version-list"],
  };
  for (const [inspector, controlIds] of Object.entries(inspectorControls)) {
    const group = page.locator(`[data-inspector-panel="${inspector}"]`);
    if (!(await group.evaluate((element) => element.open))) await group.locator(":scope > summary").click();
    await expect(group).toHaveAttribute("open", "");
    for (const controlId of controlIds) {
      await expect(page.locator(`#${controlId}`)).toBeVisible();
      if (controlId !== "builder-navigation-settings" && controlId !== "version-list") await expect(page.locator(`#${controlId}`)).toBeEnabled();
    }
  }
  await openDesignGroup(page, "brand");
  await page.locator("#design-hotel-name").fill("Preview-only design check");
  await expect(page.locator(".builder-live-header-identity strong")).toHaveText("Preview-only design check");
  await page.locator("#design-hotel-name").fill(selectedPropertyName);
});

test("appearance panel: one editor switches between components, layers, page settings, and section settings", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.locator(".panel.active")).toHaveCount(1);
  await expect(page.locator("#appearance")).toBeHidden();
  await openLegacyDesignControls(page);

  await expect(page.locator("#builder-canvas")).toHaveCount(1);
  await expect(page.locator("#builder-canvas .builder-guest-page")).toHaveCount(1);
  await expect(page.locator(".legacy-design-settings, #chat-preview, .design-stage, .design-workspace, .preview-stage")).toHaveCount(0);
  await expect(page.locator("#builder-page-settings")).toBeVisible();
  await expect(page.locator("#builder-inspector")).toBeHidden();
  await expect(page.locator("#builder-inspector-tabs")).toBeHidden();
  await expect(page.locator('[data-builder-library-panel="components"]')).toBeVisible();
  await expect(page.locator('[data-builder-library-panel="layers"]')).toBeHidden();

  const componentsTab = page.locator('[data-builder-library-tab="components"]');
  const layersTab = page.locator('[data-builder-library-tab="layers"]');
  await expect(componentsTab).toHaveAttribute("tabindex", "0");
  await expect(layersTab).toHaveAttribute("tabindex", "-1");
  await componentsTab.focus();
  await componentsTab.press("ArrowRight");
  await expect(layersTab).toBeFocused();
  await expect(layersTab).toHaveAttribute("aria-selected", "true");
  await expect(layersTab).toHaveAttribute("tabindex", "0");
  await layersTab.press("ArrowLeft");
  await expect(componentsTab).toBeFocused();
  await expect(componentsTab).toHaveAttribute("tabindex", "0");

  await layersTab.click();
  await expect(page.locator('[data-builder-library-panel="components"]')).toBeHidden();
  await expect(page.locator('[data-builder-library-panel="layers"]')).toBeVisible();
  const sectionCount = await page.locator("#builder-canvas .builder-canvas-section").count();
  await expect(page.locator("#builder-section-layers > li")).toHaveCount(sectionCount);
  await page.locator("#builder-section-layers [data-builder-layer-select]").first().click();
  await expect(page.locator("#builder-page-settings")).toBeHidden();
  await expect(page.locator("#builder-inspector")).toBeVisible();
  await expect(page.locator("#builder-inspector-tabs")).toBeVisible();
  await expect(page.locator("#builder-inspector-title")).not.toHaveText("Page Settings");

  await componentsTab.click();
  await expect(page.locator('[data-builder-library-panel="components"]')).toBeVisible();
  await expect(page.locator('[data-builder-library-panel="layers"]')).toBeHidden();
  await page.locator("#builder-templates-button").click();
  await expect(page.locator('#builder-template-menu [aria-label="Page layouts"]')).toBeVisible();
  await expect(page.locator('#builder-template-menu [aria-label="Theme palettes"]')).toBeVisible();
});

test("appearance panel: logo uploader shows selected-file status and previews the image", async ({ page }) => {
  await page.goto("/admin");
  await openLegacyDesignControls(page);
  await openDesignGroup(page, "brand");

  await expect(page.getByLabel("Upload hotel logo")).toBeVisible();
  await expect(page.getByText("Choose logo")).toBeVisible();
  await page.locator("#logo-upload-input").setInputFiles({
    name: "hotel-logo.png",
    mimeType: "image/png",
    buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/S4cAAAAASUVORK5CYII=", "base64"),
  });

  await expect(page.locator("#logo-upload-status")).toHaveText("hotel-logo.png is ready in this draft.");
  await expect(page.locator("#logo-url-input")).toHaveValue(/^data:image\/png;base64,/);
  await expect(page.locator(".builder-live-header-logo img")).toBeVisible();
});

test("appearance panel: center canvas device buttons resize the live page", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/admin");
  await openLegacyDesignControls(page);

  await page.locator('[data-builder-device="desktop"]').click();
  const desktopWidth = await page.locator("#builder-canvas").evaluate((element) => element.getBoundingClientRect().width);
  await page.locator('[data-builder-device="tablet"]').click();
  await expect.poll(() => page.locator("#builder-canvas").evaluate((element) => element.getBoundingClientRect().width)).toBeLessThanOrEqual(768);
  await page.locator('[data-builder-device="mobile"]').click();
  await expect.poll(() => page.locator("#builder-canvas").evaluate((element) => element.getBoundingClientRect().width)).toBeLessThanOrEqual(390);
  await expect(desktopWidth).toBeGreaterThan(390);
});

test("appearance panel: add and remove prompt buttons work", async ({ page }) => {
  await page.goto("/admin");
  await openLegacyDesignControls(page);
  await openDesignGroup(page, "prompts");
  const prompts = page.locator('[data-inspector-panel="prompts"]');
  const rows = page.locator("#prompt-list .prompt-row");
  const initialCount = await rows.count();

  await page.locator("#add-prompt").click();
  await expect(rows).toHaveCount(initialCount + 1);
  await rows.last().getByRole("button", { name: "Remove prompt" }).click();
  await expect(rows).toHaveCount(initialCount);
});

test("guest experience panel: modules can be managed", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Conversation Modules");
  await expect(page.locator("#guest-module-name")).toBeEnabled();
  await expect(page.locator("#guest-module-prompt")).toBeEnabled();
  await expect(page.getByRole("button", { name: "Save Module" })).toBeEnabled();
});

test("preview controls are interactive and intro settings save", async ({ page }) => {
  const propertyId = (await (await page.request.get("/api/admin/properties")).json()).properties[0].property_id;
  const resetIntro = await page.request.put(`/api/admin/properties/${propertyId}/intro`, {
    headers: csrfHeaders(page.request),
    data: { data: { mode: "none", preset: "none", duration_ms: 1400, background: "#fbfbfa", brand_color: "#18181b", welcome_message: "", first_visit_only: true, allow_skip: true, asset_url: "", asset_type: "" } },
  });
  expect(resetIntro.ok()).toBeTruthy();
  await page.goto("/admin");
  await openLegacyDesignControls(page);
  await expect(page.locator("#builder-canvas")).toBeVisible();
  await expect(page.locator("#builder-preview-button")).toBeVisible();
  for (const button of await page.locator(".builder-preview-composer button, .builder-preview-composer textarea").all()) {
    await expect(button).toBeDisabled();
  }

  await openPanel(page, "Branding / Intro");
  await expect(page.locator(".intro-editor")).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await expect(page.locator(".intro-editor-heading")).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await expect(page.locator(".intro-preview-toolbar")).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await expect(page.locator("#intro-preview-stage")).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await expect(page.locator("#play-intro-preview")).toBeDisabled();
  await expect(page.locator("#intro-preview-empty")).toBeVisible();
  await expect(page.locator("#intro-preview-card")).toBeHidden();
  await expect(page.locator("#intro-preview-skip")).toBeHidden();
  const welcomeStyles = [
    ["quiet_luxury", "luxury_reveal", "#f4f0e8", "#27352e", "Welcome to a more considered stay."],
    ["city_boutique", "minimal_fade", "#f3f6fa", "#20304a", "Your city stay, made simple."],
    ["warm_welcome", "fade_scale", "#fff6ed", "#70452f", "We're glad you're here."],
    ["coastal_retreat", "logo_to_chat_header", "#eff8f7", "#1e5d61", "Take a breath. You're right where you need to be."],
  ];
  for (const [style, preset, background, brand, message] of welcomeStyles) {
    await page.locator(`[data-intro-template="${style}"]`).click();
    await expect(page.locator("#intro-mode")).toHaveValue("generate_from_logo");
    await expect(page.locator("#intro-preset")).toHaveValue(preset);
    await expect(page.locator("#intro-message")).toHaveValue(message);
    await expect(page.locator("#intro-background")).toHaveValue(background);
    await expect(page.locator("#intro-brand-color")).toHaveValue(brand);
    await expect(page.locator(`[data-intro-template="${style}"]`)).toHaveAttribute("aria-pressed", "true");
  }
  await page.locator('[data-intro-template="quiet_luxury"]').click();
  await expect(page.locator("#intro-accessibility-check")).toContainText("WCAG AAA");
  await page.locator("#intro-brand-color").fill("#f4f0e8");
  await expect(page.locator("#intro-accessibility-check")).toContainText("target 4.5:1");
  await expect(page.locator("#intro-accessibility-check")).toHaveClass(/review/);
  await page.locator('[data-intro-template="quiet_luxury"]').click();
  await page.locator("#intro-mode").selectOption("generate_from_logo");
  await expect(page.locator("#intro-preview-card")).toBeVisible();
  await expect(page.locator("#intro-preview-empty")).toBeHidden();
  await page.locator('[data-intro-preset="fade_scale"]').click();
  await page.locator("#intro-duration").fill("2.2");
  await page.locator("#intro-skip").uncheck();
  await expect(page.locator("#intro-preview-skip")).toBeHidden();
  await page.locator("#intro-skip").check();
  await expect(page.locator("#intro-preview-skip")).toBeVisible();
  await page.locator("#intro-first-visit").uncheck();
  await expect(page.locator("#intro-duration-range")).toHaveValue("2200");
  await expect(page.locator("#play-intro-preview")).toBeEnabled();
  await page.locator("#play-intro-preview").click();
  await expect(page.locator("#intro-preview-card")).toHaveClass(/playing/);
  await expect(page.locator("#intro-preview-skip")).toBeEnabled();
  await page.locator("#intro-preview-skip").click();
  await expect(page.locator("#intro-preview-card")).not.toHaveClass(/playing/);
  await page.locator('[data-intro-device="desktop"]').click();
  await expect(page.locator("#intro-preview-device")).toHaveClass(/desktop/);
  await page.locator("#save-intro").click();
  await expect(page.locator("#intro-save-status")).toContainText("Saved");
  await page.reload();
  await openPanel(page, "Branding / Intro");
  await expect(page.locator("#intro-mode")).toHaveValue("generate_from_logo");
  await expect(page.locator("#intro-preset")).toHaveValue("fade_scale");
  await expect(page.locator("#intro-duration")).toHaveValue("2.2");
  await expect(page.locator("#intro-first-visit")).not.toBeChecked();
  await expect(page.locator("#intro-skip")).toBeChecked();
  await page.locator("#intro-first-visit").check();
  await page.locator("#intro-mode").selectOption("custom_upload");
  await expect(page.locator("#play-intro-preview")).toBeDisabled();
  await page.locator("#intro-upload").setInputFiles({
    name: "welcome.webm",
    mimeType: "application/octet-stream",
    buffer: Buffer.from([0x1a, 0x45, 0xdf, 0xa3, 0x00, 0x00, 0x00, 0x00]),
  });
  await expect(page.locator("#intro-asset-status")).toContainText("WebM video uploaded");
  await expect(page.locator("#intro-mode")).toHaveValue("custom_upload");
  await expect(page.locator("#play-intro-preview")).toBeEnabled();
  await page.locator("#intro-remove-asset").click();
  await expect(page.locator("#intro-asset-status")).toContainText("No custom video uploaded");
  await expect(page.locator("#intro-mode")).toHaveValue("generate_from_logo");
});

async function waitForMobileSidebarTransition(page, open) {
  await page.waitForFunction((shouldBeOpen) => {
    const shell = document.querySelector(".platform-shell");
    const sidebar = document.querySelector(".platform-sidebar");
    if (!shell || !sidebar || shell.classList.contains("mobile-nav-open") !== shouldBeOpen) return false;
    const transform = new DOMMatrixReadOnly(getComputedStyle(sidebar).transform);
    const expectedX = shouldBeOpen ? 0 : -sidebar.getBoundingClientRect().width * 1.02;
    return Math.abs(transform.m41 - expectedX) <= 0.1;
  }, open, { timeout: 5_000 });
}

async function openMobileSidebar(page) {
  const shell = page.locator(".platform-shell");
  const toggle = page.locator("#sidebar-toggle");
  if (!(await shell.evaluate((element) => element.classList.contains("mobile-nav-open")))) {
    await toggle.click();
  }
  await expect(shell).toHaveClass(/mobile-nav-open/);
  await expect(toggle).toHaveAttribute("aria-label", "Close navigation");
  await waitForMobileSidebarTransition(page, true);
}

async function verifyAdminNavigation(page, isMobile) {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
  const destinations = await page.locator(".nav-item").evaluateAll((items) => {
    return items.flatMap((item) => {
      const panel = item.dataset.panel;
      if (!panel) return [];
      return [{ navId: item.dataset.navId, panel }];
    });
  });
  const sidebar = page.locator(".platform-sidebar");
  const toggle = page.locator("#sidebar-toggle");
  const shell = page.locator(".platform-shell");

  if (isMobile) {
    await openMobileSidebar(page);
    const sidebarBox = await sidebar.boundingBox();
    const topbarBox = await page.locator(".platform-topbar").boundingBox();
    expect(sidebarBox).not.toBeNull();
    expect(topbarBox).not.toBeNull();
    expect(Math.abs(sidebarBox.x)).toBeLessThanOrEqual(0.5);
    expect(sidebarBox.x + sidebarBox.width).toBeLessThanOrEqual(375.5);
    expect(Math.abs(sidebarBox.y - (topbarBox.y + topbarBox.height))).toBeLessThanOrEqual(0.5);
    expect(sidebarBox.y + sidebarBox.height).toBeLessThanOrEqual(812.5);

    const groups = sidebar.locator(":scope > .sidebar-nav > .nav-group");
    for (let index = 0; index < await groups.count(); index += 1) {
      const group = groups.nth(index);
      if (!(await group.evaluate((element) => element.open))) {
        await group.locator(":scope > summary").click();
      }
      await expect(group).toHaveAttribute("open", "");
    }
    const scrollMetrics = await sidebar.locator(".sidebar-nav").evaluate((element) => ({
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
      overflowY: getComputedStyle(element).overflowY,
    }));
    expect(scrollMetrics.scrollHeight).toBeGreaterThan(scrollMetrics.clientHeight);
    expect(["auto", "scroll"]).toContain(scrollMetrics.overflowY);
  }

  for (const { navId, panel } of destinations) {
    await test.step(`Navigate via ${navId} to ${panel}`, async () => {
      await expect(sidebar).toBeVisible();
      if (isMobile) {
        await openMobileSidebar(page);
      }
      const item = page.locator(`.nav-item[data-nav-id="${navId}"]`);
      const navGroup = item.locator("xpath=ancestor::details[1]");
      if (!(await navGroup.evaluate((element) => element.open))) {
        await navGroup.locator(":scope > summary").click();
      }
      await expect(navGroup).toHaveAttribute("open", "");
      await item.scrollIntoViewIfNeeded();
      const navBox = await item.boundingBox();
      expect(navBox).not.toBeNull();
      const receivesClick = await item.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
        return Boolean(hit && (hit === element || element.contains(hit)));
      });
      expect(receivesClick, `Navigation item ${navId} is obscured or not hit-testable`).toBe(true);
      if (isMobile) {
        await expect(item).toBeInViewport({ ratio: 0.95 });
        expect(navBox.x).toBeGreaterThanOrEqual(-0.5);
        expect(navBox.x + navBox.width).toBeLessThanOrEqual(375.5);
        expect(navBox.y).toBeGreaterThanOrEqual(103.5);
        expect(navBox.y + navBox.height).toBeLessThanOrEqual(812.5);
      }
      if (isMobile) {
        // Click the location we just hit-tested. Locator.click() performs a
        // second scroll of the nested sidebar; at the end of its long list,
        // that extra scroll can move the row behind adjacent links/topbar.
        const box = await item.boundingBox();
        await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
      } else {
        await item.click();
      }
      const active = page.locator(".panel.active");
      await expect(active).toHaveAttribute("id", panel);
      if (isMobile) {
        await expect(shell).not.toHaveClass(/mobile-nav-open/);
        await expect(toggle).toHaveAttribute("aria-label", "Open navigation");
        await waitForMobileSidebarTransition(page, false);
      }
      await expect(active.locator(":scope > .page-title h1, :scope > .onboarding-card h1").first()).toBeVisible();
      const pageGuide = active.locator(":scope > .page-comment, :scope > .contextual-help-disclosure").first();
      await expect(pageGuide).toBeVisible();
      if (panel === "appearance") {
        if (isMobile) {
          await expect(page.locator("#discard-design")).toBeHidden();
          await expect(page.locator("#save-draft")).toBeHidden();
          await expect(page.locator("#publish-design")).toBeHidden();
          await expect(page.locator(".legacy-design-settings")).toHaveCount(0);
          await expect(page.locator("#builder-page-settings")).toBeVisible();
          await expect(page.locator(".builder-more-menu summary")).toBeVisible();
          await expect(page.locator("#builder-save-button")).toBeVisible();
          await expect(page.locator("#builder-publish-button")).toBeVisible();
        } else {
          for (const selector of ["#discard-design", "#save-draft", "#publish-design"]) {
            const button = page.locator(selector);
            await expect(button).toBeHidden();
          }
          await page.locator(".builder-more-menu summary").click();
          for (const selector of ["#builder-discard-button", "#builder-save-button", "#builder-publish-button"]) {
            const button = page.locator(selector);
            await expect(button).toBeVisible();
            await expect(button).toBeEnabled();
            await button.click({ trial: true });
          }
        }
      }
      await pageGuide.locator("summary").click();
      await expect(pageGuide).toHaveAttribute("open", "");
      await expect(pageGuide.locator(".page-comment-content, .module-guide, .personalization-guide, .session-guide, .request-guide, .facility-guide, .room-guide-card, .intro-guide").first()).toBeVisible();
      const layout = await page.evaluate(() => {
        const width = document.documentElement.scrollWidth;
        const viewport = window.innerWidth;
        const offenders = [...document.querySelectorAll("body *")].map((element) => {
          const rect = element.getBoundingClientRect();
          return { tag: element.tagName, id: element.id, className: typeof element.className === "string" ? element.className : "", right: Math.round(rect.right), left: Math.round(rect.left), width: Math.round(rect.width) };
        }).filter((item) => item.width > 0 && (item.right > viewport + 1 || item.left < -1)).sort((a, b) => b.right - a.right).slice(0, 6);
        return { width, viewport, offenders };
      });
      expect(layout.width, `Horizontal page overflow on ${panel}: ${JSON.stringify(layout)}`).toBeLessThanOrEqual(layout.viewport + 1);
      const relatedLink = active.locator(".page-comment-related-link").first();
      await expect(relatedLink).toBeVisible();
      const relatedPanel = await relatedLink.getAttribute("data-panel");
      await relatedLink.click();
      await expect(page.locator(".panel.active")).toHaveAttribute("id", relatedPanel);
    });
  }

  expect(pageErrors).toEqual([]);
}

test.describe("admin navigation at a 375px viewport", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("every visible admin tab opens with page-specific guidance", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile-chrome", "The 375px navigation sweep runs in the mobile browser project.");
    test.setTimeout(90_000);
    await verifyAdminNavigation(page, true);
  });
});

test.describe("admin navigation at a 1440px desktop viewport", () => {
  test.use({ viewport: { width: 1440, height: 900 }, isMobile: false, hasTouch: false });

  test("every visible admin tab opens with page-specific guidance", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "The desktop navigation sweep runs in the standard Chromium project.");
    test.setTimeout(90_000);
    await verifyAdminNavigation(page, false);
  });
});

test("design actions require concierge.edit in the UI and on the server", async ({ page, request }) => {
  const propertyId = await getFirstPropertyId(request);
  const username = `viewer.design.${Date.now()}`;
  const created = await request.post("/api/admin/users", {
    headers: csrfHeaders(request),
    data: {
      username,
      display_name: "Design Viewer",
      password: "DesignViewerPassword123!",
      property_id: propertyId,
      role_id: "role-viewer-auditor",
      status: "active",
      force_password_change: false,
    },
  });
  expect(created.ok()).toBeTruthy();
  const userId = (await created.json()).user.id;
  try {
    const adminLogout = await page.request.post("/api/admin/auth/logout", {
      headers: csrfHeaders(page.request),
    });
    expect(adminLogout.ok()).toBeTruthy();
    const login = await page.request.post("/api/admin/auth/login", {
      data: { username, password: "DesignViewerPassword123!", remember_me: false },
    });
    expect(login.ok()).toBeTruthy();
    const csrf = (await login.json()).user.csrf_token;
    await page.goto("/admin");
    await page.locator('body[data-admin-ready="true"]').waitFor();
    await openPanel(page, "Design");
    for (const selector of ["#discard-design", "#save-draft", "#publish-design", "#builder-discard-button", "#builder-save-button", "#builder-publish-button"]) {
      await expect(page.locator(selector)).toBeHidden();
    }

    const design = await page.request.get(`/api/admin/properties/${propertyId}/design`);
    expect(design.ok()).toBeTruthy();
    const draft = (await design.json()).draft;
    const headers = { "X-CSRF-Token": csrf };
    const save = await page.request.put(`/api/admin/properties/${propertyId}/design/draft`, {
      headers,
      data: { config: draft },
    });
    const discard = await page.request.post(`/api/admin/properties/${propertyId}/design/discard`, { headers });
    const publish = await page.request.post(`/api/admin/properties/${propertyId}/design/publish`, { headers });
    for (const response of [save, discard, publish]) {
      expect(response.status()).toBe(403);
      expect((await response.json()).detail).toBe("Permission required: concierge.edit");
    }
  } finally {
    await request.delete(`/api/admin/users/${userId}`, { headers: csrfHeaders(request) });
  }
});

test("builder copies another property's published design into the selected property's draft", async ({ page }) => {
  test.skip(test.info().project.name !== "chromium", "Builder copy flow runs once in desktop Chromium.");
  let initialDraft = null;
  let cloneRequest = null;

  await page.route("**/api/admin/properties", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.properties ||= [];
    if (!payload.properties.some((item) => item.property_id === "design-source")) {
      payload.properties.push({ property_id: "design-source", hotel_name: "Source Property" });
    }
    await route.fulfill({
      status: response.status(),
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
  await page.route("**/api/admin/properties/*/design", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    initialDraft = payload.draft;
    await route.fulfill({
      status: response.status(),
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
  await page.route("**/api/admin/properties/*/design/clone", async (route) => {
    cloneRequest = route.request().postDataJSON();
    const draft = structuredClone(initialDraft);
    draft.welcome.headline = "Copied source design";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "draft_saved",
        source_property_id: cloneRequest.source_property_id,
        draft,
        revision: Number(cloneRequest.expected_revision) + 1,
      }),
    });
  });

  await page.goto("/admin");
  await openPanel(page, "Design");
  await page.locator("#builder-templates-button").click();
  await page.locator("#builder-clone-source-property").selectOption("design-source");
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("#builder-clone-property-button").click();

  await expect(page.locator("#builder-save-status")).toHaveText("Saved · cloned draft");
  await expect.poll(() => cloneRequest?.source_property_id).toBe("design-source");
  expect(cloneRequest.expected_revision).toBeGreaterThan(0);
});

test("admin: visual builder renders guest sections and supports direct editing, history, templates, devices, and draft save", async ({ page, request }) => {
  test.skip(test.info().project.name !== "chromium", "Builder interaction workflow runs once in desktop Chromium.");
  const builderPageErrors = [];
  page.on("pageerror", (error) => builderPageErrors.push(error.message));
  const propertyId = await getFirstPropertyId(request);
  const initialResponse = await request.get(`/api/admin/properties/${propertyId}/design`);
  expect(initialResponse.ok()).toBeTruthy();
  const initial = await initialResponse.json();

  try {
    await page.goto("/admin");
    await openPanel(page, "Design");
    const canvas = page.locator("#builder-canvas");
    const initialCount = await canvas.locator(".builder-canvas-section").count();
    await expect(canvas.locator(".builder-guest-page")).toBeVisible();
    await expect(canvas.locator(".builder-live-header")).toBeVisible();
    await expect(page.locator("#builder-page-settings")).toBeVisible();
    await expect(page.locator("#builder-inspector-tabs")).toBeHidden();
    await expect(page.locator("#builder-section-layers > li")).toHaveCount(initialCount);
    await page.locator("#builder-component-search").fill("Carousel");
    await expect(page.locator('[data-builder-add="carousel"]')).toBeVisible();
    await page.locator("#builder-component-search").fill("");
    await page.locator('[data-builder-add="heading"]').click();
    const headingCard = canvas.locator('.builder-canvas-section[data-builder-section^="heading-"]').last();
    await expect(headingCard).toBeVisible();
    await expect(page.locator(".builder-inspector-tabs [data-builder-tab='animation']")).toBeVisible();
    await page.locator('#builder-inspector [data-builder-field="text"]').fill("A configurable page heading");
    await expect(canvas).toContainText("A configurable page heading");

    const duplicateButton = headingCard.locator('[data-builder-action="duplicate"]');
    await duplicateButton.scrollIntoViewIfNeeded();
    await duplicateButton.click();
    expect(builderPageErrors).toEqual([]);
    await expect(canvas.locator('.builder-canvas-section[data-builder-section^="heading-"]')).toHaveCount(2);
    const ids = await canvas.locator('.builder-canvas-section[data-builder-section^="heading-"]').evaluateAll((cards) => cards.map((card) => card.dataset.builderSection));
    expect(new Set(ids).size).toBe(2);
    const duplicate = canvas.locator(`.builder-canvas-section[data-builder-section="${ids[1]}"]`);
    await duplicate.locator('[data-builder-action="toggle"]').click();
    await expect(duplicate).toHaveClass(/is-hidden/);
    await duplicate.locator('[data-builder-action="toggle"]').click();
    await expect(duplicate).not.toHaveClass(/is-hidden/);
    const duplicateLayer = page.locator(`#builder-section-layers > li:has([data-builder-layer-select="${ids[1]}"])`);
    await page.locator('[data-builder-library-tab="layers"]').click();
    await duplicateLayer.locator(".builder-layer-menu > summary", {}).click();
    await duplicateLayer.getByRole("button", { name: "Move up", exact: true }).click();
    let sectionPositions = await canvas.locator(".builder-canvas-section").evaluateAll((sections) => Object.fromEntries(sections.map((section, index) => [section.dataset.builderSection, index])));
    expect(sectionPositions[ids[1]]).toBe(sectionPositions[ids[0]] - 1);
    await duplicateLayer.locator(".builder-layer-menu > summary", {}).click();
    await duplicateLayer.getByRole("button", { name: "Move down", exact: true }).click();
    sectionPositions = await canvas.locator(".builder-canvas-section").evaluateAll((sections) => Object.fromEntries(sections.map((section, index) => [section.dataset.builderSection, index])));
    expect(sectionPositions[ids[1]]).toBe(sectionPositions[ids[0]] + 1);
    await page.locator('[data-builder-library-tab="components"]').click();

    await page.locator('[data-builder-device="tablet"]').click();
    await expect(page.locator('[data-builder-device="tablet"]')).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#builder-page-size-label")).toContainText("768 px");
    await expect.poll(() => canvas.evaluate((element) => element.getBoundingClientRect().width)).toBeLessThanOrEqual(768);
    await page.locator('[data-builder-device="mobile"]').click();
    await expect(page.locator('[data-builder-device="mobile"]')).toHaveAttribute("aria-pressed", "true");
    await expect.poll(() => canvas.evaluate((element) => element.getBoundingClientRect().width)).toBeLessThanOrEqual(390);

    await page.locator('[data-builder-tab="animation"]').click();
    await page.locator('#builder-inspector [data-builder-field="entrance"]').selectOption("fade_up");
    await page.locator('#builder-inspector [data-builder-field="delay"]').selectOption("200");
    await expect(duplicate.locator(".builder-guest-component")).toHaveAttribute("data-animation", "fade_up");
    await page.locator('[data-builder-tab="style"]').click();
    await page.locator('#builder-inspector [data-builder-field="radius"]').selectOption("large");
    await page.locator('[data-builder-tab="layout"]').click();
    await page.locator('#builder-inspector [data-builder-field="mobile_behavior"]').selectOption("scroll");
    await page.locator('[data-builder-tab="content"]').click();
    await duplicate.locator('[data-builder-action="delete"]').click();
    await expect(canvas.locator('.builder-canvas-section[data-builder-section^="heading-"]')).toHaveCount(1);
    expect(await canvas.locator(".builder-canvas-section").count()).toBe(initialCount + 1);

    await page.locator("#builder-undo-button").click();
    await expect(canvas.locator('.builder-canvas-section[data-builder-section^="heading-"]')).toHaveCount(2);
    await page.locator("#builder-redo-button").click();
    await expect(canvas.locator('.builder-canvas-section[data-builder-section^="heading-"]')).toHaveCount(1);

    const heroSection = canvas.locator('.builder-canvas-section:has(.experience-hero)').first();
    await heroSection.locator(".builder-guest-component").click();
    await page.locator('#builder-inspector [data-builder-add-button="hero"]').click();
    await heroSection.locator('.builder-guest-component [data-builder-select="button"]').first().click();
    await expect(page.locator("#builder-inspector-title")).toHaveText("Button");
    await page.locator('#builder-inspector [data-builder-field="type"]').selectOption("external_url");
    await page.locator('#builder-inspector [data-builder-field="url"]').fill("https://example.org/guest");
    await page.locator('#builder-inspector [data-builder-field="open_in"]').selectOption("new_tab");

    page.once("dialog", (dialog) => dialog.accept());
    await page.locator("#builder-templates-button").click();
    await page.locator('[data-builder-template="elegant"]').click();
    await expect(canvas.locator(".builder-canvas-section")).toHaveCount(5);
    await expect(page.locator("#builder-save-status")).toHaveText("Unsaved changes");
    await page.locator("#builder-preview-button").click();
    await expect(page.getByText("The center canvas is the live preview of this draft.")).toBeVisible();

    await page.locator("#builder-save-button").click();
    await expect(page.getByText("Draft saved.")).toBeVisible();
    const savedResponse = await request.get(`/api/admin/properties/${propertyId}/design`);
    const saved = await savedResponse.json();
    expect(saved.draft.pages[0].sections.some((section) => section.type === "restaurant")).toBe(true);
    expect(saved.published.pages[0].sections.some((section) => section.type === "restaurant")).toBe(false);
  } finally {
    const latest = await request.get(`/api/admin/properties/${propertyId}/design`);
    const current = await latest.json();
    await request.put(`/api/admin/properties/${propertyId}/design/draft`, {
      headers: csrfHeaders(request),
      data: { config: initial.draft, expected_revision: current.revision },
    });
  }
});

test("admin: layout templates apply complete themes, preserve custom draft colors, and publish to the guest UI", async ({ page, request }, testInfo) => {
  test.skip(test.info().project.name !== "chromium", "Theme switching and responsive viewport evidence runs once in desktop Chromium.");
  test.setTimeout(120_000);
  const propertyId = await getFirstPropertyId(request);
  const initialResponse = await request.get(`/api/admin/properties/${propertyId}/design`);
  expect(initialResponse.ok()).toBeTruthy();
  const initial = await initialResponse.json();
  const otherPropertyId = `e2e-theme-scope-${Date.now().toString(36)}`;
  const otherCreated = await request.put(`/api/admin/properties/${otherPropertyId}`, {
    headers: csrfHeaders(request),
    data: { property_id: otherPropertyId, hotel_name: "Theme Isolation Property", timezone: "UTC" },
  });
  expect(otherCreated.ok(), await otherCreated.text()).toBeTruthy();
  const otherInitial = await request.get(`/api/admin/properties/${otherPropertyId}/design`).then((response) => response.json());

  try {
    page.on("dialog", (dialog) => dialog.accept());
    await page.goto("/admin");
    await openPanel(page, "Design");
    const canvas = page.locator("#builder-canvas");
    const canvasTokens = () => canvas.evaluate((element) => {
      const style = getComputedStyle(element);
      return Object.fromEntries(["--builder-page-bg", "--builder-page-surface", "--builder-page-heading", "--builder-page-primary", "--builder-page-secondary", "--builder-page-button-text", "--builder-page-border", "--builder-page-hover", "--builder-page-focus", "--builder-page-font", "--builder-page-radius"].map((name) => [name, style.getPropertyValue(name).trim()]));
    });

    await page.locator("#builder-templates-button").click();
    await page.locator('[data-builder-template="luxury"]').click();
    const luxuryTokens = await canvasTokens();
    expect(luxuryTokens["--builder-page-bg"]).toBe("#f7f3e9");
    expect(luxuryTokens["--builder-page-primary"]).toBe("#102f29");
    expect(luxuryTokens["--builder-page-border"]).toBe("#d8d1c2");

    await page.locator("#builder-templates-button").click();
    await page.locator('[data-builder-template="business"]').click();
    const businessTokens = await canvasTokens();
    expect(businessTokens["--builder-page-bg"]).toBe("#edf2f8");
    expect(businessTokens["--builder-page-bg"]).not.toBe(luxuryTokens["--builder-page-bg"]);
    expect(businessTokens["--builder-page-primary"]).toBe("#101c32");
    expect(businessTokens["--builder-page-secondary"]).toBe("#20375a");
    expect(businessTokens["--builder-page-border"]).toBe("#cdd6e2");
    expect(businessTokens["--builder-page-radius"]).toBe("12px");

    await page.locator("#builder-templates-button").click();
    await page.locator("#builder-preserve-theme-input").check();
    await page.locator('[data-builder-template="resort"]').click();
    expect(await canvasTokens()).toMatchObject({ "--builder-page-bg": "#edf2f8", "--builder-page-primary": "#101c32" });
    await page.locator("#builder-templates-button").click();
    await page.locator("#builder-preserve-theme-input").uncheck();
    await page.locator('[data-builder-template="business"]').click();

    for (const device of ["desktop", "tablet", "mobile"]) {
      await page.locator(`[data-builder-device="${device}"]`).click();
      await expect(page.locator(`[data-builder-device="${device}"]`)).toHaveAttribute("aria-pressed", "true");
      expect(await canvasTokens()).toMatchObject({
        "--builder-page-bg": "#edf2f8",
        "--builder-page-primary": "#101c32",
        "--builder-page-border": "#cdd6e2",
      });
    }

    await canvas.evaluate((element) => element.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    await expect(page.locator("#builder-page-settings")).toBeVisible();
    await openDesignGroup(page, "theme");
    await page.locator("#button-color-input").fill("#123456");
    await expect.poll(async () => (await canvasTokens())["--builder-page-primary"]).toBe("#123456");
    await page.locator("#builder-save-button").click();
    await expect(page.getByText("Draft saved.")).toBeVisible();
    const saved = await request.get(`/api/admin/properties/${propertyId}/design`).then((response) => response.json());
    expect(saved.draft.theme).toMatchObject({ paletteId: "midnight-sapphire", layoutTemplateId: "business", primaryColor: "#123456", buttonColor: "#123456" });
    expect(saved.published).toEqual(initial.published);

    await page.goto("/admin");
    await openPanel(page, "Design");
    await openDesignGroup(page, "theme");
    await expect(page.locator("#button-color-input")).toHaveValue("#123456");
    await expect.poll(async () => (await canvasTokens())["--builder-page-primary"]).toBe("#123456");

    await page.locator("#builder-publish-button").click();
    await expect(page.getByText(/Published guest chat v\d+\./)).toBeVisible();
    const published = await request.get(`/api/admin/properties/${propertyId}/design`).then((response) => response.json());
    expect(published.published.theme.primaryColor).toBe("#123456");
    const otherAfterPublish = await request.get(`/api/admin/properties/${otherPropertyId}/design`).then((response) => response.json());
    expect(otherAfterPublish.published).toEqual(otherInitial.published);

    const deletedOther = await request.delete(`/api/admin/properties/${otherPropertyId}`, { headers: csrfHeaders(request) });
    expect(deletedOther.ok(), await deletedOther.text()).toBeTruthy();

    const indexHtml = await request.get("/static/index.html").then((response) => response.text());
    const guestRoot = new URL("/", page.url()).toString();
    const guestProfile = {
      property_id: propertyId,
      name: "Published Theme Property",
      concierge_name: "Concierge",
      theme: { primary_color: "#123456", secondary_color: "#20375A", background: "#EDF2F8" },
      design: published.published,
      authentication: { enabled: false, enabled_types: [] },
      languages: ["en"],
      guest_modules: [],
      quick_actions: [],
      application: { default_language: "en" },
    };
    await page.route(guestRoot, (route) => route.fulfill({ status: 200, contentType: "text/html", body: indexHtml }));
    await page.route("**/api/hotel", (route) => route.fulfill({ json: guestProfile }));
    await page.route("**/api/guest/intro**", (route) => route.fulfill({ json: { mode: "none", first_visit_only: true, allow_skip: true } }));
    await page.route("**/api/session/start", (route) => route.fulfill({ json: { session_id: "theme-preview-session", property_id: propertyId } }));
    await page.route("**/api/guest/home**", (route) => route.fulfill({ json: { greeting: "Welcome", stay: { status: "unverified" }, cards: [], quick_actions: [], suggested_prompts: [], inventory: {} } }));
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto("/");
    await expect(page.locator(".concierge-shell")).toBeVisible();
    await expect.poll(() => page.locator("html").evaluate((element) => getComputedStyle(element).getPropertyValue("--primary-color").trim())).toBe("#123456");
    for (const width of [1920, 1366, 1024, 768, 390, 375]) {
      await page.setViewportSize({ width, height: 900 });
      const guestTokens = await page.locator("html").evaluate((element) => {
        const style = getComputedStyle(element);
        return {
          background: style.getPropertyValue("--background").trim(),
          primary: style.getPropertyValue("--primary-color").trim(),
          border: style.getPropertyValue("--border").trim(),
          heading: style.getPropertyValue("--heading-color").trim(),
        };
      });
      expect(guestTokens).toEqual({ background: "#edf2f8", primary: "#123456", border: "#cdd6e2", heading: "#101c32" });
      expect(await page.locator("body").evaluate((element) => element.scrollWidth)).toBeLessThanOrEqual(width + 1);
      if (width === 375 || width === 1366) await page.screenshot({ path: testInfo.outputPath(`published-theme-${width}.png`), fullPage: true });
    }
    expect(await page.locator("h1").first().evaluate((element) => getComputedStyle(element).fontFamily)).toContain("Inter");
    const buttonColor = await page.locator(".send-button").evaluate((element) => getComputedStyle(element).backgroundColor);
    expect(buttonColor).toBe("rgb(18, 52, 86)");

    await page.goto("/admin");
    await openPanel(page, "Design");
    await page.locator("#builder-templates-button").click();
    await page.locator("#reset-theme-template").click();
    await expect.poll(async () => (await canvasTokens())["--builder-page-primary"]).toBe("#101c32");
  } finally {
    const deletedOther = await request.delete(`/api/admin/properties/${otherPropertyId}`, { headers: csrfHeaders(request) });
    if (!deletedOther.ok() && deletedOther.status() !== 404) expect(deletedOther.ok(), await deletedOther.text()).toBeTruthy();
    const saveAtLatestRevision = async (config) => {
      let result;
      for (let attempt = 0; attempt < 4; attempt += 1) {
        const latest = await request.get(`/api/admin/properties/${propertyId}/design`).then((response) => response.json());
        result = await request.put(`/api/admin/properties/${propertyId}/design/draft`, {
          headers: csrfHeaders(request),
          data: { config, expected_revision: latest.revision },
        });
        if (result.ok() || result.status() !== 409) return result;
      }
      return result;
    };
    const resetPublished = await saveAtLatestRevision(initial.published);
    expect(resetPublished.ok(), await resetPublished.text()).toBeTruthy();
    let republished;
    for (let attempt = 0; attempt < 4; attempt += 1) {
      const beforeRepublish = await request.get(`/api/admin/properties/${propertyId}/design`).then((response) => response.json());
      republished = await request.post(`/api/admin/properties/${propertyId}/design/publish`, {
        headers: csrfHeaders(request),
        data: { expected_revision: beforeRepublish.revision },
      });
      if (republished.ok() || republished.status() !== 409) break;
    }
    expect(republished.ok(), await republished.text()).toBeTruthy();
    const resetDraft = await saveAtLatestRevision(initial.draft);
    expect(resetDraft.ok(), await resetDraft.text()).toBeTruthy();
  }
});

test("admin: five premium palettes persist and render accessibly on published desktop and mobile guest pages", async ({ page, request }, testInfo) => {
  test.skip(test.info().project.name !== "chromium", "Premium palette screenshots are captured once in desktop Chromium.");
  test.setTimeout(240_000);
  const propertyId = await getFirstPropertyId(request);
  const initialResponse = await request.get(`/api/admin/properties/${propertyId}/design`);
  expect(initialResponse.ok()).toBeTruthy();
  const initial = await initialResponse.json();
  const palettes = {
    "royal-emerald-gold": { name: "Royal Emerald & Gold", background: "#F7F3E9", primary: "#102F29", secondary: "#1D5145", accent: "#C5A46D", text: "#263D37", font: "Playfair Display" },
    "midnight-sapphire": { name: "Midnight Sapphire", background: "#EDF2F8", primary: "#101C32", secondary: "#20375A", accent: "#D7B98B", text: "#101C32", font: "Manrope" },
    "champagne-onyx": { name: "Champagne & Onyx", background: "#F5F0E7", primary: "#1D1C1A", secondary: "#39342F", accent: "#B99A70", text: "#1D1C1A", font: "Playfair Display" },
    "pearl-sage": { name: "Pearl & Sage", background: "#FAF8F3", primary: "#29483C", secondary: "#779487", accent: "#D4B99B", text: "#29483C", font: "Playfair Display" },
    "obsidian-copper": { name: "Obsidian & Copper", background: "#F3F0EA", primary: "#16191D", secondary: "#2A3037", accent: "#BA805D", text: "#16191D", font: "Manrope" },
  };
  const getContrast = (first, second) => {
    const luminance = (color) => {
      const values = [1, 3, 5].map((offset) => parseInt(color.slice(offset, offset + 2), 16) / 255).map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
      return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2];
    };
    const [lighter, darker] = [luminance(first), luminance(second)].sort((a, b) => b - a);
    return (lighter + 0.05) / (darker + 0.05);
  };
  let previousPublished = initial.published;
  let guestProfile;
  let guestProfileServed = false;
  page.on("dialog", (dialog) => dialog.accept());

  const saveAtLatestRevision = async (config) => {
    let result;
    for (let attempt = 0; attempt < 4; attempt += 1) {
      const latest = await request.get(`/api/admin/properties/${propertyId}/design`).then((response) => response.json());
      result = await request.put(`/api/admin/properties/${propertyId}/design/draft`, {
        headers: csrfHeaders(request),
        data: { config, expected_revision: latest.revision },
      });
      if (result.ok() || result.status() !== 409) return result;
    }
    return result;
  };

  try {
    await page.goto("/admin");
    await openPanel(page, "Design");
    const canvas = page.locator("#builder-canvas");
    const paletteCards = page.locator("[data-design-preset]");
    await page.locator("#builder-templates-button").click();
    await expect(paletteCards).toHaveCount(5);
    const indexHtml = await request.get("/static/index.html").then((response) => response.text());
    const guestRoot = new URL("/", page.url()).toString();
    await page.route(guestRoot, (route) => route.fulfill({ status: 200, contentType: "text/html", body: indexHtml }));
    await page.route("**/api/hotel**", (route) => {
      guestProfileServed = true;
      return route.fulfill({ json: guestProfile });
    });
    await page.route("**/api/guest/intro**", (route) => route.fulfill({ json: { mode: "none", first_visit_only: true, allow_skip: true } }));
    await page.route("**/api/session/start", (route) => route.fulfill({ json: { session_id: "premium-palette-session", property_id: propertyId } }));
    await page.route("**/api/guest/home**", (route) => route.fulfill({ json: { greeting: "Welcome", stay: { status: "unverified" }, cards: [], quick_actions: [], suggested_prompts: [], inventory: {} } }));

    for (const [paletteId, palette] of Object.entries(palettes)) {
      const card = page.locator(`[data-design-preset="${paletteId}"]`);
      await expect(card).toContainText(palette.name);
      await expect(card.locator(".builder-palette-description")).not.toBeEmpty();
      const swatches = await card.locator(".builder-palette-swatch").evaluateAll((elements) => elements.map((element) => element.style.getPropertyValue("--palette-swatch-color").toUpperCase()));
      expect(swatches).toEqual([palette.background, palette.primary, palette.secondary, palette.accent, palette.text]);
      await card.click();
      const previewTokens = await canvas.evaluate((element) => {
        const style = getComputedStyle(element);
        return Object.fromEntries(["--builder-page-bg", "--builder-page-primary", "--builder-page-secondary", "--builder-page-accent", "--builder-page-ink", "--builder-page-button-text", "--builder-page-secondary-button-text"].map((name) => [name, style.getPropertyValue(name).trim().toUpperCase()]));
      });
      expect(previewTokens).toMatchObject({
        "--builder-page-bg": palette.background,
        "--builder-page-primary": palette.primary,
        "--builder-page-secondary": palette.secondary,
        "--builder-page-accent": palette.accent,
        "--builder-page-ink": palette.text,
      });
      expect(card).toHaveAttribute("aria-pressed", "true");

      await page.locator("#builder-save-button").click();
      await expect(page.getByText("Draft saved.")).toBeVisible();
      const saved = await request.get(`/api/admin/properties/${propertyId}/design`).then((response) => response.json());
      expect(saved.draft.theme).toMatchObject({ paletteId, background: palette.background.toLowerCase(), primaryColor: palette.primary.toLowerCase(), secondaryColor: palette.secondary.toLowerCase(), accent: palette.accent.toLowerCase(), bodyColor: palette.text.toLowerCase() });
      expect(saved.draft.typography.headingFontFamily).toBe(palette.font);
      expect(saved.published).toEqual(previousPublished);

      await page.locator("#builder-publish-button").click();
      await expect(page.getByText(/Published guest chat v\d+\./)).toBeVisible();
      const publishedState = await request.get(`/api/admin/properties/${propertyId}/design`).then((response) => response.json());
      previousPublished = publishedState.published;
      expect(previousPublished.theme.paletteId).toBe(paletteId);
      expect(previousPublished.typography.headingFontFamily).toBe(palette.font);

      guestProfile = {
        property_id: propertyId,
        name: "Published Palette Property",
        concierge_name: "Concierge",
        theme: { primary_color: palette.primary, secondary_color: palette.secondary, background: palette.background },
        design: previousPublished,
        authentication: { enabled: false, enabled_types: [] },
        languages: ["en"],
        guest_modules: [],
        quick_actions: [],
        application: { default_language: "en" },
      };
      guestProfileServed = false;
      await page.goto("/");
      await expect(page.locator(".concierge-shell")).toBeVisible();
      expect(guestProfileServed).toBeTruthy();
      await expect.poll(() => page.locator("html").evaluate((element) => getComputedStyle(element).getPropertyValue("--primary-color").trim().toUpperCase())).toBe(palette.primary);
      await expect.poll(() => page.locator("html").evaluate((element) => getComputedStyle(element).getPropertyValue("--heading-font-family"))).toContain(palette.font);
      for (const [width, label] of [[1366, "desktop"], [375, "mobile"]]) {
        await page.setViewportSize({ width, height: 950 });
        const guestTokens = await page.locator("html").evaluate((element) => {
          const style = getComputedStyle(element);
          return Object.fromEntries(["--background", "--primary-color", "--secondary-color", "--accent", "--body-color", "--button-text", "--secondary-button-text", "--focus-color"].map((name) => [name, style.getPropertyValue(name).trim().toUpperCase()]));
        });
        expect(guestTokens).toMatchObject({
          "--background": palette.background,
          "--primary-color": palette.primary,
          "--secondary-color": palette.secondary,
          "--accent": palette.accent,
          "--body-color": palette.text,
        });
        expect(getContrast(guestTokens["--body-color"], guestTokens["--background"])).toBeGreaterThanOrEqual(4.5);
        expect(getContrast(guestTokens["--button-text"], guestTokens["--primary-color"])).toBeGreaterThanOrEqual(4.5);
        expect(getContrast(guestTokens["--secondary-button-text"], guestTokens["--secondary-color"])).toBeGreaterThanOrEqual(4.5);
        expect(getContrast(guestTokens["--focus-color"], guestTokens["--background"])).toBeGreaterThanOrEqual(3);
        expect(await page.locator("body").evaluate((element) => element.scrollWidth)).toBeLessThanOrEqual(width + 1);
        expect(await page.locator(".send-button").evaluate((element) => getComputedStyle(element).backgroundColor)).toBe(`rgb(${parseInt(palette.primary.slice(1, 3), 16)}, ${parseInt(palette.primary.slice(3, 5), 16)}, ${parseInt(palette.primary.slice(5, 7), 16)})`);
        expect(await page.locator(".home-hero h1").evaluate((element) => getComputedStyle(element).fontFamily)).toContain(palette.font);
        await page.screenshot({ path: testInfo.outputPath(`palette-${paletteId}-${label}.png`), fullPage: true });
      }
      await page.goto("/admin");
      await openPanel(page, "Design");
      await page.locator("#builder-templates-button").click();
      await expect(page.locator(`[data-design-preset="${paletteId}"]`)).toHaveAttribute("aria-pressed", "true");
    }
  } finally {
    const restorePublishedDraft = await saveAtLatestRevision(initial.published);
    expect(restorePublishedDraft.ok(), await restorePublishedDraft.text()).toBeTruthy();
    const latest = await request.get(`/api/admin/properties/${propertyId}/design`).then((response) => response.json());
    const republished = await request.post(`/api/admin/properties/${propertyId}/design/publish`, {
      headers: csrfHeaders(request),
      data: { expected_revision: latest.revision },
    });
    expect(republished.ok(), await republished.text()).toBeTruthy();
    const restoreDraft = await saveAtLatestRevision(initial.draft);
    expect(restoreDraft.ok(), await restoreDraft.text()).toBeTruthy();
  }
});

test("admin: AI Chat Designer switches presets, persists per-property drafts, publishes, and renders responsively", async ({ page, request }, testInfo) => {
  test.skip(test.info().project.name !== "chromium", "Chat Designer screenshots are captured once in desktop Chromium.");
  test.setTimeout(240_000);
  const propertyId = await getFirstPropertyId(request);
  const initialResponse = await request.get(`/api/admin/properties/${propertyId}/design`);
  expect(initialResponse.ok()).toBeTruthy();
  const initial = await initialResponse.json();
  const properties = (await request.get("/api/admin/properties").then((response) => response.json())).properties;
  const otherProperty = properties.find((property) => property.property_id !== propertyId);
  const otherBefore = otherProperty
    ? await request.get(`/api/admin/properties/${otherProperty.property_id}/design`).then((response) => response.json())
    : null;
  const styles = {
    luxury: { name: "Luxury Chat", header: "#102F29" },
    chatgpt: { name: "ChatGPT Inspired", header: "#FFFFFF" },
    boutique: { name: "Boutique Chat", header: "#FFFEFB" },
    midnight: { name: "Midnight Chat", header: "#101316" },
  };
  let published = initial.published;
  let guestProfile;
  const saveAtLatestRevision = async (config) => {
    let result;
    for (let attempt = 0; attempt < 4; attempt += 1) {
      const latest = await request.get(`/api/admin/properties/${propertyId}/design`).then((response) => response.json());
      result = await request.put(`/api/admin/properties/${propertyId}/design/draft`, {
        headers: csrfHeaders(request),
        data: { config, expected_revision: latest.revision },
      });
      if (result.ok() || result.status() !== 409) return result;
    }
    return result;
  };
  page.on("dialog", (dialog) => dialog.accept());
  try {
    await page.goto("/admin");
    await openPanel(page, "Design");
    await openDesignGroup(page, "chat");
    const cards = page.locator("#chat-preset-options [data-chat-style]");
    await expect(cards).toHaveCount(4);
    await expect(page.locator("#chat-preset-options .chat-preset-swatches i")).toHaveCount(20);
    await page.locator("#chat-inherit-theme-input").uncheck();
    await page.setViewportSize({ width: 1404, height: 1200 });
    for (const [styleId, style] of Object.entries(styles)) {
      const card = page.locator(`#chat-preset-options [data-chat-style="${styleId}"]`);
      await expect(card).toContainText(style.name);
      await expect(card.locator("small")).not.toBeEmpty();
      await card.click();
      await expect(card).toHaveAttribute("aria-pressed", "true");
      const tokens = await page.locator("#builder-canvas").evaluate((element) => {
        const computed = getComputedStyle(element);
        return Object.fromEntries(["--chat-header-bg", "--chat-guest-bg", "--chat-assistant-bg", "--chat-input-bg", "--chat-send-bg"].map((name) => [name, computed.getPropertyValue(name).trim().toUpperCase()]));
      });
      expect(tokens["--chat-header-bg"]).toBe(style.header);
      expect(tokens["--chat-guest-bg"]).not.toBe("");
      expect(tokens["--chat-assistant-bg"]).not.toBe("");
      const swatches = await card.locator(".chat-preset-swatches i").count();
      expect(swatches).toBe(5);
      await page.locator("[data-builder-device=desktop]").click();
      await page.locator(".builder-chat-preview-window").screenshot({ path: testInfo.outputPath(`chat-${styleId}-desktop.png`) });
      await page.locator("[data-builder-device=mobile]").click();
      await expect(page.locator("#builder-canvas")).toHaveAttribute("data-device", "mobile");
      await page.locator(".builder-chat-preview-window").screenshot({ path: testInfo.outputPath(`chat-${styleId}-mobile.png`) });
    }

    await page.locator("#chat-display-mode-input").selectOption("fullscreen");
    await expect(page.locator("#builder-canvas")).toHaveAttribute("data-chat-mode", "fullscreen");
    await expect(page.locator(".builder-chat-preview")).toHaveClass(/is-fullscreen/);
    await page.locator("#chat-display-mode-input").selectOption("floating");
    await page.locator("#chat-assistant-name-input").fill("Maya");
    await page.locator("#chat-welcome-input").fill("Welcome to your stay. How can I help?");
    await page.locator("#chat-prompts-input").fill("Explore dining\nFind the spa");
    await page.locator("#chat-timestamps-input").check();
    await page.locator("#chat-token-sendBackground").evaluate((element) => {
      element.value = "#123456";
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await page.locator("[data-builder-device=desktop]").click();
    const desktopPreview = page.locator(".builder-chat-preview");
    await expect(desktopPreview).toHaveAttribute("data-chat-style", "midnight");
    await page.locator("#builder-save-button").click();
    await expect(page.getByText("Draft saved.")).toBeVisible();
    const saved = await request.get(`/api/admin/properties/${propertyId}/design`).then((response) => response.json());
    expect(saved.draft.chat).toMatchObject({
      presetId: "midnight", paletteId: "midnight", inheritLandingTheme: false, displayMode: "floating",
      assistantName: "Maya", welcomeMessage: "Welcome to your stay. How can I help?", suggestedPrompts: ["Explore dining", "Find the spa"], showTimestamps: true,
    });
    expect(saved.draft.chat.tokens.sendBackground.toLowerCase()).toBe("#123456");
    expect(saved.published).toEqual(initial.published);
    if (otherBefore) {
      const otherAfterDraft = await request.get(`/api/admin/properties/${otherProperty.property_id}/design`).then((response) => response.json());
      expect(otherAfterDraft.draft).toEqual(otherBefore.draft);
      expect(otherAfterDraft.published).toEqual(otherBefore.published);
    }

    await page.locator("#builder-publish-button").click();
    await expect(page.getByText(/Published guest chat v\d+\./)).toBeVisible();
    const publishedState = await request.get(`/api/admin/properties/${propertyId}/design`).then((response) => response.json());
    published = publishedState.published;
    expect(published.chat).toMatchObject({ displayMode: "floating", assistantName: "Maya", tokens: { sendBackground: "#123456" } });

    const indexHtml = await request.get("/static/index.html").then((response) => response.text());
    const guestRoot = new URL("/", page.url()).toString();
    await page.route(guestRoot, (route) => route.fulfill({ status: 200, contentType: "text/html", body: indexHtml }));
    guestProfile = {
      property_id: propertyId,
      name: "Chat Designer QA Property",
      concierge_name: "Concierge",
      design: published,
      authentication: { enabled: false, enabled_types: [] },
      languages: ["en"],
      guest_modules: [],
      quick_actions: [],
      application: { default_language: "en" },
    };
    await page.route("**/api/hotel**", (route) => route.fulfill({ json: guestProfile }));
    await page.route("**/api/guest/intro**", (route) => route.fulfill({ json: { mode: "none", first_visit_only: true, allow_skip: true } }));
    await page.route("**/api/session/start", (route) => route.fulfill({ json: { session_id: "chat-designer-session", property_id: propertyId } }));
    await page.route("**/api/session/resume", (route) => route.fulfill({ json: { session_id: "chat-designer-session", property_id: propertyId } }));
    await page.route("**/api/guest/home**", (route) => route.fulfill({ json: { greeting: "Welcome", stay: { status: "unverified" }, cards: [], quick_actions: [], suggested_prompts: [], inventory: {} } }));
    await page.route("**/api/guest/personalization**", (route) => route.fulfill({ json: { enabled: false, preferences: [] } }));
    await page.goto("/");
    await expect(page.locator("#chat-launcher")).toBeVisible();
    await expect.poll(() => page.locator("html").getAttribute("data-chat-mode")).toBe("floating");
    await expect.poll(() => page.locator("#chat-assistant-name").textContent()).toBe("Maya");
    const publishedTokens = await page.locator("html").evaluate((element) => {
      const style = getComputedStyle(element);
      return Object.fromEntries(["--chat-send-bg", "--chat-guest-bg", "--chat-assistant-bg", "--chat-input-bg"].map((name) => [name, style.getPropertyValue(name).trim().toUpperCase()]));
    });
    expect(publishedTokens["--chat-send-bg"]).toBe("#123456");
    await page.locator("#chat-launcher").click();
    await expect(page.locator("body")).toHaveClass(/chat-floating-open/);
    await expect(page.locator("#concierge-view")).toBeVisible();
    const welcomeContrast = await page.locator("#concierge-view").evaluate((element) => {
      const background = getComputedStyle(document.documentElement).getPropertyValue("--chat-window-bg").trim();
      const heading = getComputedStyle(element.querySelector(".welcome-state h1")).color;
      const subtitle = getComputedStyle(element.querySelector(".welcome-subtitle")).color;
      const input = element.querySelector(".composer textarea");
      const inputStyle = getComputedStyle(input);
      const composerBackground = getComputedStyle(element.querySelector(".composer")).backgroundColor;
      const rgbToHex = (value) => `#${value.match(/\d+/g).slice(0, 3).map((channel) => Number(channel).toString(16).padStart(2, "0")).join("")}`;
      return {
        heading: window.ConciergeTheme.contrastRatio(rgbToHex(heading), background),
        subtitle: window.ConciergeTheme.contrastRatio(rgbToHex(subtitle), background),
        inputBackground: inputStyle.backgroundColor,
        composerBackground: rgbToHex(composerBackground),
        inputToken: getComputedStyle(document.documentElement).getPropertyValue("--chat-input-bg").trim().toLowerCase(),
      };
    });
    expect(welcomeContrast.heading).toBeGreaterThanOrEqual(4.5);
    expect(welcomeContrast.subtitle).toBeGreaterThanOrEqual(4.5);
    expect(welcomeContrast.inputBackground).toBe("rgba(0, 0, 0, 0)");
    expect(welcomeContrast.composerBackground).toBe(welcomeContrast.inputToken);
    await page.locator("#concierge-view").screenshot({ path: testInfo.outputPath("chat-published-floating-desktop.png") });
    await page.setViewportSize({ width: 375, height: 812 });
    await expect(page.locator("#concierge-view")).toBeVisible();
    expect(await page.locator("body").evaluate((element) => element.scrollWidth)).toBeLessThanOrEqual(376);
    await page.locator("#concierge-view").screenshot({ path: testInfo.outputPath("chat-published-floating-mobile.png") });
    await page.locator("#chat-expand-button").click();
    await expect(page.locator("body")).toHaveClass(/chat-fullscreen-open/);
    const fullscreenBounds = await page.locator("#concierge-view").boundingBox();
    expect(fullscreenBounds.x).toBe(0);
    expect(fullscreenBounds.y).toBe(0);
    expect(fullscreenBounds.width).toBe(375);
    expect(fullscreenBounds.height).toBe(812);
    await page.locator("#chat-minimize-button").click();
    await expect(page.locator("#chat-launcher")).toBeVisible();
    await page.evaluate((design) => {
      const chat = window.ConciergeTheme.applyChat(document.documentElement, { ...design, chat: { ...design.chat, displayMode: "embedded" } });
      document.querySelector("#chat-launcher").hidden = chat.displayMode !== "floating";
    }, published);
    await expect(page.locator("#chat-launcher")).toBeHidden();
    expect(await page.locator("#chat-launcher").evaluate((element) => getComputedStyle(element).display)).toBe("none");
  } finally {
    const restorePublishedDraft = await saveAtLatestRevision(initial.published);
    expect(restorePublishedDraft.ok(), await restorePublishedDraft.text()).toBeTruthy();
    const latest = await request.get(`/api/admin/properties/${propertyId}/design`).then((response) => response.json());
    const republished = await request.post(`/api/admin/properties/${propertyId}/design/publish`, {
      headers: csrfHeaders(request),
      data: { expected_revision: latest.revision },
    });
    expect(republished.ok(), await republished.text()).toBeTruthy();
    const restoreDraft = await saveAtLatestRevision(initial.draft);
    expect(restoreDraft.ok(), await restoreDraft.text()).toBeTruthy();
  }
});

test("admin: empty guest page offers a clear, draft-safe starting point", async ({ page, request }, testInfo) => {
  test.skip(test.info().project.name !== "chromium", "Builder empty-state interaction is verified once in Chromium.");
  const propertyId = await getFirstPropertyId(request);
  const initialResponse = await request.get(`/api/admin/properties/${propertyId}/design`);
  expect(initialResponse.ok()).toBeTruthy();
  const initial = await initialResponse.json();
  const emptyDraft = structuredClone(initial.draft);
  const home = emptyDraft.pages.find((item) => item.id === "home");
  expect(home).toBeTruthy();
  home.sections = [];
  const seeded = await request.put(`/api/admin/properties/${propertyId}/design/draft`, {
    headers: csrfHeaders(request),
    data: { config: emptyDraft, expected_revision: initial.revision },
  });
  expect(seeded.ok(), await seeded.text()).toBeTruthy();

  try {
    await page.setViewportSize({ width: 1404, height: 954 });
    await page.goto("/admin");
    await openPanel(page, "Design");
    const canvas = page.locator("#builder-canvas");
    const emptyState = canvas.locator(".builder-empty-canvas");
    await expect(emptyState).toBeVisible();
    await expect(emptyState.getByRole("heading", { name: "Start building your Home page" })).toBeVisible();
    await expect(emptyState).toContainText("guests see changes only after you publish");
    await expect(canvas.locator(".builder-chat-preview-toolbar small")).toContainText(/separate from page sections/i);
    await expect(canvas.locator(".builder-chat-preview-window")).toBeVisible();
    await expect(canvas.locator(".builder-chat-message")).toHaveCount(3);

    await page.locator('[data-builder-device="mobile"]').click();
    await expect(emptyState.getByRole("button", { name: "Choose a page layout" })).toBeVisible();
    await expect(emptyState.getByRole("button", { name: "Add a hero section" })).toBeVisible();
    await canvas.screenshot({ path: testInfo.outputPath("builder-empty-mobile.png") });

    await emptyState.getByRole("button", { name: "Choose a page layout" }).click();
    await expect(page.locator("#builder-template-menu")).toBeVisible();
    await expect(page.locator("#builder-templates-button")).toHaveAttribute("aria-expanded", "true");
    await page.locator("#builder-templates-button").click();
    await emptyState.getByRole("button", { name: "Add a hero section" }).click();
    await expect(canvas.locator('.builder-canvas-section[data-builder-section^="hero-"]')).toHaveCount(1);
    await expect(page.locator("#builder-layer-count")).toHaveText("1");
    const afterEditing = await request.get(`/api/admin/properties/${propertyId}/design`).then((response) => response.json());
    expect(afterEditing.draft.pages.find((item) => item.id === "home").sections).toEqual([]);
    expect(afterEditing.published).toEqual(initial.published);
  } finally {
    const latestResponse = await request.get(`/api/admin/properties/${propertyId}/design`);
    const latest = await latestResponse.json();
    const restore = await request.put(`/api/admin/properties/${propertyId}/design/draft`, {
      headers: csrfHeaders(request),
      data: { config: initial.draft, expected_revision: latest.revision },
    });
    expect(restore.ok(), await restore.text()).toBeTruthy();
  }
});

test("admin: builder visual evidence covers devices, inspector tabs, image upload, and drag reorder", async ({ page, request }, testInfo) => {
  test.skip(test.info().project.name !== "chromium", "Builder screenshot evidence is captured once in desktop Chromium.");
  test.setTimeout(120_000);
  const propertyId = await getFirstPropertyId(request);
  const initialResponse = await request.get(`/api/admin/properties/${propertyId}/design`);
  expect(initialResponse.ok()).toBeTruthy();
  const initial = await initialResponse.json();
  const screenshot = async (name) => page.screenshot({ path: testInfo.outputPath(`builder-${name}.png`), fullPage: true });
  const pointerDrag = async (source, target, targetOffset = { x: 20, y: 12 }, expectDropIndicator = false, indicatorScreenshot = "") => {
    await source.scrollIntoViewIfNeeded();
    const sourceBox = await source.boundingBox();
    let targetBox = await target.boundingBox();
    expect(sourceBox).toBeTruthy();
    expect(targetBox).toBeTruthy();
    await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(sourceBox.x + sourceBox.width / 2 + 12, sourceBox.y + sourceBox.height / 2 + 5, { steps: 3 });
    const scrollBox = await page.locator(".builder-canvas-scroll").boundingBox();
    const viewportHeight = await page.evaluate(() => window.innerHeight);
    const visibleTop = Math.max(0, scrollBox.y);
    const visibleBottom = Math.min(viewportHeight, scrollBox.y + scrollBox.height);
    if (targetBox.y < visibleTop || targetBox.y > visibleBottom) {
      const edgeX = Math.min(Math.max(sourceBox.x + sourceBox.width / 2, scrollBox.x + 12), scrollBox.x + scrollBox.width - 12);
      const edgeY = targetBox.y < visibleTop ? visibleTop + 10 : visibleBottom - 10;
      for (let attempt = 0; attempt < 14; attempt += 1) {
        await page.mouse.move(edgeX, edgeY + (attempt % 2), { steps: 1 });
        await page.waitForTimeout(24);
        targetBox = await target.boundingBox();
        if (targetBox.y >= visibleTop && targetBox.y <= visibleBottom) break;
      }
    }
    targetBox = await target.boundingBox();
    await page.mouse.move(targetBox.x + targetOffset.x, targetBox.y + targetOffset.y, { steps: 8 });
    if (expectDropIndicator) {
      const indicators = page.locator("#builder-canvas .drop-before, #builder-canvas .drop-after, #builder-canvas [data-builder-action-item].drop-after, #builder-section-layers .drop-before, #builder-section-layers .drop-after");
      await expect(indicators).toHaveCount(1);
      if (indicatorScreenshot) await screenshot(indicatorScreenshot);
    }
    await page.mouse.up();
  };

  try {
    await page.setViewportSize({ width: 1749, height: 1126 });
    await page.goto("/admin");
    await openPanel(page, "Design");
    const canvas = page.locator("#builder-canvas");
    await expect(canvas.locator(".builder-guest-page")).toBeVisible();
    await expect(page.locator("#builder-component-library")).toContainText("Hero");
    await screenshot("desktop");
    await screenshot("component-library");
    await page.locator("#builder-focus-button").click();
    await expect(page.locator(".experience-builder")).toHaveClass(/is-focus-mode/);
    await expect(page.locator(".builder-library-panel")).toBeHidden();
    await expect(page.locator("#builder-canvas")).toBeVisible();
    await screenshot("focus-mode");
    await page.locator("#builder-focus-button").click();

    await page.locator('[data-builder-library-tab="layers"]').click();
    await expect(page.locator("#builder-section-layers > li")).toHaveCount(await canvas.locator(".builder-canvas-section").count());
    await expect(page.locator("#builder-section-layers .builder-layer-drag-handle").first()).toBeVisible();
    await screenshot("layers");
    const firstLayer = page.locator("#builder-section-layers > li").first();
    const secondLayer = page.locator("#builder-section-layers > li").nth(1);
    const firstLayerId = await firstLayer.getAttribute("data-builder-layer-section");
    const secondLayerBox = await secondLayer.boundingBox();
    await pointerDrag(firstLayer.locator("[data-builder-layer-drag-handle]"), secondLayer, { x: 18, y: secondLayerBox.height - 2 }, true, "drop-indicator-layers");
    await expect(page.locator("#builder-section-layers > li").nth(1)).toHaveAttribute("data-builder-layer-section", firstLayerId);
    await page.locator('[data-builder-library-tab="components"]').click();
    await page.locator("#builder-templates-button").click();
    await screenshot("templates");
    await page.locator("#builder-templates-button").click();
    await screenshot("page-theme");

    const headerSection = canvas.locator('.builder-canvas-section:has(.builder-live-header)').first();
    if (await headerSection.count()) {
      const menuItem = headerSection.locator('.builder-guest-component [data-builder-select="header_item"][data-builder-item-id="menu"]');
      await expect(menuItem).toBeVisible();
      await menuItem.click();
      await expect(page.locator("#builder-inspector-title")).toHaveText("Header Element");
      await expect(page.locator('#builder-inspector [data-builder-field="show_menu"]')).toBeVisible();
      await screenshot("header-selected");
    }
    const existingNavigation = canvas.locator('.builder-canvas-section:has(.builder-live-bottom-nav)').first();
    if (await existingNavigation.count()) {
      const navigationSectionId = await existingNavigation.getAttribute("data-builder-section");
      await page.locator('[data-builder-library-tab="layers"]').click();
      await page.locator(`#builder-section-layers [data-builder-layer-select="${navigationSectionId}"]`).click();
      await expect(page.locator("#builder-inspector-title")).toHaveText("Bottom Navigation");
      await expect(page.locator('#builder-inspector [data-builder-add-navigation-item="true"]')).toBeVisible();
      await page.locator('[data-builder-library-tab="components"]').click();
    }
    await canvas.evaluate((element) => element.click());
    await expect(page.locator("#builder-inspector-title")).toHaveText("Page Settings");

    for (const section of await canvas.locator(".builder-canvas-section").all()) {
      await section.locator(".builder-guest-component").click();
      await expect(section).toHaveClass(/is-selected/);
      await expect(page.locator("#builder-inspector-title")).not.toHaveText("Page Settings");
    }

    const hero = canvas.locator('.builder-canvas-section:has(.experience-hero)').first();
    await hero.locator(".builder-guest-component").click();
    await expect(hero).toHaveClass(/is-selected/);
    await expect(page.locator('[data-builder-tab="content"]')).toBeVisible();
    await expect(page.locator('[data-builder-tab="style"]')).toBeVisible();
    await expect(page.locator('[data-builder-tab="layout"]')).toBeVisible();
    await expect(page.locator('[data-builder-tab="animation"]')).toBeVisible();
    await page.locator('[data-builder-tab="content"]').click();
    await screenshot("hero-selected");

    await page.locator('[data-builder-tab="animation"]').click();
    await page.locator('#builder-inspector [data-builder-field="entrance"]').selectOption("fade_up");
    const animationOptions = await page.locator('#builder-inspector [data-builder-field="entrance"] option').allTextContents();
    for (const label of ["None", "Fade", "Fade Up", "Fade Down", "Slide Left", "Slide Right", "Scale"]) expect(animationOptions).toContain(label);
    await expect(hero.locator(".builder-guest-component")).toHaveAttribute("data-animation", "fade_up");
    await expect(hero.locator(".builder-guest-component")).toHaveClass(/experience-visible/);
    await page.locator("#builder-inspector [data-builder-replay-animation]").click();
    await page.waitForTimeout(500);
    await screenshot("animation-inspector");

    await page.locator('[data-builder-device="mobile"]').click();
    await expect.poll(() => canvas.evaluate((element) => element.getBoundingClientRect().width)).toBeLessThanOrEqual(390);
    await screenshot("mobile-canvas");
    await page.locator('[data-builder-device="desktop"]').click();

    await pointerDrag(page.locator('[data-builder-add="text"]'), canvas);
    const textSection = canvas.locator('.builder-canvas-section[data-builder-section^="text-"]').last();
    await expect(textSection).toBeVisible();
    const quickActions = canvas.locator('.builder-canvas-section:has(.experience-quick_actions)').first();
    const quickActionsId = await quickActions.getAttribute("data-builder-section");
    await pointerDrag(quickActions.locator("[data-builder-drag-handle]"), hero, { x: 22, y: 3 }, true);
    await expect(canvas.locator(".builder-canvas-section").first()).toHaveAttribute("data-builder-section", quickActionsId);
    await screenshot("drag-reorder");

    await quickActions.locator(".builder-guest-component").click();
    await page.locator('[data-builder-tab="content"]').click();
    await expect(page.locator("#builder-inspector-title")).toHaveText("Quick Actions");
    await screenshot("quick-actions-selected");
    await page.locator('#builder-inspector [data-builder-add-quick-action="true"]').click();
    await page.locator('#builder-inspector [data-builder-field="label"]').fill("Dining");
    await page.locator('#builder-inspector [data-builder-field="label"]').press("Tab");
    await page.locator('#builder-inspector [data-builder-field="prompt"]').fill("Show configured property dining options.");
    await page.locator('#builder-inspector [data-builder-field="prompt"]').press("Tab");
    await quickActions.locator(".builder-guest-component").click();
    await page.locator('#builder-inspector [data-builder-add-quick-action="true"]').click();
    await page.locator('#builder-inspector [data-builder-field="label"]').fill("Wellness");
    await page.locator('#builder-inspector [data-builder-field="label"]').press("Tab");
    await page.locator('#builder-inspector [data-builder-field="prompt"]').fill("Show configured property wellness options.");
    await page.locator('#builder-inspector [data-builder-field="prompt"]').press("Tab");
    const quickCards = quickActions.locator(".experience-action-card");
    await expect(quickCards).toHaveCount(2);
    await quickCards.last().click();
    await expect(page.locator("#builder-inspector-title")).toHaveText("Quick Action");
    await expect(page.locator('#builder-inspector [data-builder-field="label"]')).toBeVisible();
    await screenshot("quick-action-selected");
    await page.locator('#builder-inspector [data-builder-nested-item-action="delete"]').click();
    await expect(quickCards).toHaveCount(1);
    await quickActions.locator(".builder-guest-component").click();
    await page.locator('#builder-inspector [data-builder-add-quick-action="true"]').click();
    await page.locator('#builder-inspector [data-builder-field="label"]').fill("Wellness");
    await page.locator('#builder-inspector [data-builder-field="label"]').press("Tab");
    await page.locator('#builder-inspector [data-builder-field="prompt"]').fill("Show configured property wellness options.");
    await page.locator('#builder-inspector [data-builder-field="prompt"]').press("Tab");
    await expect(quickCards).toHaveCount(2);
    await pointerDrag(quickCards.nth(1), quickCards.first(), { x: 20, y: 12 }, true);
    await expect(quickCards.first()).toContainText("Wellness");
    await screenshot("quick-actions");

    const currentHero = canvas.locator('.builder-canvas-section:has(.experience-hero)').first();
    await currentHero.locator(".builder-guest-component").click();
    await page.locator('[data-builder-tab="content"]').click();
    const [imageChooser] = await Promise.all([
      page.waitForEvent("filechooser"),
      page.locator('[data-builder-upload-image="image_url"]').click(),
    ]);
    await imageChooser.setFiles({
      name: "synthetic-builder.png",
      mimeType: "image/png",
      buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/pZ8AAAAASUVORK5CYII=", "base64"),
    });
    await expect.poll(() => currentHero.locator(".experience-hero-image").evaluate((image) => image.src.startsWith("data:image/png;base64,"))).toBe(true);
    await screenshot("hero-image");

    await page.locator('[data-builder-add="image"]').click();
    const imageSection = canvas.locator('.builder-canvas-section:has(.experience-image)').last();
    const mediaPicker = page.locator('#builder-inspector [data-builder-image-library="url"]');
    await expect(mediaPicker).toBeVisible();
    const imageOptions = await mediaPicker.locator("option").evaluateAll((items) => items.map((option) => ({ label: option.textContent, value: option.value })));
    const libraryImage = imageOptions.find((option) => option.value.startsWith("data:image/png;base64,"));
    expect(libraryImage).toBeTruthy();
    await mediaPicker.selectOption({ value: libraryImage.value });
    await expect(imageSection.locator("img.experience-image")).toHaveAttribute("src", libraryImage.value);
    await screenshot("property-media-library");

    await currentHero.locator(".builder-guest-component").click();
    await page.locator('#builder-inspector [data-builder-add-button="hero"]').click();
    await currentHero.locator('.builder-guest-component [data-builder-select="button"]').first().click();
    await page.locator('#builder-inspector [data-builder-field="type"]').selectOption("external_url");
    const actionTypeOptions = await page.locator('#builder-inspector [data-builder-field="type"] option').allTextContents();
    for (const label of ["Internal Page", "External URL", "Restaurant", "Menu", "Room Service", "Housekeeping", "Transportation", "Concierge", "Phone", "Email", "Map / Location"]) expect(actionTypeOptions).toContain(label);
    await page.locator('#builder-inspector [data-builder-field="url"]').fill("javascript:alert(1)");
    await expect(page.locator('#builder-inspector [data-builder-field="url"]')).toHaveAttribute("aria-invalid", "true");
    await expect(page.locator("#builder-inspector [data-builder-url-error]")).toContainText("HTTP or HTTPS");
    await page.locator('#builder-inspector [data-builder-field="url"]').fill("https://example.org/guest");
    await page.locator('#builder-inspector [data-builder-field="open_in"]').selectOption("new_tab");
    await expect(currentHero.locator(".builder-guest-component")).toHaveClass(/experience-visible/);
    await screenshot("button-action-inspector");
    const draftSections = await page.evaluate(() => ({
      mobile: document.querySelector("#builder-canvas").dataset.device,
      width: document.querySelector("#builder-canvas").getBoundingClientRect().width,
    }));
    expect(draftSections.mobile).toBe("desktop");
    expect(draftSections.width).toBeGreaterThan(390);
    await page.locator('[data-builder-library-tab="layers"]').click();
    await expect(page.locator("#builder-section-layers .builder-layer-child-select").filter({ hasText: "Dining" }).first()).toBeVisible();
    await screenshot("nested-layers");
    await page.locator('[data-builder-library-tab="components"]').click();

    await page.locator('[data-builder-add="card_grid"]').click();
    let cardGrid = canvas.locator('.builder-canvas-section:has(.experience-card_grid)').last();
    await page.locator('#builder-inspector [data-builder-add-card="true"]').click();
    await expect(page.locator("#builder-inspector-title")).toHaveText("Card");
    await page.locator('#builder-inspector [data-builder-field="title"]').fill("Sample preview card");
    await page.locator('#builder-inspector [data-builder-field="title"]').press("Tab");
    await cardGrid.locator('.builder-custom-card').last().click();
    await expect(page.locator('#builder-inspector [data-builder-field="action"]')).toHaveCount(0);
    await screenshot("card-item-selected");

    await page.locator('[data-builder-add="bottom_navigation"]').click();
    let bottomNavigation = canvas.locator('.builder-canvas-section:has(.builder-live-bottom-nav)').last();
    await expect(page.locator("#builder-inspector-title")).toHaveText("Bottom Navigation");
    await page.locator('[data-builder-tab="style"]').click();
    await expect(page.locator('#builder-inspector [data-builder-field="active_color"]')).toBeVisible();
    await page.locator('[data-builder-tab="layout"]').click();
    await expect(page.locator('#builder-inspector [data-builder-field="position"]')).toBeVisible();
    await page.locator('[data-builder-tab="content"]').click();
    await screenshot("bottom-navigation-selected");
    await page.once("dialog", (dialog) => dialog.accept());
    await bottomNavigation.locator('[data-builder-action="delete"]').click();
    await expect(canvas.locator('.builder-canvas-section:has(.builder-live-bottom-nav)')).toHaveCount(await existingNavigation.count());
    if (await existingNavigation.count()) {
      await page.once("dialog", (dialog) => dialog.accept());
      await existingNavigation.locator('[data-builder-action="delete"]').click();
    }
    await page.locator('[data-builder-device="mobile"]').click();
    await expect(canvas.locator(".builder-live-bottom-nav")).toHaveCount(0);
    await screenshot("mobile-without-footer");
    await page.locator('[data-builder-device="desktop"]').click();
    await page.locator('[data-builder-add="bottom_navigation"]').click();
    bottomNavigation = canvas.locator('.builder-canvas-section:has(.builder-live-bottom-nav)').last();
    await expect(bottomNavigation.locator(".builder-empty-state")).toContainText("No navigation items yet.");
    await screenshot("bottom-navigation-empty");
    await bottomNavigation.locator('[data-builder-add-navigation-item="true"]').click();
    await expect(page.locator("#builder-inspector-title")).toHaveText("Navigation Item");
    await page.locator('#builder-inspector [data-builder-field="label"]').fill("Dining");
    await page.locator('#builder-inspector [data-builder-field="label"]').press("Tab");
    await page.locator('#builder-inspector [data-builder-field="type"]').selectOption("external_url");
    await page.locator('#builder-inspector [data-builder-field="url"]').fill("javascript:alert(1)");
    await expect(page.locator('#builder-inspector [data-builder-field="url"]')).toHaveAttribute("aria-invalid", "true");
    await page.locator('#builder-inspector [data-builder-field="url"]').fill("https://example.org/dining");
    await page.locator('#builder-inspector [data-builder-field="open_in"]').selectOption("new_tab");
    await screenshot("navigation-item-action-inspector");
    await page.locator('[data-builder-library-tab="layers"]').click();
    const navigationSectionId = await bottomNavigation.getAttribute("data-builder-section");
    await expect(page.locator(`#builder-section-layers .builder-layer-child-select[data-builder-parent-section="${navigationSectionId}"]`).filter({ hasText: "Dining" })).toBeVisible();
    await screenshot("navigation-nested-layers");
    await page.locator('[data-builder-device="mobile"]').click();
    await expect(canvas.locator('.builder-live-bottom-nav button').filter({ hasText: "Dining" })).toBeVisible();
    await screenshot("mobile-with-custom-footer");
    await page.locator('[data-builder-device="desktop"]').click();
    await page.locator('[data-builder-library-tab="components"]').click();

    await page.locator("#builder-save-button").click();
    await expect(page.getByText("Draft saved.")).toBeVisible();
    const persisted = await (await request.get(`/api/admin/properties/${propertyId}/design`)).json();
    const savedHome = persisted.draft.pages.find((item) => item.id === "home");
    const savedQuickActions = savedHome.sections.find((item) => item.type === "quick_actions");
    const savedImage = savedHome.sections.find((item) => item.type === "image");
    const savedHero = savedHome.sections.find((item) => item.type === "hero");
    const savedNavigation = savedHome.sections.find((item) => item.type === "bottom_navigation");
    expect(savedQuickActions.properties.items.map((item) => item.label)).toEqual(["Wellness", "Dining"]);
    expect(savedImage.properties.url).toMatch(/^data:image\/png;base64,/);
    expect(savedHero.properties.buttons[0].action).toMatchObject({ type: "external_url", url: "https://example.org/guest", open_in: "new_tab" });
    expect(savedNavigation.properties.items[0]).toMatchObject({ label: "Dining", action: { type: "external_url", url: "https://example.org/dining", open_in: "new_tab" } });
  } finally {
    const latest = await request.get(`/api/admin/properties/${propertyId}/design`);
    const current = await latest.json();
    await request.put(`/api/admin/properties/${propertyId}/design/draft`, {
      headers: csrfHeaders(request),
      data: { config: initial.draft, expected_revision: current.revision },
    });
  }
});

test("admin: page help uses an accessible question-mark icon", async ({ page }) => {
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();

  const guide = page.locator("#overview > .page-comment");
  await expect(guide).toBeVisible();
  await expect(guide.locator(".page-comment-help-icon")).toHaveText("?");
  const summary = guide.locator("summary");
  await expect(summary).toHaveAttribute("aria-label", "Help for Operations overview");
  await summary.click();
  await expect(guide).toHaveAttribute("open", "");
});

test("admin: local property recommendations can be given home-card images", async ({ page, request }) => {
  const propertyId = await getFirstPropertyId(request);
  const recommendationName = "Home image QA " + Date.now();
  const imageUrl = "/property-home-image-qa.webp";
  let recommendationId = "";

  try {
    await page.goto("/admin");
    await openPanel(page, "Recommendations");
    await page.locator("#recommendation-name").fill(recommendationName);
    await page.locator("#recommendation-category").fill("Dining");
    await page.locator("#recommendation-description").fill("Property-configured suggestion content.");
    await page.locator("#recommendation-images").fill(imageUrl);
    await page.locator("#save-recommendation").click();
    await expect(page.getByText("Recommendation saved.")).toBeVisible();

    const response = await request.get(`/api/admin/properties/${propertyId}/recommendations`);
    expect(response.ok()).toBeTruthy();
    const saved = (await response.json()).recommendations.find((item) => item.name === recommendationName);
    expect(saved?.images).toEqual([imageUrl]);
    recommendationId = saved.recommendation_id;
  } finally {
    if (recommendationId) {
      await request.delete(`/api/admin/properties/${propertyId}/recommendations/${recommendationId}`, { headers: csrfHeaders(request) });
    }
  }
});

test("admin: long workflow guidance is collapsed until requested", async ({ page }) => {
  await page.goto("/admin");
  for (const label of ["Guest Requests", "Guest Sessions", "Personalization", "Conversation Modules", "Rooms", "Facilities", "Branding / Intro"]) {
    await openPanel(page, label);
    const help = page.locator(".panel.active > .contextual-help-disclosure");
    await expect(help).toBeVisible();
    await expect(help).not.toHaveAttribute("open", "");
    await help.locator("summary").click();
    await expect(help).toHaveAttribute("open", "");
    await expect(help.locator(":scope > section, :scope > .card").first()).toBeVisible();
  }
});

test("every visible admin page fits the tablet layout", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The tablet layout sweep needs one browser profile.");
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
  const destinations = await page.locator(".nav-item").evaluateAll((items) => {
    const panels = [...new Set(items.map((item) => item.dataset.panel).filter(Boolean))];
    return panels;
  });

  for (const panel of destinations) {
    const item = page.locator(`.nav-item[data-panel="${panel}"]`).first();
    await item.evaluate((element) => {
      const group = element.closest("details");
      if (group) group.open = true;
    });
    await item.click();
    await expect(page.locator(".panel.active")).toHaveAttribute("id", panel);
    const layout = await page.evaluate(() => {
      const viewport = window.innerWidth;
      const offenders = [...document.querySelectorAll("body *")].map((element) => {
        const rect = element.getBoundingClientRect();
        return { tag: element.tagName, id: element.id, className: typeof element.className === "string" ? element.className : "", left: Math.round(rect.left), right: Math.round(rect.right), width: Math.round(rect.width) };
      }).filter((item) => item.width > 0 && item.right > viewport + 1).sort((a, b) => b.right - a.right).slice(0, 6);
      return { width: document.documentElement.scrollWidth, viewport, offenders };
    });
    expect(layout.width, `Horizontal overflow on ${panel} at tablet width: ${JSON.stringify(layout)}`).toBeLessThanOrEqual(layout.viewport + 1);
  }
});

test("AI providers panel: provider management controls are available", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Models & Providers");
  await expect(page.locator("#ai-default-provider")).toBeEnabled();
  await expect(page.locator("#ai-routing-mode")).toBeEnabled();
  await expect(page.locator("#ai-local-only")).toBeEnabled();
  await expect(page.getByRole("button", { name: "Save AI Settings" })).toBeEnabled();
  await expect(page.locator("article.provider-row")).toHaveCount(7);
  await expect(page.getByRole("heading", { name: "Google Gemini" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "OpenRouter" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Local AI" })).toBeVisible();
});

test("AI provider configure and drawer close buttons work", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Models & Providers");
  await page.locator("article.provider-row [data-action='configure']").first().click();
  await expect(page.locator("#provider-drawer")).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await expect(page.locator("#provider-drawer")).toBeHidden();
});

test("zones map toolbar buttons switch tools and execute safely", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Zones & Maps");

  for (const tool of ["select", "rectangle", "polygon", "ellipse", "freeform", "waypoint", "connect", "access_point"]) {
    const button = page.locator(`[data-map-tool="${tool}"]`);
    await button.click();
    await expect(button).toHaveClass(/active/);
    await expect(button).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#floor-map-canvas")).toHaveAttribute("data-tool", tool);
  }
  const zoomBefore = await page.locator("#map-zoom-label").innerText();
  await page.locator("#map-zoom-in").click();
  await expect(page.locator("#map-zoom-label")).not.toHaveText(zoomBefore);
  await page.locator("#map-fit-canvas").click();
  await expect(page.locator("#map-zoom-label")).toHaveText("100%");
});

test("map workspace adapts to a short desktop viewport", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/admin");
  await openPanel(page, "Zones & Maps");
  const workspace = await page.locator(".map-workspace").boundingBox();
  expect(workspace).not.toBeNull();
  expect(workspace.height).toBeLessThanOrEqual(440);
  const canvasViewport = await page.locator("#map-canvas-viewport").boundingBox();
  expect(canvasViewport).not.toBeNull();
  expect(canvasViewport.y + canvasViewport.height).toBeLessThanOrEqual(720);
  await page.setViewportSize({ width: 390, height: 844 });
  const mobileCanvas = await page.locator("#map-canvas-viewport").boundingBox();
  expect(mobileCanvas).not.toBeNull();
  expect(mobileCanvas.width).toBeLessThanOrEqual(390);
});

test("obsolete product sections are removed from navigation", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.locator('.nav-item .nav-label', { hasText: "Improvement Loop" })).toHaveCount(0);
  await expect(page.locator('.nav-item .nav-label', { hasText: "PMS" })).toHaveCount(0);
  await expect(page.locator('.nav-item .nav-label', { hasText: "License" })).toHaveCount(0);
  await expect(page.locator('.nav-item .nav-label', { hasText: "Exports" })).toHaveCount(0);
});

test("knowledge panel exposes managed source controls", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Knowledge");
  await expect(page.locator("#knowledge-title")).toBeEnabled();
  await expect(page.getByRole("button", { name: "Save Knowledge" })).toBeEnabled();
  await expect(page.locator("#knowledge-list")).toBeVisible();
});

test("managed knowledge review queue uses bounded pages and server search", async ({ page }) => {
  const requests = [];
  await page.route("**/api/admin/properties/*/knowledge/managed**", async (route) => {
    const url = new URL(route.request().url());
    const offset = Number(url.searchParams.get("offset") || 0);
    const query = url.searchParams.get("q");
    requests.push({ offset, query });
    const filtered = Boolean(query);
    const title = filtered ? "Needle Evidence" : (offset ? "Review Item 51" : "Review Item 1");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [{
          item_id: "knowledge-" + offset,
          source_id: null,
          title,
          content: filtered ? "Needle found in verified knowledge" : "Verified facilities information",
          category: "Facilities",
          status: "ready_review",
          visibility: "admin",
          conflict: false,
          risk_flags: [],
          location: {},
        }],
        total: filtered ? 1 : 51,
        limit: 50,
        offset,
        sources: [],
        categories: ["Facilities"],
        limits: {},
      }),
    });
  });

  await page.goto("/admin");
  await openPanel(page, "Knowledge");
  await expect(page.locator("#managed-knowledge-page-info")).toContainText("Page 1 of 2");
  await expect(page.locator("#managed-knowledge-list")).toContainText("Review Item 1");
  await page.locator("#managed-knowledge-page-next").click();
  await expect(page.locator("#managed-knowledge-page-info")).toContainText("Page 2 of 2");
  await expect(page.locator("#managed-knowledge-list")).toContainText("Review Item 51");
  await expect.poll(() => requests[requests.length - 1]?.offset).toBe(50);

  await page.locator("#managed-knowledge-search").fill("needle");
  await expect(page.locator("#managed-knowledge-page-info")).toContainText("Page 1 of 1");
  await expect(page.locator("#managed-knowledge-list")).toContainText("Needle Evidence");
  await expect.poll(() => requests[requests.length - 1]?.query).toBe("needle");
  await expect.poll(() => requests[requests.length - 1]?.offset).toBe(0);
});

test("wifi panel: truthful status and manual test are available", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "ANTlabs / Wi-Fi");
  await expect(page.locator("#antlabs-configured")).not.toHaveText("Checking");
  await expect(page.getByRole("button", { name: "Test Connection" })).toBeEnabled();
});

test("authentication type panel: toggles are available", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Authentication Types");
  await expect(page.locator("#auth-types .poc-note")).toBeVisible();
  await expect(page.locator("#authentication-enabled")).toBeEnabled();
  await expect(page.locator(".auth-type-row")).toHaveCount(10);
  await expect(page.getByRole("heading", { name: "PMS / Room Login" })).toBeVisible();
  const pmsToggle = page.locator('[data-auth-type="pms"]');
  await expect(pmsToggle).toBeEnabled();
  const saveButton = page.getByRole("button", { name: "Save authentication settings" });
  await expect(saveButton).toBeDisabled();
  await expect(page.locator(".auth-save-bar")).toHaveCSS("position", "static");
  const wasPmsEnabled = await pmsToggle.isChecked();
  await pmsToggle.click();
  await expect(pmsToggle).toBeChecked({ checked: !wasPmsEnabled });
  await expect(page.locator("#auth-save-state")).toContainText("Unsaved changes");
  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  await expect(page.locator("#toast")).toContainText("Authentication methods saved");
  await expect(pmsToggle).toBeChecked({ checked: !wasPmsEnabled });
  await expect(saveButton).toBeDisabled();
  await expect(page.locator("#auth-save-state")).toContainText("All changes saved");
});

test("authentication master switch saves and reloads independently of method choices", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Authentication Types");
  const master = page.locator("#authentication-enabled");
  const original = await master.isChecked();
  const pms = page.locator('[data-auth-type="pms"]');
  const originalPms = await pms.isChecked();
  const saveButton = page.getByRole("button", { name: "Save authentication settings" });
  await expect(saveButton).toBeDisabled();

  await master.click();
  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  await expect(page.locator("#toast")).toContainText(original ? "sign-in is off" : "sign-in is on");
  await expect(saveButton).toBeDisabled();
  await page.reload();
  await openPanel(page, "Authentication Types");
  await expect(page.locator("#authentication-enabled")).toBeChecked({ checked: !original });
  await expect(page.locator('[data-auth-type="pms"]')).toBeChecked({ checked: originalPms });

  await page.locator("#authentication-enabled").click();
  await expect(saveButton).toBeEnabled();
  await saveButton.click();
});

test("requests panel: service request controls are available", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Guest Requests");
  await expect(page.locator("#service-room")).toBeVisible();
  await expect(page.locator("#service-type")).toBeVisible();
  await expect(page.getByRole("button", { name: "Create Request" })).toBeVisible();
  await expect(page.locator("#service-request-list")).toBeVisible();
  await expect(page.locator("#request-last-updated")).toContainText("Updated");
});

test("requests panel: operational summary counts and filters use property-local dates", async ({ page }) => {
  const now = Math.floor(Date.now() / 1000);
  const requests = [
    { request_id: "open-1", status: "new", sla_state: "within_sla", request_type: "Water", room: "101", description: "Water", created_at: now, updated_at: now, notes: [] },
    { request_id: "progress-1", status: "in_progress", sla_state: "within_sla", request_type: "Towels", room: "102", description: "Towels", created_at: now, updated_at: now, notes: [] },
    { request_id: "soon-1", status: "assigned", sla_state: "warning", request_type: "Pillows", room: "103", description: "Pillows", created_at: now, updated_at: now, notes: [] },
    { request_id: "late-1", status: "new", sla_state: "overdue", request_type: "Taxi", room: "104", description: "Taxi", created_at: now, updated_at: now, notes: [] },
    { request_id: "done-today", status: "completed", sla_state: "completed", request_type: "Ice", room: "105", description: "Ice", completed_at: now, created_at: now, updated_at: now, notes: [] },
    { request_id: "done-before", status: "completed", sla_state: "completed", request_type: "Laundry", room: "106", description: "Laundry", completed_at: now - 172800, created_at: now - 172800, updated_at: now - 172800, notes: [] },
  ];
  const summary = { open: 4, in_progress: 1, due_soon: 1, overdue: 1, completed_today: 1 };
  await page.route("**/api/admin/properties/*/service-requests?*", (route) => {
    const url = new URL(route.request().url());
    const status = url.searchParams.get("status") || "all";
    const filtered = requests.filter((item) => {
      if (!status || status === "all") return true;
      if (status === "open") return !["completed", "cancelled"].includes(item.status);
      if (status === "due_soon") return item.sla_state === "warning";
      if (status === "overdue") return item.sla_state === "overdue";
      if (status === "completed_today") return item.request_id === "done-today";
      return item.status === status;
    });
    const query = (url.searchParams.get("q") || "").toLowerCase();
    const matching = query ? filtered.filter((item) => `${item.request_id} ${item.request_type} ${item.room} ${item.description}`.toLowerCase().includes(query)) : filtered;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ service_requests: matching, total: matching.length, all_total: requests.length, limit: 50, offset: 0, summary }),
    });
  });
  await page.goto("/admin");
  await openPanel(page, "Guest Requests");

  await expect(page.locator("#request-count-open")).toHaveText("4");
  await expect(page.locator("#request-count-in_progress")).toHaveText("1");
  await expect(page.locator("#request-count-due_soon")).toHaveText("1");
  await expect(page.locator("#request-count-overdue")).toHaveText("1");
  await expect(page.locator("#request-count-completed_today")).toHaveText("1");

  for (const [filter, requestId] of [["in_progress", "progress-1"], ["due_soon", "soon-1"], ["overdue", "late-1"], ["completed_today", "done-today"]]) {
    await page.locator(`[data-request-filter="${filter}"]`).click();
    await expect(page.locator("#service-request-result-count")).toContainText("1–1 of 1 matching");
    await expect(page.locator("#service-request-list")).toContainText(requestId);
  }
});

test("requests panel identifies queued overdue escalations and records their in-app history", async ({ page }) => {
  const now = Math.floor(Date.now() / 1000);
  const overdueRequest = {
    request_id: "overdue-escalated",
    status: "in_progress",
    sla_state: "overdue",
    request_type: "Towels",
    room: "412",
    department: "Housekeeping",
    description: "The request is past its service target.",
    due_at: now - 120,
    sla_target_seconds: 1800,
    created_at: now - 1920,
    updated_at: now,
    notes: [],
    escalation: { target: "Duty Manager", due_at: now - 120, scheduled_at: now, status: "queued" },
  };
  await page.route("**/api/admin/properties/*/service-requests?*", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      service_requests: [overdueRequest],
      total: 1,
      all_total: 1,
      limit: 50,
      offset: 0,
      summary: { open: 1, in_progress: 1, due_soon: 0, overdue: 1, completed_today: 0 },
    }),
  }));
  await page.route("**/api/admin/properties/*/service-requests/overdue-escalated/history", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      history: [{
        history_id: "history-escalation",
        request_id: overdueRequest.request_id,
        action: "overdue_escalation_queued",
        detail: { target: "Duty Manager", due_at: now - 120, delivery_status: "queued" },
        created_at: now,
      }],
    }),
  }));

  await page.goto("/admin");
  await openPanel(page, "Guest Requests");
  const card = page.locator(".service-request-card").filter({ hasText: overdueRequest.request_id });
  await expect(card.locator(".request-escalation-badge")).toHaveText("Escalation queued");
  await card.getByText("View activity history").click();
  await expect(card.locator(".service-request-history-content")).toContainText(
    "Overdue escalation queued for Duty Manager",
  );
});

test("requests panel: pagination fetches bounded pages from the full queue", async ({ page }) => {
  const requests = Array.from({ length: 55 }, (_, index) => ({
    request_id: `request-${String(54 - index).padStart(3, "0")}`,
    status: "new",
    sla_state: "within_sla",
    request_type: "Towels",
    room: String(100 + index),
    description: `Request ${index}`,
    created_at: 1_800_000_000 - index,
    updated_at: 1_800_000_000 - index,
    notes: [],
  }));
  await page.route("**/api/admin/properties/*/service-requests?*", (route) => {
    const url = new URL(route.request().url());
    const limit = Number(url.searchParams.get("limit") || 50);
    const offset = Number(url.searchParams.get("offset") || 0);
    const query = (url.searchParams.get("q") || "").toLowerCase();
    const filtered = requests.filter((item) => `${item.request_id} ${item.room} ${item.description}`.toLowerCase().includes(query));
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        service_requests: filtered.slice(offset, offset + limit),
        total: filtered.length,
        all_total: requests.length,
        limit,
        offset,
        summary: { open: requests.length, in_progress: 0, due_soon: 0, overdue: 0, completed_today: 0 },
      }),
    });
  });
  await page.goto("/admin");
  await openPanel(page, "Guest Requests");
  await expect(page.locator("#service-request-result-count")).toContainText("1–50 of 55 matching");
  await expect(page.locator("#service-request-list")).toContainText("request-054");
  await expect(page.locator("#service-request-page-next")).toBeEnabled();
  await page.locator("#service-request-page-next").click();
  await expect(page.locator("#service-request-page-info")).toHaveText("Page 2 of 2");
  await expect(page.locator("#service-request-result-count")).toContainText("51–55 of 55 matching");
  await expect(page.locator("#service-request-list")).toContainText("request-000");
  await expect(page.locator("#service-request-page-next")).toBeDisabled();
  await page.locator("#service-request-page-previous").click();
  await expect(page.locator("#service-request-page-info")).toHaveText("Page 1 of 2");
});

test("operations assistant formats evidence, completes the first reply, and keeps follow-up context", async ({ page }) => {
  const requests = [];
  await page.route("**/assistant/query", async (route) => {
    const request = route.request().postDataJSON();
    requests.push(request);
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        question: request.question,
        conversation_id: "assistant-ui-audit",
        answer: "### Confirmed observations\n\n**Database:** responding normally.\n\n- API: healthy\n- Error count: 0",
        finding: "System checks completed.",
        component: "system",
        timeframe: "Last 24 hours",
        evidence_items: [{ label: "Database", state: "healthy", detail: "Probe completed." }],
        recommendations: [],
        links: [],
        downloads: [],
      }),
    });
  });
  await page.goto("/admin");
  await openPanel(page, "AI Assistant");
  const input = page.locator("#assistant-page-input");
  const submit = page.locator("#assistant-page-form button[type='submit']");
  await input.fill("Check the system health");
  await submit.click();
  await expect(page.locator("#assistant-page-messages .assistant-message.loading")).toBeVisible();
  await expect(submit).toHaveText("Thinking…");
  await expect(page.locator("#assistant-page-messages .assistant-answer-copy h4")).toHaveText("Confirmed observations");
  const answerCopy = page.locator("#assistant-page-messages .assistant-answer-copy");
  await expect(answerCopy.locator("strong")).toContainText("Database:");
  await expect(answerCopy.locator("li")).toHaveCount(2);
  expect(await answerCopy.innerText()).not.toMatch(/###|\*\*/);
  await expect(submit).toBeEnabled();
  await expect(submit).toHaveText("Send");
  await expect(page.locator("#assistant-page-messages .assistant-message.user")).toHaveCount(1);

  await input.fill("What did the database check show?");
  await submit.click();
  await expect(page.locator("#assistant-page-messages .assistant-message.user")).toHaveCount(2);
  expect(requests).toHaveLength(2);
  expect(requests[1].conversation_id).toBe("assistant-ui-audit");
  await expect(submit).toBeEnabled();
});

test("deployment panel: status info displayed", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Network Access");
  await expect(page.locator("#domain-status")).not.toHaveText("");
  await expect(page.locator("#ssl-status")).not.toHaveText("");
  await expect(page.getByRole("button", { name: "Verify DNS & SSL" })).toBeEnabled();
});

test("users and access panels expose username-first management", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Users");
  await expect(page.getByRole("heading", { name: "User management" })).toBeVisible();
  await expect(page.locator("#users-table")).toBeVisible();
  await expect(page.locator("#users-table-body").getByText("@admin")).toBeVisible();
  await expect(page.locator("#users-page-info")).toContainText("Page 1 of 1");
  await expect(page.locator("#users-page-next")).toBeDisabled();
  await page.getByRole("button", { name: "Create User" }).click();
  await expect(page.locator("#admin-username")).toBeVisible();
  await expect(page.locator("#admin-email")).toHaveAttribute("placeholder", "name@hotel.com");
  await page.locator('#user-dialog .dialog-heading [data-close-dialog="user-dialog"]').click({ force: true });

  await openPanel(page, "Roles");
  await expect(page.getByRole("heading", { name: "Roles", exact: true })).toBeVisible();
  await expect(page.locator("#role-list").getByRole("heading", { name: "Super Admin" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create Role" })).toBeVisible();

  await openPanel(page, "Audit");
  await expect(page.getByRole("heading", { name: "Audit logs" })).toBeVisible();
  await expect(page.locator("#audit .data-table-shell")).toBeVisible();
});

test("user management requests bounded pages and server-side filters", async ({ page }) => {
  const requests = [];
  await page.route("**/api/admin/users**", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const url = new URL(route.request().url());
    const offset = Number(url.searchParams.get("offset") || 0);
    requests.push({ offset, query: url.searchParams.get("q"), status: url.searchParams.get("status") });
    const filtered = Boolean(url.searchParams.get("q"));
    const username = filtered ? "needle-user" : (offset ? "page-user-51" : "page-user-1");
    const displayName = filtered ? "Needle User" : (offset ? "Page User 51" : "Page User 1");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        users: [{
          id: "user-" + offset + "-" + username,
          username,
          display_name: displayName,
          email: null,
          property_id: null,
          role: "Super Admin",
          status: url.searchParams.get("status") || "active",
          last_login: null,
          created: null,
        }],
        total: filtered ? 1 : 51,
        limit: 50,
        offset,
      }),
    });
  });

  await page.goto("/admin");
  await openPanel(page, "Users");
  await expect(page.locator("#users-page-info")).toContainText("Page 1 of 2");
  await expect(page.locator("#users-table-body")).toContainText("@page-user-1");
  await page.locator("#users-page-next").click();
  await expect(page.locator("#users-page-info")).toContainText("Page 2 of 2");
  await expect(page.locator("#users-table-body")).toContainText("@page-user-51");
  await expect.poll(() => requests[requests.length - 1]?.offset).toBe(50);
  await page.locator("#users-page-previous").click();
  await expect(page.locator("#users-table-body")).toContainText("@page-user-1");
  await expect.poll(() => requests[requests.length - 1]?.offset).toBe(0);

  await page.locator("#users-page-next").click();
  await expect(page.locator("#users-table-body")).toContainText("@page-user-51");
  await page.locator("#user-search").fill("needle");
  await expect(page.locator("#users-page-info")).toContainText("Page 1 of 1");
  await expect(page.locator("#users-table-body")).toContainText("@needle-user");
  await expect.poll(() => requests[requests.length - 1]?.query).toBe("needle");
  await page.locator("#user-status-filter").selectOption("disabled");
  await expect.poll(() => requests[requests.length - 1]?.status).toBe("disabled");
  await expect.poll(() => requests[requests.length - 1]?.offset).toBe(0);
});

test("role dialog and audit action buttons work", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Roles");
  await page.getByRole("button", { name: "Create Role" }).click();
  await expect(page.locator("#role-dialog")).toBeVisible();
  await page.locator('#role-dialog [data-close-dialog="role-dialog"]').last().click();
  await expect(page.locator("#role-dialog")).toBeHidden();

  await openPanel(page, "Audit");
  await page.getByRole("button", { name: "Refresh" }).click();
  await page.getByRole("button", { name: "Apply" }).click();
  const auditRows = page.locator("#audit-table-body tr");
  const emptyState = page.locator("#audit-empty");
  await expect.poll(async () => (await auditRows.count()) > 0 || await emptyState.isVisible()).toBeTruthy();
  if (await auditRows.count()) await expect(page.locator("#audit-table-body")).toBeVisible();
});

test("audit log uses bounded server pages with working next and previous controls", async ({ page }) => {
  const requestedOffsets = [];
  await page.route("**/api/admin/audit**", async (route) => {
    const url = new URL(route.request().url());
    const limit = Number(url.searchParams.get("limit"));
    const offset = Number(url.searchParams.get("offset"));
    requestedOffsets.push({ limit, offset });
    const events = Array.from({ length: limit }, (_, index) => ({
      audit_id: offset + index + 1,
      timestamp: 1792126733,
      username: "fixture-auditor",
      display_name: "Fixture Auditor",
      role: "Auditor",
      property_id: null,
      action: `fixture-action-${offset + index}`,
      resource: "fixture",
      resource_id: String(offset + index),
      ip_address: "127.0.0.1",
    }));
    await route.fulfill({ json: { events, total: 101, limit, offset } });
  });

  await page.goto("/admin");
  await openPanel(page, "Audit");
  await expect(page.locator("#audit-table-body tr")).toHaveCount(50);
  await expect(page.locator("#audit-page-info")).toContainText("Page 1 of 3");
  await expect(page.locator("#audit-page-previous")).toBeDisabled();
  await expect(page.locator("#audit-page-next")).toBeEnabled();

  await page.locator("#audit-page-next").click();
  await expect.poll(() => requestedOffsets.length).toBe(2);
  await expect(page.locator("#audit-table-body tr").first()).toContainText("fixture-action-50");
  await expect(page.locator("#audit-page-info")).toContainText("Page 2 of 3");
  await expect(page.locator("#audit-page-previous")).toBeEnabled();
  expect(requestedOffsets).toEqual([{ limit: 50, offset: 0 }, { limit: 50, offset: 50 }]);

  await page.locator("#audit-page-previous").click();
  await expect.poll(() => requestedOffsets.length).toBe(3);
  await expect(page.locator("#audit-table-body tr").first()).toContainText("fixture-action-0");
  expect(requestedOffsets[2]).toEqual({ limit: 50, offset: 0 });
});

// --- 2. Core Configuration Workflow (serial - mutates shared DB) ---

test.describe("config workflow (serial)", () => {
  test.describe.configure({ mode: "serial" });

  test("full config workflow: change, save draft, preview unchanged, publish, persist", async ({
    page,
    request,
  }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "Config workflow only needs one browser profile.");

    const propertyId = await getFirstPropertyId(request);
    const originalPublished = await getOriginalDesign(request, propertyId);
    const qaHeadline = `Stabilize QA ${Date.now()}`;
    const qaHotelName = `QA Hotel ${Date.now()}`;
    const qaAccent = "#6b21a8";
    const qaActionLabel = "Dining " + Date.now();
    const qaActionDescription = "Menus, opening hours, and reservations";
    const qaGreeting = "Welcome back";

    try {
      await page.goto("/admin");
      await openLegacyDesignControls(page);

      await openDesignGroup(page, "brand");
      await page.locator("#design-hotel-name").fill(qaHotelName);
      await openDesignGroup(page, "content");
      await page.locator("#greeting-input").fill(qaGreeting);
      await page.locator("#welcome-input").fill(qaHeadline);
      await openDesignGroup(page, "theme");
      await page.locator("#accent-input").fill(qaAccent);
      await openDesignGroup(page, "prompts");
      await page.locator("#add-prompt").click();
      const actionRow = page.locator(".prompt-row").last();
      await actionRow.locator(".prompt-label").fill(qaActionLabel);
      await actionRow.locator(".prompt-text").fill("Show available dining options");
      await actionRow.locator(".prompt-description").fill(qaActionDescription);

      await page.getByRole("button", { name: "Save Draft", exact: true }).click();
      await expect(page.getByText("Draft saved.")).toBeVisible();

      // Guest still shows original published config
      const hotelApi = await request.get("/api/hotel");
      expect(hotelApi.ok()).toBeTruthy();
      const hotelData = await hotelApi.json();
      expect(hotelData.design?.welcome?.headline).not.toBe(qaHeadline);

      // Preview shows draft changes
      await expect(page.locator(".builder-live-header-identity strong")).toHaveText(qaHotelName);
      await expect(page.locator(".builder-canvas .experience-hero h1")).toHaveText(qaHeadline);

      // Publish
      page.once("dialog", (dialog) => dialog.accept());
      await page.locator("#builder-publish-button").click();
      await expect(page.getByText(/Published guest chat/)).toBeVisible();

      // Guest now shows published config
      const hotelApiAfter = await request.get("/api/hotel");
      expect(hotelApiAfter.ok()).toBeTruthy();
      const hotelAfter = await hotelApiAfter.json();
      expect(hotelAfter.design?.welcome?.headline).toBe(qaHeadline);
      expect(hotelAfter.design?.welcome?.greeting).toBe(qaGreeting);
      expect(hotelAfter.design?.suggestions).toContainEqual(expect.objectContaining({
        label: qaActionLabel,
        prompt: "Show available dining options",
        description: qaActionDescription,
      }));

      // Reload persists
      await page.goto("/");
      await expect(page.locator(".experience-hero h1")).toHaveText(qaHeadline);
      await expect(page.locator(".experience-hero .experience-eyebrow")).toHaveText(qaGreeting);
      const actionButton = page.locator(".experience-quick_actions .experience-action-card").filter({ hasText: qaActionLabel });
      await expect(actionButton.locator("small")).toHaveText(qaActionDescription);
    } finally {
      await request.put(`/api/admin/properties/${propertyId}/design/draft`, {
        headers: csrfHeaders(request),
        data: { config: originalPublished },
      });
      await request.post(`/api/admin/properties/${propertyId}/design/publish`, { headers: csrfHeaders(request) });
    }
  });

  test("discard: resets draft to published", async ({ page, request }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "Discard test only needs one browser.");

    const propertyId = await getFirstPropertyId(request);
    const originalPublished = await getOriginalDesign(request, propertyId);
    const discardHeadline = `Discard test ${Date.now()}`;

    try {
      await page.goto("/admin");
      await openLegacyDesignControls(page);

      await openDesignGroup(page, "content");
      await page.locator("#welcome-input").fill(discardHeadline);
      await page.getByRole("button", { name: "Save Draft", exact: true }).click();
      await expect(page.getByText("Draft saved.")).toBeVisible();

      await page.locator(".builder-more-menu summary").click();
      await page.locator("#builder-discard-button").click();
      await expect(page.getByText("Draft reset to the published design.")).toBeVisible();

      const design = await request.get(`/api/admin/properties/${propertyId}/design`);
      const draft = (await design.json()).draft;
      expect(draft.welcome.headline).toBe(originalPublished.welcome.headline);
    } finally {
      await request.put(`/api/admin/properties/${propertyId}/design/draft`, {
        headers: csrfHeaders(request),
        data: { config: originalPublished },
      });
      await request.post(`/api/admin/properties/${propertyId}/design/publish`, { headers: csrfHeaders(request) });
    }
  });

  test("version restore: restores previous version to draft", async ({
    page,
    request,
  }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "Restore test only needs one browser.");

    const propertyId = await getFirstPropertyId(request);
    const originalPublished = await getOriginalDesign(request, propertyId);

    try {
      // Publish version A
      await page.goto("/admin");
      await openLegacyDesignControls(page);
      await openDesignGroup(page, "content");
      await page.locator("#welcome-input").fill("Version A headline");
      await page.getByRole("button", { name: "Save Draft", exact: true }).click();
      await expect(page.getByText("Draft saved.")).toBeVisible();
      page.once("dialog", (dialog) => dialog.accept());
      await page.locator("#builder-publish-button").click();
      await expect(page.locator("#publish-state")).toContainText("Published");

      // Publish version B
      await page.locator("#welcome-input").fill("Version B headline");
      await page.getByRole("button", { name: "Save Draft", exact: true }).click();
      await expect(page.getByText("Draft saved.")).toBeVisible();
      page.once("dialog", (dialog) => dialog.accept());
      await page.locator("#builder-publish-button").click();
      await expect(page.locator("#publish-state")).toContainText("Published");

      // Verify version list has entries
      await openDesignGroup(page, "versions");
      const versionRows = page.locator(".version-row");
      await expect(versionRows.first()).toBeVisible();
      const count = await versionRows.count();
      expect(count).toBeGreaterThanOrEqual(1);

      // Restore oldest version (last button in reversed list)
      const restoreBtn = versionRows.last().locator("button");
      await restoreBtn.click();
      await expect(page.getByText("restored to draft")).toBeVisible();

      // Draft should have a valid headline different from current published
      const design = await request.get(`/api/admin/properties/${propertyId}/design`);
      const draft = (await design.json()).draft;
      expect(draft.welcome).toBeDefined();
      expect(draft.welcome.headline).toBeTruthy();
    } finally {
      await request.put(`/api/admin/properties/${propertyId}/design/draft`, {
        headers: csrfHeaders(request),
        data: { config: originalPublished },
      });
      await request.post(`/api/admin/properties/${propertyId}/design/publish`, { headers: csrfHeaders(request) });
    }
  });

  test("property save: hotel name persists via API", async ({ page, request }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "Property save only needs one browser.");

    const propertyId = await getFirstPropertyId(request);
    const originalPublished = await getOriginalDesign(request, propertyId);
    const originalProperty = await request.get(`/api/admin/properties/${propertyId}`).then(r => r.json());
    const originalName = originalProperty.hotel_name;
    const newName = `Persist Test ${Date.now()}`;

    try {
      await page.goto("/admin");
      await page.locator('body[data-admin-ready="true"]').waitFor();
      await openPanel(page, "Hotel Information");
      await page.locator("#hotel-info-name").fill(newName);
      await page.locator("#hotel-info-country").fill("Philippines");
      await page.locator("#hotel-info-latitude").fill("14.5995");
      await page.locator("#hotel-info-longitude").fill("120.9842");
      await page.getByRole("button", { name: "Save & Publish" }).click();
      await expect(page.getByText("Hotel information saved and published to the guest profile.")).toBeVisible();

      const res = await request.get(`/api/admin/properties/${propertyId}`);
      expect(await res.json()).toMatchObject({
        hotel_name: newName,
        country: "Philippines",
        latitude: 14.5995,
        longitude: 120.9842,
      });
    } finally {
      await request.put(`/api/admin/properties/${propertyId}/design/draft`, {
        headers: csrfHeaders(request),
        data: { config: originalPublished },
      });
      await request.post(`/api/admin/properties/${propertyId}/design/publish`, { headers: csrfHeaders(request) });
      const propRes = await request.get(`/api/admin/properties/${propertyId}`);
      const prop = await propRes.json();
      prop.hotel_name = originalName;
      prop.country = originalProperty.country || "";
      prop.latitude = originalProperty.latitude;
      prop.longitude = originalProperty.longitude;
      await request.put(`/api/admin/properties/${propertyId}`, { headers: csrfHeaders(request), data: prop });
    }
  });
});

// --- 3. Admin responsiveness ---

test("admin: no horizontal overflow at 1440px", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/admin");
  const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
  expect(bodyWidth).toBeLessThanOrEqual(1440);
});

test("admin: no horizontal overflow at 1280px", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/admin");
  const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
  expect(bodyWidth).toBeLessThanOrEqual(1280);
});

test("admin: no horizontal overflow at tablet (768px)", async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto("/admin");
  const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
  expect(bodyWidth).toBeLessThanOrEqual(768);
});

test("admin: no horizontal overflow at mobile (375px)", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/admin");
  const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
  expect(bodyWidth).toBeLessThanOrEqual(375);
});

test("admin: all nav items reachable at mobile", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
  await page.locator(".nav-group").evaluateAll((groups) => {
    for (const group of groups) group.open = true;
  });
  const navItems = page.locator(".nav-item");
  const count = await navItems.count();
  expect(count).toBeGreaterThanOrEqual(14);
  for (let i = 0; i < count; i++) {
    const nav = navItems.nth(i);
    await nav.scrollIntoViewIfNeeded();
    await expect(nav).toBeVisible();
  }
});

// --- 4. Security ---

test("security: no API keys in client JS", async ({ page }) => {
  await page.goto("/admin");
  const body = await page.content();
  expect(body).not.toContain("GEMINI_API_KEY");
  expect(body).not.toContain("OPENAI_API_KEY");
  expect(body).not.toContain("GOOGLE_PLACES_API_KEY");

  await page.goto("/");
  const guestBody = await page.content();
  expect(guestBody).not.toContain("GEMINI_API_KEY");
  expect(guestBody).not.toContain("OPENAI_API_KEY");
});

test("admin: published guest waypoint exposes a scannable signed QR", async ({ page, request }) => {
  const csrf = await loginAdmin(request);
  const propertyId = `wayfinding-e2e-${Date.now().toString(36)}`;
  const label = `QR Lobby ${Date.now().toString(36)}`;
  const domain = `${propertyId}.example.test`;
  const base = `/api/admin/properties/${propertyId}`;
  let propertyCreated = false;
  try {
    const createdProperty = await request.put(base, {
      headers: csrfHeaders(request),
      data: {
        property_id: propertyId,
        hotel_name: "Wayfinding QR E2E",
        timezone: "Asia/Manila",
        domain,
        guardrails: { directions_enabled: true },
        app_settings: {
          deployment: {
            guest_access_enabled: true,
            https_required: true,
            public_base_url: `https://${domain}`,
          },
        },
      },
    });
    expect(createdProperty.ok(), await createdProperty.text()).toBeTruthy();
    propertyCreated = true;

    const buildingResponse = await request.post(`${base}/buildings`, {
      headers: csrfHeaders(request), data: { data: { name: "Wayfinding Building" } },
    });
    expect(buildingResponse.ok(), await buildingResponse.text()).toBeTruthy();
    const building = await buildingResponse.json();
    const floorResponse = await request.post(`${base}/floors`, {
      headers: csrfHeaders(request), data: { data: { building_id: building.building_id, name: "Lobby", level: 0 } },
    });
    expect(floorResponse.ok(), await floorResponse.text()).toBeTruthy();
    const floor = await floorResponse.json();
    const zoneResponse = await request.put(`${base}/zones`, {
      headers: csrfHeaders(request),
      data: { data: {
        floor_id: floor.floor_id, name: "Guest Lobby",
        geometry: { type: "rectangle", x: 0, y: 0, width: 1200, height: 720 },
      } },
    });
    expect(zoneResponse.ok(), await zoneResponse.text()).toBeTruthy();
    const zone = await zoneResponse.json();
    const mapSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 720"><rect width="1200" height="720" fill="#fff"/></svg>';
    const mapResponse = await request.post(`${base}/floors/${floor.floor_id}/maps`, {
      headers: csrfHeaders(request),
      data: {
        filename: "lobby.svg", content_type: "image/svg+xml",
        content_base64: Buffer.from(mapSvg).toString("base64"), width: 1200, height: 720,
      },
    });
    expect(mapResponse.ok(), await mapResponse.text()).toBeTruthy();
    const nodeResponse = await request.post(`${base}/navigation/nodes`, {
      headers: csrfHeaders(request),
      data: { data: { floor_id: floor.floor_id, zone_id: zone.zone_id, label, x: 80, y: 120, guest_visible: true } },
    });
    expect(nodeResponse.ok(), await nodeResponse.text()).toBeTruthy();

    const draftResponse = await request.post(`${base}/map-revisions`, { headers: csrfHeaders(request) });
    expect(draftResponse.ok(), await draftResponse.text()).toBeTruthy();
    const draft = await draftResponse.json();
    const publishResponse = await request.post(`${base}/map-revisions/${draft.revision_id}/publish`, {
      headers: csrfHeaders(request), data: { expected_current_revision_id: null },
    });
    expect(publishResponse.ok(), await publishResponse.text()).toBeTruthy();

    await page.goto("/admin");
    await page.locator('body[data-admin-ready="true"]').waitFor();
    await page.locator("#property-switcher").selectOption(propertyId);
    await expect(page.locator("#property-switcher")).toHaveValue(propertyId);
    await openPanel(page, "Zones & Maps");
    await expect(page.locator("#map-publish-status")).toContainText("Published revision");
    await page.locator("#zone-tree .map-object-row").filter({ hasText: label }).click();
    const qrPanel = page.locator("#map-wayfinding-qr-panel");
    await expect(qrPanel).toBeVisible();
    await page.getByRole("button", { name: "Generate QR code" }).click();
    await expect(page.locator("#map-wayfinding-status")).toContainText("QR code ready");
    const qrImage = page.locator("#map-wayfinding-qr");
    await expect(qrImage).toBeVisible();
    expect(await qrImage.getAttribute("src")).toMatch(/^data:image\/svg\+xml;charset=utf-8,/);
    const guestLink = page.locator("#map-wayfinding-url");
    await expect(guestLink).toBeVisible();
    const guestUrl = new URL(await guestLink.getAttribute("href"));
    expect(guestUrl.protocol).toBe("https:");
    expect(guestUrl.searchParams.get("property_id")).toBe(propertyId);
    expect(guestUrl.searchParams.get("start_node_id")).toMatch(/^node_/);
    expect(guestUrl.searchParams.get("start_sig")).toMatch(/^[0-9a-f]{64}$/);
  } finally {
    if (propertyCreated) {
      const removed = await request.delete(base, { headers: csrfHeaders(request) });
      expect(removed.ok(), await removed.text()).toBeTruthy();
    }
  }
});
