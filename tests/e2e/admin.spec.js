import { expect, test } from "@playwright/test";

// --- Helpers ---
const csrfByRequest = new WeakMap();

async function loginAdmin(api) {
  const response = await api.post("/api/admin/auth/login", {
    data: { username: "admin", password: "ChangeMe123!", remember_me: false },
  });
  expect(response.ok()).toBeTruthy();
  const csrf = (await response.json()).user.csrf_token;
  csrfByRequest.set(api, csrf);
  return csrf;
}

function csrfHeaders(api) {
  return { "X-CSRF-Token": csrfByRequest.get(api) };
}

async function openPanel(page, label) {
  await page.locator('body[data-admin-ready="true"]').waitFor();
  const button = page.locator(".nav-item").filter({ hasText: label }).first();
  await button.evaluate((element) => {
    const group = element.closest("details");
    if (group) group.open = true;
  });
  await button.click();
}

test.beforeEach(async ({ page, request }) => {
  await loginAdmin(request);
  await loginAdmin(page.request);
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

// --- 1. Admin Controls Audit (read-only, safe to run in parallel) ---

test("topbar: publish state, Save Draft, Publish, Discard, Open guest app", async ({ page }) => {
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
  const viewportWidth = page.viewportSize()?.width || 1440;
  if (viewportWidth > 640) {
    await expect(page.locator("#publish-state")).toBeVisible();
  }
  if (viewportWidth > 900) {
    await expect(page.getByRole("button", { name: "Save Draft" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Publish" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Discard" })).toBeEnabled();
  } else {
    await expect(page.locator("#property-switcher")).toBeVisible();
    await expect(page.locator("#profile-button")).toBeVisible();
  }
  await expect(page.locator('.topbar-status a[href="/"]')).toHaveAttribute("href", "/");
});

test("sidebar: all navigation items are visible and clickable", async ({ page }) => {
  await page.goto("/admin");
  const navLabels = [
    ["Dashboard", "overview"],
    ["Guest Requests", "requests"],
    ["Guest Sessions", "sessions"],
    ["Preview", "guest"],
    ["Rooms", "rooms"],
    ["Zones & Maps", "zones"],
    ["Overview", "knowledge"],
    ["Models & Providers", "ai"],
    ["Improvement Loop", "improvement-loop"],
    ["ANTlabs / Wi-Fi", "wifi"],
    ["Design", "appearance"],
    ["Branding / Intro", "intro"],
    ["Location", "location"],
    ["Users", "users"],
    ["Roles", "roles"],
    ["Permissions", "permissions"],
    ["Domain", "domain"],
    ["SSL", "ssl"],
    ["Network", "network"],
    ["Audit", "audit"],
    ["Security", "security"],
    ["License", "license"],
  ];
  for (const [label, panel] of navLabels) {
    await openPanel(page, label);
    await expect(page.locator(`#${panel}`)).toBeVisible();
  }
});

test("sidebar: each visible navigation item has a feature status", async ({ page }) => {
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
  const navItems = page.locator(".nav-item");
  const count = await navItems.count();
  expect(count).toBeGreaterThan(0);
  const labels = new Set();
  for (let i = 0; i < count; i++) {
    const item = navItems.nth(i);
    const label = (await item.locator(".nav-label").innerText()).trim();
    expect(labels.has(label)).toBeFalsy();
    labels.add(label);
    await expect(item.locator(".nav-status")).toHaveText(/Live|Partial|Coming Soon|Configuration Required/);
  }
});

test("overview panel: property basics are editable", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.locator("#property-id")).toBeDisabled();
  await expect(page.locator("#hotel-name-input")).toBeEnabled();
  await expect(page.locator("#concierge-name-input")).toBeEnabled();
  await expect(page.locator("#domain-input")).toBeEnabled();
  await expect(page.locator("#deployment-mode")).toBeEnabled();
  await expect(page.locator("#overview-title")).not.toBeEmpty();
});

test("appearance panel: all design controls are wired and update preview", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Design");

  await expect(page.locator("#design-hotel-name")).not.toHaveValue("");
  await expect(page.locator("#welcome-input")).toBeEnabled();
  await expect(page.locator("#greeting-input")).toBeEnabled();
  await expect(page.locator("#logo-display-input")).toBeEnabled();
  await expect(page.locator("#logo-upload-input")).toBeEnabled();
  await expect(page.locator("#background-input")).toBeEnabled();
  await expect(page.locator("#text-color-input")).toBeEnabled();
  await expect(page.locator("#secondary-text-color-input")).toBeEnabled();
  await expect(page.locator("#background-image-input")).toBeEnabled();
  await expect(page.locator("#background-overlay-input")).toBeEnabled();
  await expect(page.locator("#accent-input")).toBeEnabled();
  await expect(page.locator("#font-input")).toBeEnabled();
  await expect(page.locator("#density-input")).toBeEnabled();
  await expect(page.locator("#content-width-input")).toBeEnabled();
  await expect(page.locator("#message-width-input")).toBeEnabled();
  await expect(page.locator("#user-style-input")).toBeEnabled();
  await expect(page.locator("#assistant-style-input")).toBeEnabled();
  await expect(page.locator("#header-enabled-input")).toBeEnabled();
  await expect(page.locator("#show-logo-input")).toBeEnabled();
  await expect(page.locator("#show-name-input")).toBeEnabled();
  await expect(page.getByRole("button", { name: "Add prompt" })).toBeEnabled();
  await expect(page.getByText("Live guest chat preview")).toBeVisible();
});

test("appearance panel: preview size buttons work", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Design");

  await expect(page.locator(".phone-preview")).toHaveClass(/mobile/);
  await page.getByRole("button", { name: "Tablet" }).click();
  await expect(page.locator(".phone-preview")).toHaveClass(/tablet/);
  await page.getByRole("button", { name: "Desktop" }).click();
  await expect(page.locator(".phone-preview")).toHaveClass(/desktop/);
  await page.getByRole("button", { name: "Mobile" }).click();
  await expect(page.locator(".phone-preview")).toHaveClass(/mobile/);
});

test("guest experience panel: module table has locked buttons", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Concierge Preview");
  const lockedButtons = page.locator('button:has-text("Locked")');
  await expect(lockedButtons).toHaveCount(4);
  for (const btn of await lockedButtons.all()) {
    await expect(btn).toBeDisabled();
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

test("improvement loop panel: operator controls and model selection are available", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Improvement Loop");

  await expect(page.getByRole("heading", { name: "Continuous improvement loop" })).toBeVisible();
  await expect(page.locator("#loop-provider")).toBeEnabled();
  await expect(page.locator("#loop-model")).toBeEnabled();
  await expect(page.locator("#loop-approval-mode")).toBeEnabled();
  await expect(page.getByRole("button", { name: "Run once" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Start loop" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mark satisfied" })).toBeVisible();
  await expect(page.locator("#loop-provider option", { hasText: "Google Gemini" })).toHaveCount(1);
});

test("knowledge panel: upload zone disabled with POC note", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Overview");
  await expect(page.locator("#knowledge .poc-note")).toBeVisible();
  await expect(page.locator(".upload-zone")).toHaveAttribute("aria-disabled", "true");
});

test("wifi panel: all controls disabled with POC note", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "ANTlabs / Wi-Fi");
  await expect(page.locator("#wifi .poc-note")).toBeVisible();
  for (const sel of await page.locator("#wifi select").all()) {
    await expect(sel).toBeDisabled();
  }
  for (const inp of await page.locator("#wifi input").all()) {
    await expect(inp).toBeDisabled();
  }
});

test("authentication type panel: toggles are available", async ({ page }) => {
  await page.goto("/admin");
  await page.evaluate(() => window.activatePanel?.("auth-types"));
  await expect(page.locator("#auth-types .poc-note")).toBeVisible();
  await expect(page.locator(".auth-type-row")).toHaveCount(10);
  await expect(page.getByText("PMS / Room Login")).toBeVisible();
  await expect(page.locator('[data-auth-type="pms"]')).toBeEnabled();
});

test("requests panel: service request controls are available", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Guest Requests");
  await expect(page.locator("#service-room")).toBeVisible();
  await expect(page.locator("#service-type")).toBeVisible();
  await expect(page.getByRole("button", { name: "Create Request" })).toBeVisible();
  await expect(page.locator("#service-request-list")).toBeVisible();
});

test("deployment panel: status info displayed", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Domain");
  await expect(page.locator("#domain .feature-status")).toHaveText("Configuration Required");
});

test("license panel: license grid displayed", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "License");
  await expect(page.locator(".license-grid")).toBeVisible();
});

test("users and access panels expose username-first management", async ({ page }) => {
  await page.goto("/admin");
  await openPanel(page, "Users");
  await expect(page.getByRole("heading", { name: "User management" })).toBeVisible();
  await expect(page.locator("#users-table")).toBeVisible();
  await expect(page.locator("#users-table-body").getByText("@admin")).toBeVisible();
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

    try {
      await page.goto("/admin");
      await openPanel(page, "Design");

      await page.locator("#design-hotel-name").fill(qaHotelName);
      await page.locator("#welcome-input").fill(qaHeadline);
      await page.locator("#accent-input").fill(qaAccent);
      await page.getByRole("button", { name: "Add prompt" }).click();

      await page.getByRole("button", { name: "Save Draft" }).click();
      await expect(page.getByText("Draft saved.")).toBeVisible();

      // Guest still shows original published config
      const hotelApi = await request.get("/api/hotel");
      expect(hotelApi.ok()).toBeTruthy();
      const hotelData = await hotelApi.json();
      expect(hotelData.design?.welcome?.headline).not.toBe(qaHeadline);

      // Preview shows draft changes
      await expect(page.locator("#preview-hotel")).toHaveText(qaHotelName);
      await expect(page.locator("#preview-welcome")).toHaveText(qaHeadline);

      // Publish
      await page.getByRole("button", { name: "Publish" }).click();
      await expect(page.getByText(/Published guest chat/)).toBeVisible();

      // Guest now shows published config
      const hotelApiAfter = await request.get("/api/hotel");
      expect(hotelApiAfter.ok()).toBeTruthy();
      const hotelAfter = await hotelApiAfter.json();
      expect(hotelAfter.design?.welcome?.headline).toBe(qaHeadline);

      // Reload persists
      await page.goto("/");
      await expect(page.locator("#welcome-headline")).toHaveText(qaHeadline);
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
      await openPanel(page, "Design");

      await page.locator("#welcome-input").fill(discardHeadline);
      await page.getByRole("button", { name: "Save Draft" }).click();
      await expect(page.getByText("Draft saved.")).toBeVisible();

      await page.getByRole("button", { name: "Discard" }).click();
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
      await openPanel(page, "Design");
      await page.locator("#welcome-input").fill("Version A headline");
      await page.getByRole("button", { name: "Save Draft" }).click();
      await expect(page.getByText("Draft saved.")).toBeVisible();
      await page.getByRole("button", { name: "Publish" }).click();
      await expect(page.locator("#publish-state")).toContainText("Published");

      // Publish version B
      await page.locator("#welcome-input").fill("Version B headline");
      await page.getByRole("button", { name: "Save Draft" }).click();
      await expect(page.getByText("Draft saved.")).toBeVisible();
      await page.getByRole("button", { name: "Publish" }).click();
      await expect(page.locator("#publish-state")).toContainText("Published");

      // Verify version list has entries
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

  test("overview save: hotel name persists via API", async ({ page, request }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "Property save only needs one browser.");

    const propertyId = await getFirstPropertyId(request);
    const originalPublished = await getOriginalDesign(request, propertyId);
    const originalName = (await request.get(`/api/admin/properties/${propertyId}`).then(r => r.json())).hotel_name;
    const newName = `Persist Test ${Date.now()}`;

    try {
      await page.goto("/admin");
      await page.locator('body[data-admin-ready="true"]').waitFor();
      await page.locator("#hotel-name-input").fill(newName);
      await page.locator("#hotel-name-input").press("Tab");
      await page.getByRole("button", { name: "Save Draft" }).click();
      await expect(page.getByText("Draft saved.")).toBeVisible();

      const res = await request.get(`/api/admin/properties/${propertyId}`);
      expect((await res.json()).hotel_name).toBe(newName);
    } finally {
      await request.put(`/api/admin/properties/${propertyId}/design/draft`, {
        headers: csrfHeaders(request),
        data: { config: originalPublished },
      });
      await request.post(`/api/admin/properties/${propertyId}/design/publish`, { headers: csrfHeaders(request) });
      const propRes = await request.get(`/api/admin/properties/${propertyId}`);
      const prop = await propRes.json();
      prop.hotel_name = originalName;
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
