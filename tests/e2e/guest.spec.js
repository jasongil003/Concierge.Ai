import { expect, test } from "@playwright/test";

const csrfByRequest = new WeakMap();

async function loginAdmin(request) {
  if (csrfByRequest.has(request)) return csrfByRequest.get(request);
  const response = await request.post("/api/admin/auth/login", {
    data: { username: "admin", password: "ChangeMe123!", remember_me: false },
  });
  expect(response.ok()).toBeTruthy();
  const csrf = (await response.json()).user.csrf_token;
  csrfByRequest.set(request, csrf);
  return csrf;
}

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

test("guest: loads with an unconfigured property profile", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("#welcome-headline")).toBeVisible();
  await expect(page.locator("#suggestion-list button")).toHaveCount(0);
  await expect(page.getByLabel("Ask your concierge")).toBeVisible();
  await expect(page.locator("#send-button")).toBeDisabled();
});

test("guest: hotel name and concierge name are displayed", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#hotel-name")).toBeVisible();
  await expect(page.locator("#concierge-name")).toBeVisible();
});

// --- 2. Chat submit and multiline composer ---

test("guest: chat submit works with direct input", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("What time is breakfast?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".message-row.user")).toContainText("What time is breakfast?");
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
  await expect(page.locator(".recommendation-card").first()).toContainText("Synthetic test recommendation.");
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
  await page.getByRole("button", { name: "Open hotel menu" }).click();
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

  await expect(page.getByText(/Please confirm.*send it/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm request" })).toBeVisible();
});

test("guest: confirm request persists and returns a request id", async ({ page, request }) => {
  await ensureGuestData(request);
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Send two towels to my room");
  await page.getByRole("button", { name: "Send message" }).click();

  await page.getByRole("button", { name: "Confirm request" }).click();
  await expect(page.getByText(/Request req_[a-f0-9]+ was created/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirmed" })).toBeDisabled();
});

// --- 7. Hotel menu ---

test("guest: menu opens and closes", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Open hotel menu" }).click();
  await expect(page.locator("#hotel-menu")).toHaveClass(/open/);

  await page.getByRole("button", { name: "Close menu" }).click();
  await expect(page.locator("#hotel-menu")).not.toHaveClass(/open/);
});

test("guest: options button opens the same working menu", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Open options" }).click();
  await expect(page.locator("#hotel-menu")).toHaveClass(/open/);
  await page.getByRole("button", { name: "Close menu" }).click();
  await expect(page.locator("#hotel-menu")).not.toHaveClass(/open/);
});

test("guest: hotel information menu action responds with configured property details", async ({ page, request }) => {
  const hotel = await (await request.get("/api/hotel")).json();
  await page.goto("/");
  await page.getByRole("button", { name: "Open hotel menu" }).click();
  await page.getByRole("button", { name: "Hotel information", exact: true }).click();
  await expect(page.locator(".message-row.assistant").last()).toContainText(hotel.description || hotel.name);
  await expect(page.locator("#hotel-menu")).not.toHaveClass(/open/);
});

for (const [label, expectedText] of [
  ["Language", "Language preference set"],
  ["Accessibility", "Accessibility display mode"],
  ["Privacy", "session is temporary"],
  ["Help", "Ask about verified hotel information"],
]) {
  test(`guest: ${label.toLowerCase()} menu action responds`, async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Open hotel menu" }).click();
    await page.getByRole("button", { name: label, exact: true }).click();
    await expect(page.locator(".message-row.assistant").last()).toContainText(expectedText);
    await expect(page.locator("#hotel-menu")).not.toHaveClass(/open/);
  });
}

test("guest: new conversation resets messages", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Hello");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".message-row.user")).toBeVisible();

  await page.getByRole("button", { name: "Open hotel menu" }).click();
  await page.getByRole("button", { name: "New conversation" }).click();
  await expect(page.locator(".message-row")).toHaveCount(0);
});

// --- 8. Mobile layout ---

test("guest: mobile layout (375px) has no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/");

  const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
  expect(bodyWidth).toBeLessThanOrEqual(375);
});

test("guest: mobile layout shows all core elements", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/");

  await expect(page.locator("#welcome-headline")).toBeVisible();
  await expect(page.getByLabel("Ask your concierge")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
});

test("guest: composer input uses the available width", async ({ page }) => {
  await page.goto("/");
  const sizes = await page.locator("#composer-form").evaluate((form) => {
    const input = form.querySelector("textarea");
    return { form: form.getBoundingClientRect().width, input: input.getBoundingClientRect().width };
  });
  expect(sizes.input).toBeGreaterThan(sizes.form * 0.7);
});

// --- 9. Unsupported attachment control is not exposed ---

test("guest: unsupported attachment control is not exposed", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "More actions" })).toHaveCount(0);
});

// --- 10. Dark mode (if supported) ---

test("guest: dark mode renders without errors", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");

  await expect(page.locator("#welcome-headline")).toBeVisible();
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
    data: { username: "admin", password: "ChangeMe123!", remember_me: false },
  });
  expect(login.ok()).toBeTruthy();
  await page.goto("/admin");
  await page.waitForLoadState("networkidle");

  expect(errors).toEqual([]);
});
