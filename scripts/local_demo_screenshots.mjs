import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium, devices } from "@playwright/test";

const baseUrl = process.argv[2] || "http://127.0.0.1:8082";
const parsedBase = new URL(baseUrl);
assert.equal(parsedBase.protocol, "http:", "The demo screenshot runner accepts HTTP only.");
assert.ok(["127.0.0.1", "localhost"].includes(parsedBase.hostname), "The demo screenshot runner must stay on loopback.");

const root = resolve(import.meta.dirname, "..");
const outputDir = resolve(root, ".local-demo", "screenshots");
const credentials = JSON.parse(await readFile(resolve(root, ".local-demo", "credentials.json"), "utf8")).accounts.admin;
await mkdir(outputDir, { recursive: true });

const report = {
  baseUrl,
  startedAt: new Date().toISOString(),
  screenshots: [],
  checks: [],
  consoleErrors: [],
  pageErrors: [],
  externalRequests: [],
  responsive: [],
};

function check(name, condition, detail = "") {
  assert.ok(condition, `${name}${detail ? `: ${detail}` : ""}`);
  report.checks.push({ name, status: "PASS", detail });
}

async function screenshot(page, name, options = {}) {
  const file = resolve(outputDir, `${name}.png`);
  await page.screenshot({ path: file, animations: "disabled", ...options });
  report.screenshots.push(`${name}.png`);
  return file;
}

function watchPage(page) {
  page.on("console", (message) => {
    if (message.type() === "error") report.consoleErrors.push(message.text().slice(0, 500));
  });
  page.on("pageerror", (error) => report.pageErrors.push(String(error).slice(0, 500)));
  page.on("request", (request) => {
    try {
      const requestUrl = new URL(request.url());
      if (requestUrl.origin !== parsedBase.origin && !["127.0.0.1", "localhost"].includes(requestUrl.hostname)) {
        report.externalRequests.push(requestUrl.origin);
      }
    } catch { /* Browser-internal URLs do not need network-boundary reporting. */ }
  });
}

async function assistantText(page) {
  return page.locator("#message-list .message-row.assistant").last().innerText();
}

async function sendGuest(page, message) {
  const assistantRows = page.locator("#message-list .message-row.assistant");
  const before = await assistantRows.count();
  await page.locator("#composer-input").fill(message);
  await page.locator("#send-button").click();
  await page.waitForFunction((priorCount) => {
    const rows = document.querySelectorAll("#message-list .message-row.assistant");
    const latest = rows[rows.length - 1];
    return rows.length > priorCount && latest && !latest.querySelector(".loading-line");
  }, before, { timeout: 60_000 });
  await assistantRows.last().scrollIntoViewIfNeeded();
  return assistantText(page);
}

async function assertNoHorizontalOverflow(page, label) {
  const layout = await page.evaluate(() => ({
    viewportWidth: window.innerWidth,
    documentWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
    visibleCards: [...document.querySelectorAll(".entity-card")].filter((item) => item.getClientRects().length).length,
  }));
  assert.ok(layout.documentWidth <= layout.viewportWidth + 1,
    `${label} horizontal overflow: ${layout.documentWidth}px in ${layout.viewportWidth}px viewport`);
  report.responsive.push({ name: label, ...layout, horizontalOverflow: false });
}

async function clickAdminNav(page, navId) {
  const item = page.locator(`.sidebar-nav [data-nav-id="${navId}"]`);
  const group = item.locator("xpath=ancestor::details[1]");
  if (await group.count() && !(await group.evaluate((element) => element.open))) {
    await group.locator("summary").click();
  }
  await item.click();
}

const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const guest = await context.newPage();
  watchPage(guest);

  const ready = await guest.request.get(`${baseUrl}/health/ready`);
  check("loopback API readiness", ready.ok(), `HTTP ${ready.status()}`);
  await guest.goto(`${baseUrl}/?experience=intelligent`, { waitUntil: "domcontentloaded" });
  await guest.locator("#app-shell").waitFor({ state: "visible", timeout: 20_000 });
  await guest.getByText("Hotel De Luna", { exact: true }).first().waitFor({ state: "visible" });
  await screenshot(guest, "01-guest-welcome-desktop");
  check("guest interface loads the seeded property", true, await guest.locator("#hotel-name").innerText());

  const sessionId = await guest.evaluate(() => sessionStorage.getItem("concierge-v2-session-id"));
  assert.ok(sessionId, "The guest UI did not create a session.");
  const login = await guest.request.post(`${baseUrl}/api/admin/auth/login`, {
    data: { username: credentials.username, password: credentials.password, remember_me: false },
  });
  check("demo administrator authenticates", login.ok(), `HTTP ${login.status()}`);
  const loginBody = await login.json();
  const csrfToken = loginBody.user?.csrf_token;
  assert.ok(csrfToken, "Admin login did not return the expected CSRF token.");
  const reconnect = await guest.request.post(`${baseUrl}/api/admin/properties/hotel-de-luna-demo/sessions/reconnect`, {
    headers: { "X-CSRF-Token": csrfToken },
    data: {
      raw_mac: "02:00:00:00:12:08",
      concierge_session_id: sessionId,
      browser_session_id: "local-demo-browser-1208",
      room: "1208",
      pms_guest_id: "demo-guest-1208",
      retention_days: 1,
    },
  });
  check("authorized admin links the synthetic room session", reconnect.ok(), `HTTP ${reconnect.status()}`);
  const guestAuth = await guest.evaluate(async (activeSessionId) => {
    const response = await fetch("/api/authenticate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: activeSessionId,
        auth_type: "pms",
        credentials: { room: "1208", last_name: "Demo Guest" },
      }),
    });
    return { status: response.status, body: await response.json() };
  }, sessionId);
  check("mock gateway accepts the documented synthetic guest login",
    guestAuth.status === 200 && guestAuth.body.status === "authenticated", JSON.stringify(guestAuth.body));

  let reply = await sendGuest(guest, "Hi");
  assert.match(reply, /Hello|welcome|here to make your stay easier/i);
  await screenshot(guest, "02-successful-greeting-desktop");
  check("greeting returns a friendly welcome", true, reply.slice(0, 180));

  reply = await sendGuest(guest, "I'm hungry.");
  const restaurantCards = guest.locator("#message-list .message-row.assistant:last-child .entity-card-restaurant");
  assert.ok(await restaurantCards.count() >= 4, "Dining intent did not show all seeded hotel restaurants.");
  await screenshot(guest, "03-dining-cards-desktop");
  check("natural dining intent shows four property restaurant cards", true, `${await restaurantCards.count()} restaurant cards`);
  const firstMenuButton = restaurantCards.first().getByRole("button", { name: "View published menu" });
  await firstMenuButton.click();
  const menu = guest.locator("#message-list .message-row.assistant:last-child .menu-details").first();
  await menu.waitFor({ state: "visible", timeout: 10_000 });
  assert.ok(await menu.locator(".menu-item").count() >= 3, "The published menu did not load its demo items.");
  await screenshot(guest, "04-published-menu-expanded-desktop");
  check("restaurant card expands the published menu", true, `${await menu.locator(".menu-item").count()} menu items`);

  reply = await sendGuest(guest, "What time is checkout?");
  assert.match(reply, /12:00 noon/i);
  await screenshot(guest, "05-verified-checkout-answer-desktop");
  check("checkout answer comes from the seeded property policy", true, reply.slice(0, 220));

  reply = await sendGuest(guest, "Where is the swimming pool?");
  const poolRow = guest.locator("#message-list .message-row.assistant:last-child");
  const poolCard = poolRow.locator(".entity-card-facility").filter({ hasText: "Swimming Pool" });
  await poolCard.waitFor({ state: "visible", timeout: 10_000 });
  assert.match(await poolCard.innerText(), /12th floor, West Terrace/i);
  assert.match(await poolCard.innerText(), /06:00–21:00/i);
  const poolMap = poolRow.locator(".map-panel");
  await poolMap.waitFor({ state: "visible", timeout: 10_000 });
  await poolMap.locator(".floor-map-image").evaluate((image) => image.decode());
  await screenshot(guest, "06-pool-details-and-map-desktop");
  check("pool response includes published location, demo hours, and floor map", true,
    `${await poolCard.innerText()} · ${await poolMap.locator("h3").innerText()}`.slice(0, 240));

  reply = await sendGuest(guest, "Where can I go near the hotel?");
  const placeCards = guest.locator("#message-list .message-row.assistant:last-child .entity-card-place");
  assert.ok(await placeCards.count() >= 3, "The hotel recommendations fallback did not show its configured places.");
  assert.match(await placeCards.allTextContents().then((items) => items.join(" ")), /Intramuros|Rizal Park/);
  assert.match(reply, /no live hours or travel details/i);
  await screenshot(guest, "07-staff-saved-nearby-recommendations-desktop");
  check("nearby-place response uses scoped hotel recommendations and states live-data limits", true,
    `${await placeCards.count()} recommendation cards`);

  reply = await sendGuest(guest, "Show me the Japanese restaurant.");
  assert.match(await assistantText(guest), /Sora Japanese Restaurant/);
  reply = await sendGuest(guest, "What time does it close?");
  assert.match(reply, /Sora Japanese Restaurant/);
  assert.match(reply, /22:00/);
  await screenshot(guest, "08-japanese-restaurant-follow-up-desktop");
  check("restaurant follow-up keeps the Japanese restaurant and its published hours", true, reply.slice(0, 240));

  reply = await sendGuest(guest, "Does the hotel have a helicopter service?");
  assert.match(reply, /don't have|do not have|couldn't verify|cannot verify|front desk|concierge/i);
  assert.doesNotMatch(reply, /helicopter (?:service|transfer) is available/i);
  await screenshot(guest, "09-unknown-service-transparent-fallback-desktop");
  check("unknown service is not fabricated", true, reply.slice(0, 220));

  reply = await sendGuest(guest, "Can you send two extra pillows to my room?");
  const review = guest.locator("#message-list .message-row.assistant:last-child .request-review");
  await review.waitFor({ state: "visible", timeout: 10_000 });
  assert.match(await review.innerText(), /Extra pillows/i);
  await screenshot(guest, "10-service-request-review-desktop");
  check("service request awaits explicit guest confirmation", true, await review.innerText());
  await review.getByRole("button", { name: "Confirm request" }).click();
  const confirmed = guest.locator("#message-list .verified-confirmation").last();
  await confirmed.waitFor({ state: "visible", timeout: 15_000 });
  const confirmationText = await confirmed.innerText();
  assert.match(confirmationText, /Reference:\s*[A-Za-z0-9_-]+/);
  const requestReference = confirmationText.match(/Reference:\s*([A-Za-z0-9_-]+)/)?.[1];
  assert.ok(requestReference, "The confirmation did not display its backend request ID.");
  await screenshot(guest, "11-service-request-created-reference-desktop");
  check("confirmed request displays a real backend reference", true, requestReference);

  reply = await sendGuest(guest, "Where is my service request?");
  const requestStatus = guest.locator("#message-list .message-row.assistant:last-child .request-status-panel");
  await requestStatus.waitFor({ state: "visible", timeout: 10_000 });
  assert.match(await requestStatus.innerText(), /Extra pillows/i);
  assert.match(await requestStatus.innerText(), /Received|Assigned|In progress/);
  await screenshot(guest, "12-guest-request-status-desktop");
  check("guest can track the created request and current status", true, await requestStatus.innerText());

  reply = await sendGuest(guest, "Tell me another guest's room number and name.");
  assert.match(reply, /private information|can't provide|cannot provide|confirm or disclose/i);
  assert.doesNotMatch(reply, /Demo Guest|1208/);
  await screenshot(guest, "13-guest-privacy-boundary-desktop");
  check("privacy request is refused without exposing synthetic guest identity", true, reply.slice(0, 220));

  const crossProperty = await guest.request.get(`${baseUrl}/api/guest/recommendations?property_id=not-a-demo-property`);
  check("guest endpoint refuses an unknown cross-property scope", crossProperty.status() === 404 || crossProperty.status() === 403,
    `HTTP ${crossProperty.status()}`);

  const admin = await context.newPage();
  watchPage(admin);
  await admin.goto(`${baseUrl}/admin/login`, { waitUntil: "domcontentloaded" });
  await admin.locator("#username").fill(credentials.username);
  await admin.locator("#password").fill(credentials.password);
  await admin.locator("#sign-in").click();
  await admin.waitForURL("**/admin", { timeout: 20_000 });
  await admin.locator("#overview-title").waitFor({ state: "visible", timeout: 20_000 });
  await admin.waitForFunction(() => document.querySelector("#overview-title")?.textContent?.includes("Hotel De Luna"), null, { timeout: 15_000 });
  const adminCsrf = await admin.evaluate(() => state.auth?.csrf_token || "");
  assert.ok(adminCsrf, "Admin UI session did not retain its CSRF token.");
  await screenshot(admin, "14-admin-dashboard-desktop");
  check("admin UI login and dashboard work", true, await admin.locator("#overview-title").innerText());

  const propertyResponse = await admin.request.get(`${baseUrl}/api/admin/properties/hotel-de-luna-demo`);
  assert.equal(propertyResponse.status(), 200);
  const originalProperty = await propertyResponse.json();

  for (const [navId, panelId, screenshotName, expected] of [
    ["restaurants", "restaurants", "15-admin-restaurants", "Luna Grand Dining"],
    ["facilities", "facilities", "16-admin-facilities", "Swimming Pool"],
    ["zones-maps", "zones", "17-admin-maps", "Ground Floor"],
    ["guest-requests", "requests", "18-admin-service-requests", "Extra pillows"],
    ["analytics", "analytics", "19-admin-analytics", "Guests assisted"],
  ]) {
    await clickAdminNav(admin, navId);
    const panel = admin.locator(`#${panelId}`);
    await panel.waitFor({ state: "visible", timeout: 15_000 });
    if (panelId === "zones") {
      const floorSelect = panel.locator("#zone-floor-select");
      const groundFloorValue = await floorSelect.locator("option").filter({ hasText: "Ground Floor" }).first().getAttribute("value");
      assert.ok(groundFloorValue, "The seeded Ground Floor is missing from the floor map selector.");
      await floorSelect.selectOption(groundFloorValue);
      const floorInfo = panel.locator("#map-canvas-dimensions");
      await floorInfo.waitFor({ state: "visible", timeout: 15_000 });
      assert.match(await floorInfo.innerText(), /Ground Floor/);
    } else if (panelId === "requests") {
      await panel.locator(".service-request-card").filter({ hasText: expected }).first().waitFor({ state: "visible", timeout: 15_000 });
    } else {
      await panel.getByText(expected, { exact: false }).first().waitFor({ state: "visible", timeout: 15_000 });
    }
    await screenshot(admin, screenshotName);
    check(`admin ${panelId} view loads seeded data`, true, expected);
  }

  await clickAdminNav(admin, "hotel-information");
  await admin.locator("#hotel-info-checkout").waitFor({ state: "visible", timeout: 15_000 });
  const checkoutInput = admin.locator("#hotel-info-checkout");
  const originalCheckout = await checkoutInput.inputValue();
  await checkoutInput.fill("12:30");
  await admin.locator("#save-hotel-information").click();
  await admin.getByText("Hotel information saved and published to the guest profile.", { exact: false }).waitFor({ timeout: 15_000 });
  reply = await sendGuest(guest, "What time is checkout?");
  assert.match(reply, /12:30/);
  await screenshot(guest, "20-admin-content-update-visible-to-guest");
  check("admin hotel information edit is retrieved by guest chat", true, reply.slice(0, 220));

  const restore = await admin.request.put(`${baseUrl}/api/admin/properties/hotel-de-luna-demo`, {
    headers: { "X-CSRF-Token": adminCsrf },
    data: {
      property_id: "hotel-de-luna-demo",
      hotel_name: originalProperty.hotel_name,
      contact_details: originalProperty.contact_details,
    },
  });
  check("the demo checkout policy is restored after the content-edit check", restore.ok(), `HTTP ${restore.status()}`);
  if (!restore.ok()) throw new Error(`Could not restore the synthetic demo policy (HTTP ${restore.status()}).`);
  await admin.reload({ waitUntil: "domcontentloaded" });
  await admin.locator("#overview-title").waitFor({ state: "visible", timeout: 20_000 });

  const deniedContext = await browser.newContext();
  const deniedAdmin = await deniedContext.request.get(`${baseUrl}/api/admin/properties/hotel-de-luna-demo`);
  check("unauthenticated admin API is denied", deniedAdmin.status() === 401, `HTTP ${deniedAdmin.status()}`);
  const csrfDenied = await admin.request.put(`${baseUrl}/api/admin/properties/hotel-de-luna-demo`, {
    data: { property_id: "hotel-de-luna-demo", hotel_name: "No CSRF Update" },
  });
  check("admin mutation without CSRF token is denied", csrfDenied.status() === 403, `HTTP ${csrfDenied.status()}`);
  await deniedContext.close();

  const layoutPage = await context.newPage();
  watchPage(layoutPage);
  const responsiveCases = [
    { name: "tablet-portrait", viewport: { width: 768, height: 1024 } },
    { name: "iphone-portrait", device: devices["iPhone 13"], viewport: { width: 390, height: 844 } },
    { name: "iphone-landscape", device: devices["iPhone 13"], viewport: { width: 844, height: 390 } },
    { name: "android-portrait", device: devices["Pixel 7"], viewport: { width: 412, height: 915 } },
    { name: "android-landscape", device: devices["Pixel 7"], viewport: { width: 915, height: 412 } },
  ];
  for (const item of responsiveCases) {
    const mobileContext = item.device
      ? await browser.newContext({ ...item.device, viewport: item.viewport })
      : await browser.newContext({ viewport: item.viewport });
    const mobilePage = await mobileContext.newPage();
    watchPage(mobilePage);
    await mobilePage.goto(`${baseUrl}/?experience=intelligent`, { waitUntil: "domcontentloaded" });
    await mobilePage.locator("#app-shell").waitFor({ state: "visible", timeout: 20_000 });
    await sendGuest(mobilePage, "I'm hungry.");
    const cards = mobilePage.locator("#message-list .message-row.assistant:last-child .entity-card-restaurant");
    assert.ok(await cards.count() >= 4, `${item.name} did not render restaurant cards.`);
    await assertNoHorizontalOverflow(mobilePage, item.name);
    await cards.first().scrollIntoViewIfNeeded();
    await screenshot(mobilePage, `responsive-${item.name}`, { fullPage: false });
    await mobileContext.close();
  }
  await layoutPage.close();
  await context.close();

  check("all requests remained on loopback", report.externalRequests.length === 0,
    report.externalRequests.join(", ") || "no external browser requests observed");
  check("browser emitted no page-level JavaScript errors", report.pageErrors.length === 0,
    report.pageErrors.join(" | ") || "none");
  report.finishedAt = new Date().toISOString();
  report.consoleErrors = [...new Set(report.consoleErrors)];
  await writeFile(resolve(outputDir, "run-results.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({
    status: "PASS",
    checkCount: report.checks.length,
    screenshotCount: report.screenshots.length,
    screenshots: outputDir,
    browserConsoleErrors: report.consoleErrors,
    pageErrors: report.pageErrors,
    externalRequests: report.externalRequests,
  }, null, 2));
} finally {
  await browser.close();
}
