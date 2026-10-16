import { expect, test } from "@playwright/test";
import { ensureTestProperty } from "./support.js";

const conversationsRoute = "**/api/admin/properties/*/conversations?*";
const retentionRoute = "**/api/admin/properties/*/conversations/retention";
const csrfByRequest = new WeakMap();

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function conversationsResponse(retentionDays) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ conversations: [], retention: { retention_days: retentionDays } }),
  };
}

function savedRetentionResponse(retentionDays, status = 200) {
  return {
    status,
    contentType: "application/json",
    body: JSON.stringify(status === 200 ? { retention_days: retentionDays } : { detail: "Temporary save failure." }),
  };
}

async function loginAdmin(api) {
  const response = await api.post("/api/admin/auth/login", {
    data: { username: "admin", password: "PlaywrightOnly-Admin-123!", remember_me: false },
  });
  expect(response.ok()).toBeTruthy();
  const csrf = (await response.json()).user.csrf_token;
  csrfByRequest.set(api, csrf);
  await ensureTestProperty(api, csrf);
  return csrf;
}

async function createTestProperty(api) {
  const propertyId = "e2e-retention-" + Date.now().toString(36);
  const response = await api.put("/api/admin/properties/" + propertyId, {
    headers: { "X-CSRF-Token": csrfByRequest.get(api) },
    data: { property_id: propertyId, hotel_name: "Retention Race Test", timezone: "Asia/Manila" },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return propertyId;
}

async function deleteTestProperty(api, propertyId) {
  const response = await api.delete("/api/admin/properties/" + propertyId, {
    headers: { "X-CSRF-Token": csrfByRequest.get(api) },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
}

async function openConversations(page) {
  await page.goto("/admin");
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
  const button = page.locator(".nav-item").filter({ hasText: "Conversations" }).first();
  await button.evaluate((element) => {
    const group = element.closest("details");
    if (group) group.open = true;
  });
  await button.scrollIntoViewIfNeeded();
  await button.click();
  const retention = page.locator(".conversation-retention");
  await expect(retention).toBeVisible();
  if (!(await retention.evaluate((element) => element.open))) {
    await retention.locator(":scope > summary").click();
  }
}

async function fulfill(route, payload) {
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
}

test.beforeEach(async ({ page }) => {
  await loginAdmin(page.request);
});

test("a stale inbox response cannot overwrite a retention save", async ({ page }) => {
  const initialStarted = deferred();
  const releaseInitial = deferred();
  const initialFinished = deferred();
  const refreshedAfterSave = deferred();
  let getCount = 0;

  await page.route(conversationsRoute, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    getCount += 1;
    if (getCount === 1) {
      initialStarted.resolve();
      await releaseInitial.promise;
      await route.fulfill(conversationsResponse(30));
      initialFinished.resolve();
      return;
    }
    await route.fulfill(conversationsResponse(21));
    if (getCount === 2) refreshedAfterSave.resolve();
  });
  await page.route(retentionRoute, (route) => route.fulfill(savedRetentionResponse(21)));

  await openConversations(page);
  await initialStarted.promise;
  await page.locator("#conversation-retention-days").fill("21");
  await page.getByRole("button", { name: "Save retention" }).click();
  await refreshedAfterSave.promise;
  await expect(page.locator("#conversation-retention-days")).toHaveValue("21");

  releaseInitial.resolve();
  await initialFinished.promise;
  await expect(page.locator("#conversation-retention-days")).toHaveValue("21");
});

test("the latest of simultaneous inbox refreshes wins", async ({ page }) => {
  const started = [deferred(), deferred()];
  const release = [deferred(), deferred()];
  const finished = [deferred(), deferred()];
  let getCount = 0;

  await page.route(conversationsRoute, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const index = getCount++;
    if (index < 2) {
      started[index].resolve();
      await release[index].promise;
    }
    await route.fulfill(conversationsResponse(index === 0 ? 99 : 12));
    if (index < 2) finished[index].resolve();
  });

  await openConversations(page);
  await started[0].promise;
  await page.evaluate(() => { void loadConversations(); });
  await started[1].promise;

  release[1].resolve();
  await finished[1].promise;
  await expect(page.locator("#conversation-retention-days")).toHaveValue("12");
  release[0].resolve();
  await finished[0].promise;
  await expect(page.locator("#conversation-retention-days")).toHaveValue("12");
});

test("an in-flight inbox response cannot cross a property switch", async ({ page }) => {
  const secondPropertyId = await createTestProperty(page.request);
  const initialStarted = deferred();
  const releaseInitial = deferred();
  const initialFinished = deferred();
  const secondStarted = deferred();
  let initialPropertyId = "";

  await page.route(conversationsRoute, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const match = new URL(route.request().url()).pathname.match(/\/properties\/([^/]+)\/conversations$/);
    const propertyId = match?.[1] || "";
    if (propertyId === secondPropertyId) {
      secondStarted.resolve();
      return route.fulfill(conversationsResponse(42));
    }
    initialPropertyId = propertyId;
    initialStarted.resolve();
    await releaseInitial.promise;
    await route.fulfill(conversationsResponse(84));
    initialFinished.resolve();
  });

  try {
    await openConversations(page);
    await initialStarted.promise;
    await expect(page.locator("#property-switcher")).toHaveValue(initialPropertyId);
    await page.locator("#property-switcher").selectOption(secondPropertyId);
    await secondStarted.promise;
    await expect(page.locator("#conversation-retention-days")).toHaveValue("42");

    releaseInitial.resolve();
    await initialFinished.promise;
    await expect(page.locator("#property-switcher")).toHaveValue(secondPropertyId);
    await expect(page.locator("#conversation-retention-days")).toHaveValue("42");
  } finally {
    releaseInitial.resolve();
    await deleteTestProperty(page.request, secondPropertyId);
  }
});

test("an edit made during a save remains available for the next save", async ({ page }) => {
  const firstPutStarted = deferred();
  const releaseFirstPut = deferred();
  const firstRefreshFinished = deferred();
  const secondPutFinished = deferred();
  const secondRefreshFinished = deferred();
  let putCount = 0;
  let secondSubmittedValue = null;
  let getCount = 0;

  await page.route(conversationsRoute, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const index = getCount++;
    await route.fulfill(conversationsResponse(index === 0 ? 30 : index === 1 ? 21 : 42));
    if (index === 1) firstRefreshFinished.resolve();
    if (index === 2) secondRefreshFinished.resolve();
  });
  await page.route(retentionRoute, async (route) => {
    putCount += 1;
    const submitted = route.request().postDataJSON().retention_days;
    if (putCount === 1) {
      firstPutStarted.resolve();
      await releaseFirstPut.promise;
      await route.fulfill(savedRetentionResponse(21));
      return;
    }
    secondSubmittedValue = submitted;
    await route.fulfill(savedRetentionResponse(42));
    secondPutFinished.resolve();
  });

  await openConversations(page);
  const input = page.locator("#conversation-retention-days");
  const save = page.getByRole("button", { name: "Save retention" });
  await expect(input).toHaveValue("30");
  await input.fill("21");
  await save.click();
  await firstPutStarted.promise;
  await input.fill("42");
  releaseFirstPut.resolve();
  await firstRefreshFinished.promise;
  await expect(input).toHaveValue("42");
  await expect(save).toBeEnabled();

  await save.click();
  await secondPutFinished.promise;
  await secondRefreshFinished.promise;
  await expect(input).toHaveValue("42");
  expect(secondSubmittedValue).toBe(42);
});

test("a failed retention save keeps the draft and allows a retry", async ({ page }) => {
  const failedPutFinished = deferred();
  const retriedPutFinished = deferred();
  const refreshAfterRetry = deferred();
  let putCount = 0;
  let getCount = 0;

  await page.route(conversationsRoute, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const index = getCount++;
    await route.fulfill(conversationsResponse(index === 0 ? 30 : 14));
    if (index === 1) refreshAfterRetry.resolve();
  });
  await page.route(retentionRoute, async (route) => {
    putCount += 1;
    if (putCount === 1) {
      await route.fulfill(savedRetentionResponse(0, 500));
      failedPutFinished.resolve();
      return;
    }
    await route.fulfill(savedRetentionResponse(14));
    retriedPutFinished.resolve();
  });

  await openConversations(page);
  const input = page.locator("#conversation-retention-days");
  const save = page.getByRole("button", { name: "Save retention" });
  await input.fill("21");
  await save.click();
  await failedPutFinished.promise;
  await expect(input).toHaveValue("21");
  await expect(save).toBeEnabled();

  await save.click();
  await retriedPutFinished.promise;
  await refreshAfterRetry.promise;
  await expect(input).toHaveValue("14");
});

test("the server's saved retention value is preserved over an older follow-up GET", async ({ page }) => {
  const savedResponseFinished = deferred();
  let getCount = 0;

  await page.route(conversationsRoute, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    getCount += 1;
    await route.fulfill(conversationsResponse(30));
    if (getCount === 2) savedResponseFinished.resolve();
  });
  await page.route(retentionRoute, (route) => route.fulfill(savedRetentionResponse(14)));

  await openConversations(page);
  await page.locator("#conversation-retention-days").fill("21");
  await page.getByRole("button", { name: "Save retention" }).click();
  await savedResponseFinished.promise;
  await expect(page.locator("#conversation-retention-days")).toHaveValue("14");
});
