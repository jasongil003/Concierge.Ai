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
    pms: "PMS / Room Login",
    access_code: "Access Code",
  };
  prop.antlabs_config = {
    ...(prop.antlabs_config || {}),
    authentication_types: Object.fromEntries(
      ["pms", "access_code"].map((id) => [id, { label: labels[id], enabled: enabledIds.includes(id) }])
    ),
  };
  const response = await request.put(`/api/admin/properties/${propertyId}`, {
    headers: { "X-CSRF-Token": csrf },
    data: prop,
  });
  expect(response.ok()).toBeTruthy();
}

// --- 1. Guest initial load ---

test("guest: loads and shows welcome state with suggestions", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("#welcome-headline")).toBeVisible();
  await expect(page.getByLabel("Suggested prompts")).toBeVisible();
  await expect(page.getByLabel("Ask your concierge")).toBeVisible();
  await expect(page.locator("#send-button")).toBeDisabled();
});

test("guest: hotel name and concierge name are displayed", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#hotel-name")).toBeVisible();
  await expect(page.locator("#concierge-name")).toBeVisible();
});

test("guest: suggestion buttons exist and are clickable", async ({ page }) => {
  await page.goto("/");
  const suggestions = page.locator("#suggestion-list button");
  const count = await suggestions.count();
  expect(count).toBeGreaterThan(0);

  for (let i = 0; i < count; i++) {
    await expect(suggestions.nth(i)).toBeVisible();
    await expect(suggestions.nth(i)).toBeEnabled();
  }
});

test("guest: clicking suggestion sends message", async ({ page }) => {
  await page.goto("/");
  const firstSuggestion = page.locator("#suggestion-list button").first();
  await firstSuggestion.click();
  await expect(page.locator(".message-row.user .message-text")).toBeVisible();
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

// --- 3. Hotel FAQ answer (fast path) ---

test("guest: breakfast question returns fast-path answer", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("What time is breakfast?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".message-row.assistant")).toContainText("6:30 AM");
});

test("guest: checkout question returns fast-path answer", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("What time is checkout?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".message-row.assistant")).toContainText("12:00 PM");
});

test("guest: pool hours question returns fast-path answer", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("What time does the pool close?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".message-row.assistant")).toContainText("10:00 PM");
});

// --- 4. Wi-Fi authentication flow ---

test.describe("wi-fi authentication flow", () => {
test.describe.configure({ mode: "serial" });

test("guest: wi-fi flow shows auth card with room/last name fields", async ({ page, request }) => {
  await setAuthTypes(request, ["pms"]);
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Connect me to Wi-Fi");
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.getByText("Please verify your stay with your room number and last name.")).toBeVisible();
  await expect(page.getByPlaceholder("1503")).toBeVisible();
  await expect(page.getByPlaceholder("Surname")).toBeVisible();
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

  await page.getByPlaceholder("1503").fill("412");
  await page.getByPlaceholder("Surname").fill("Smith");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByText("You're connected")).toBeVisible();
});

test("guest: wi-fi flow only lists enabled non-PMS methods", async ({ page, request }) => {
  await setAuthTypes(request, ["access_code"]);
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Connect me to Wi-Fi");
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.getByText("This hotel currently supports: Access Code.")).toBeVisible();
  await expect(page.getByPlaceholder("1503")).toHaveCount(0);
});
});

// --- 5. Nearby dining / restaurant cards ---

test("guest: nearby dining shows recommendation cards", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Recommend somewhere nearby to eat");
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.locator(".recommendation-card")).toHaveCount(3);
  await expect(page.locator(".recommendation-card").first()).toContainText("Lusso Bistro");
});

test("guest: restaurant card directions button shows toast", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Recommend somewhere nearby to eat");
  await page.getByRole("button", { name: "Send message" }).click();

  const directionsBtn = page.locator(".recommendation-card").first().getByRole("button", { name: "Directions" });
  await directionsBtn.click();
  await expect(page.locator(".toast")).toBeVisible();
});

test("guest: restaurant card details button shows toast", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Recommend somewhere nearby to eat");
  await page.getByRole("button", { name: "Send message" }).click();

  const detailsBtn = page.locator(".recommendation-card").first().getByRole("button", { name: "Details" });
  await detailsBtn.click();
  await expect(page.locator(".toast")).toBeVisible();
});

// --- 6. Service request confirmation ---

test("guest: housekeeping request shows confirmation card", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Send two towels to my room");
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.getByText("Please confirm before I create it.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm request" })).toBeVisible();
});

test("guest: confirm request shows confirmed status", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Ask your concierge").fill("Send two towels to my room");
  await page.getByRole("button", { name: "Send message" }).click();

  await page.getByRole("button", { name: "Confirm request" }).click();
  await expect(page.getByText("Request confirmed.")).toBeVisible();
});

// --- 7. Hotel menu ---

test("guest: menu opens and closes", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Open hotel menu" }).click();
  await expect(page.locator("#hotel-menu")).toHaveClass(/open/);

  await page.getByRole("button", { name: "Close menu" }).click();
  await expect(page.locator("#hotel-menu")).not.toHaveClass(/open/);
});

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

// --- 9. Plus button shows POC warning ---

test("guest: plus button shows POC warning", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "More actions" }).click();
  await expect(page.locator(".toast")).toBeVisible();
  await expect(page.locator(".toast")).toContainText("disabled for this POC");
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
