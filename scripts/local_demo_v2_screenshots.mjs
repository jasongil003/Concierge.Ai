import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium, devices } from "@playwright/test";

const baseUrl = process.argv[2] || "http://127.0.0.1:8082";
const parsedBase = new URL(baseUrl);
assert.equal(parsedBase.protocol, "http:", "The V2 demo runner accepts HTTP only.");
assert.ok(["127.0.0.1", "localhost"].includes(parsedBase.hostname), "The V2 demo runner must stay on loopback.");

const root = resolve(import.meta.dirname, "..");
const outputDir = resolve(root, ".local-demo", "screenshots");
const credentials = JSON.parse(await readFile(resolve(root, ".local-demo", "credentials.json"), "utf8")).accounts.admin;
await mkdir(outputDir, { recursive: true });

const report = {
  suite: "Hotel De Luna V2 local demo",
  baseUrl,
  startedAt: new Date().toISOString(),
  checks: [],
  images: [],
  screenshots: [],
  consoleErrors: [],
  pageErrors: [],
  failedLocalRequests: [],
  externalRequests: [],
  responsive: [],
};

function check(name, condition, detail = "") {
  assert.ok(condition, `${name}${detail ? `: ${detail}` : ""}`);
  report.checks.push({ name, status: "PASS", detail });
}

function watchPage(page) {
  page.on("console", (message) => {
    if (message.type() === "error") report.consoleErrors.push(message.text().slice(0, 400));
  });
  page.on("pageerror", (error) => report.pageErrors.push(String(error).slice(0, 400)));
  page.on("requestfailed", (request) => {
    const url = new URL(request.url());
    if (url.origin === parsedBase.origin) report.failedLocalRequests.push(`${request.method()} ${url.pathname}: ${request.failure()?.errorText || "failed"}`);
  });
  page.on("request", (request) => {
    try {
      const url = new URL(request.url());
      if (url.origin !== parsedBase.origin && !["127.0.0.1", "localhost"].includes(url.hostname)) report.externalRequests.push(url.origin);
    } catch { /* Ignore browser-internal URLs. */ }
  });
}

async function screenshot(page, name, options = {}) {
  const path = resolve(outputDir, `${name}.png`);
  await page.screenshot({ path, animations: "disabled", ...options });
  report.screenshots.push(`${name}.png`);
}

async function sendGuest(page, message) {
  const rows = page.locator("#message-list .message-row.assistant");
  const before = await rows.count();
  await page.locator("#composer-input").fill(message);
  await page.locator("#send-button").click();
  await page.waitForFunction((count) => {
    const items = document.querySelectorAll("#message-list .message-row.assistant");
    const latest = items[items.length - 1];
    return items.length > count && latest && !latest.querySelector(".loading-line");
  }, before, { timeout: 60_000 });
  return rows.last().innerText();
}

async function assertImages(page, imageLocator, label) {
  const count = await imageLocator.count();
  assert.ok(count > 0, `${label}: no rendered images were found.`);
  for (let index = 0; index < count; index += 1) {
    const image = imageLocator.nth(index);
    await image.scrollIntoViewIfNeeded();
    const result = await image.evaluate(async (element) => {
      try { await element.decode(); } catch { /* Report the rendered dimensions below. */ }
      return { width: element.naturalWidth, height: element.naturalHeight, src: element.currentSrc || element.src };
    });
    assert.ok(result.width > 0 && result.height > 0, `${label}: image ${index + 1} did not decode (${result.src}).`);
    const imageUrl = new URL(result.src, baseUrl);
    assert.equal(imageUrl.origin, parsedBase.origin, `${label}: an image escaped the local media origin.`);
    report.images.push({ label, width: result.width, height: result.height, path: imageUrl.pathname });
  }
  return count;
}

async function clickAdminNav(page, navId) {
  const item = page.locator(`.sidebar-nav [data-nav-id="${navId}"]`);
  const group = item.locator("xpath=ancestor::details[1]");
  if (await group.count() && !(await group.evaluate((element) => element.open))) await group.locator("summary").click();
  await item.click();
}

async function assertNoHorizontalOverflow(page, name) {
  const layout = await page.evaluate(() => ({
    viewportWidth: window.innerWidth,
    documentWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
  }));
  assert.ok(layout.documentWidth <= layout.viewportWidth + 1,
    `${name} overflows horizontally: ${layout.documentWidth}px in ${layout.viewportWidth}px.`);
  report.responsive.push({ name, ...layout, horizontalOverflow: false });
}

const browser = await chromium.launch({ headless: true });
try {
  const guestContext = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const guest = await guestContext.newPage();
  watchPage(guest);
  const health = await guest.request.get(`${baseUrl}/health/ready`);
  check("isolated local API is healthy", health.ok(), `HTTP ${health.status()}`);

  await guest.goto(`${baseUrl}/?experience=intelligent`, { waitUntil: "domcontentloaded" });
  await guest.locator("#app-shell").waitFor({ state: "visible", timeout: 20_000 });
  await guest.locator("#hotel-name").getByText("Hotel De Luna").waitFor({ state: "visible" });
  await guest.waitForFunction(() => Boolean(sessionStorage.getItem("concierge-v2-session-id")), null, { timeout: 20_000 });
  const sessionId = await guest.evaluate(() => sessionStorage.getItem("concierge-v2-session-id"));
  assert.ok(sessionId, "The guest page did not create a conversation session.");
  await screenshot(guest, "v2-01-guest-welcome");
  check("guest UI loads the imported property", true, await guest.locator("#hotel-name").innerText());

  const login = await guest.request.post(`${baseUrl}/api/admin/auth/login`, {
    data: { username: credentials.username, password: credentials.password, remember_me: false },
  });
  check("generated local Admin credentials authenticate", login.ok(), `HTTP ${login.status()}`);
  const guestAuth = await guest.request.post(`${baseUrl}/api/authenticate`, {
    data: { session_id: sessionId, auth_type: "pms", credentials: { room: "1208", last_name: "Rivera" } },
  });
  const guestAuthBody = await guestAuth.json();
  check("guest Wi-Fi authentication stays disabled in the isolated demo", guestAuth.status() === 403, `HTTP ${guestAuth.status()}: ${guestAuthBody.detail || guestAuthBody.message || "disabled by property policy"}`);

  let reply = await sendGuest(guest, "Hi");
  assert.match(reply, /Hello|welcome|here to make your stay easier/i);
  await screenshot(guest, "v2-02-greeting");
  check("greeting returns a welcome", true, reply.slice(0, 160));

  reply = await sendGuest(guest, "I'm hungry.");
  let diningRow = guest.locator("#message-list .message-row.assistant:last-child");
  let restaurantCards = diningRow.locator(".entity-card-restaurant");
  assert.equal(await restaurantCards.count(), 4, "Dining intent should return the four imported restaurants.");
  const restaurantImages = await assertImages(guest, restaurantCards.locator(".entity-card-image"), "restaurant cards");
  await screenshot(guest, "v2-03-restaurant-cards");
  check("dining cards show all four restaurants with local images", true, `${await restaurantCards.count()} cards; ${restaurantImages} decoded images`);

  let menuItems = 0;
  let menuImages = 0;
  for (let index = 0; index < await restaurantCards.count(); index += 1) {
    const card = restaurantCards.nth(index);
    await card.getByRole("button", { name: "View published menu" }).click();
    const menu = card.locator(".menu-details");
    await menu.waitFor({ state: "visible" });
    const entries = menu.locator(".menu-item");
    menuItems += await entries.count();
    const prices = await menu.locator(".menu-price").count();
    assert.ok(prices > 0, `Menu in ${await card.locator("h3").innerText()} has no prices.`);
    assert.ok(await entries.first().locator("p").count(), "Menu item descriptions are missing.");
    menuImages += await assertImages(guest, menu.locator(".menu-item-image"), `menu ${index + 1}`);
    if (index === 0) await screenshot(guest, "v2-04-menu-items-and-prices");
  }
  assert.equal(menuItems, 40, `Expected 40 published menu items; found ${menuItems}.`);
  assert.equal(menuImages, 40, `Expected 40 local menu images; found ${menuImages}.`);
  check("all forty published menu items show descriptions, demo prices, and decoded local images", true, `${menuItems} items; ${menuImages} images`);

  reply = await sendGuest(guest, "What is the price and description of Breakfast Buffet?");
  const queriedMenuItem = guest.locator("#message-list .message-row.assistant:last-child .entity-card-menu_item");
  await queriedMenuItem.waitFor({ state: "visible", timeout: 15_000 });
  assert.match(await queriedMenuItem.innerText(), /PHP 1,450 \(DEMO\)/);
  assert.match(await queriedMenuItem.innerText(), /Buffet selection of Filipino and continental dishes/);
  const queriedMenuImages = await assertImages(guest, queriedMenuItem.locator(".entity-card-image"), "queried menu item");
  await screenshot(guest, "v2-05-menu-item-question");
  check("a specific menu question returns its published description, demo price, and local image", true, `${queriedMenuImages} decoded image`);

  reply = await sendGuest(guest, "Show me the room types.");
  const roomCards = guest.locator("#message-list .message-row.assistant:last-child .entity-card-room");
  assert.equal(await roomCards.count(), 6, `The guest room catalog should contain six room types. Reply: ${reply}`);
  assert.match(await roomCards.allTextContents().then((items) => items.join(" ")), /PHP [0-9,]+/);
  assert.match(reply, /synthetic demo references|not live bookings/i);
  const roomImages = await assertImages(guest, roomCards.locator(".entity-card-image"), "room cards");
  await screenshot(guest, "v2-05-room-catalog");
  check("guest room cards show six room types, demo rates, and local images", true, `${await roomCards.count()} cards; ${roomImages} decoded images`);

  reply = await sendGuest(guest, "What time is checkout?");
  assert.match(reply, /12:00/);
  await screenshot(guest, "v2-06-checkout-policy");
  check("guest checkout policy is retrieved from the imported property", true, reply.slice(0, 180));

  reply = await sendGuest(guest, "Where is the Infinity Pool?");
  const facilityRow = guest.locator("#message-list .message-row.assistant:last-child");
  const facilityCard = facilityRow.locator(".entity-card-facility").filter({ hasText: "Infinity Pool" });
  await facilityCard.waitFor({ state: "visible", timeout: 15_000 });
  const facilityImages = await assertImages(guest, facilityCard.locator(".entity-card-image"), "Infinity Pool facility card");
  const map = facilityRow.locator(".map-panel");
  await map.waitFor({ state: "visible", timeout: 15_000 });
  const mapImages = await assertImages(guest, map.locator(".floor-map-image"), "guest conceptual map");
  assert.match(await facilityCard.innerText(), /Level|floor/i);
  assert.equal(await facilityRow.locator(".directions-panel").count(), 0, "Conceptual map data must not be shown as live directions.");
  await screenshot(guest, "v2-07-facility-and-conceptual-map");
  check("facility lookup displays its local image and conceptual floor map without live directions", true, `${facilityImages + mapImages} decoded images`);

  reply = await sendGuest(guest, "What attractions are near the hotel?");
  const placeCards = guest.locator("#message-list .message-row.assistant:last-child .entity-card-place");
  assert.ok(await placeCards.count() >= 6, `Expected all six V2 attraction samples; found ${await placeCards.count()}.`);
  const attractionImages = await assertImages(guest, placeCards.locator(".entity-card-image"), "nearby attraction cards");
  assert.match(reply, /live hours|travel details|verified/i);
  await screenshot(guest, "v2-08-nearby-attractions");
  check("nearby recommendations include V2 samples and local images", true, `${await placeCards.count()} cards; ${attractionImages} decoded images`);

  reply = await sendGuest(guest, "Can you bring two extra pillows to room 1208?");
  const review = guest.locator("#message-list .message-row.assistant:last-child .request-review");
  await review.waitFor({ state: "visible", timeout: 15_000 });
  assert.match(await review.innerText(), /Extra Pillows/i);
  const confirmation = review.getByRole("button", { name: "Confirm request" });
  assert.ok(await confirmation.isEnabled());
  await confirmation.click();
  const confirmed = guest.locator("#message-list .verified-confirmation").last();
  await confirmed.waitFor({ state: "visible", timeout: 20_000 });
  const confirmationText = await confirmed.innerText();
  const requestReference = confirmationText.match(/Reference:\s*([A-Za-z0-9_-]+)/)?.[1];
  assert.ok(requestReference, "The guest confirmation did not show the backend request ID.");
  reply = await sendGuest(guest, "Where is my service request?");
  const status = guest.locator("#message-list .message-row.assistant:last-child .request-status-panel");
  await status.waitFor({ state: "visible", timeout: 15_000 });
  assert.match(await status.innerText(), /Extra Pillows/i);
  assert.match(await status.innerText(), /Received|Assigned|In progress/);
  await screenshot(guest, "v2-09-request-confirmation-and-status");
  check("guest request is explicitly confirmed, gets a backend ID, and appears in status", true, requestReference);

  reply = await sendGuest(guest, "Can the hotel arrange a helicopter transfer?");
  assert.match(reply, /couldn't verify|do not have|don't have|front desk|concierge/i);
  assert.doesNotMatch(reply, /helicopter (?:transfer|service) is available/i);
  check("unknown hotel service is not fabricated", true, reply.slice(0, 160));
  const crossProperty = await guest.request.get(`${baseUrl}/api/guest/recommendations?property_id=not-a-demo-property`);
  check("unknown cross-property guest scope is denied", crossProperty.status() === 403 || crossProperty.status() === 404, `HTTP ${crossProperty.status()}`);

  const adminContext = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const admin = await adminContext.newPage();
  watchPage(admin);
  await admin.goto(`${baseUrl}/admin/login`, { waitUntil: "domcontentloaded" });
  await admin.locator("#username").fill(credentials.username);
  await admin.locator("#password").fill(credentials.password);
  await admin.locator("#sign-in").click();
  await admin.waitForURL("**/admin", { timeout: 20_000 });
  await admin.locator("#overview-title").waitFor({ state: "visible", timeout: 20_000 });
  assert.match(await admin.locator("#overview-title").innerText(), /Hotel De Luna/);
  await screenshot(admin, "v2-10-admin-dashboard");
  check("Admin UI login opens the imported property dashboard", true, await admin.locator("#overview-title").innerText());

  await clickAdminNav(admin, "rooms");
  const roomPanel = admin.locator("#rooms");
  await roomPanel.waitFor({ state: "visible" });
  const adminRooms = roomPanel.locator(".room-entry");
  assert.equal(await adminRooms.count(), 6, "Admin should show all six imported room types.");
  assert.ok((await adminRooms.first().innerText()).includes("Demo nightly reference"));
  const adminRoomImages = await assertImages(admin, roomPanel.locator(".room-entry-images img"), "Admin room gallery");
  await screenshot(admin, "v2-11-admin-room-catalog");
  check("Admin Rooms panel shows six rates and stored galleries", true, `${await adminRooms.count()} rooms; ${adminRoomImages} images`);

  await clickAdminNav(admin, "restaurants");
  const restaurantPanel = admin.locator("#restaurants");
  await restaurantPanel.waitFor({ state: "visible" });
  await restaurantPanel.getByText("Luna Grand Dining", { exact: false }).first().waitFor({ state: "visible" });
  await restaurantPanel.getByText("Sky Lounge", { exact: false }).first().waitFor({ state: "visible" });
  const restaurantWorkflow = restaurantPanel.locator("#restaurant-workflow-disclosure");
  await restaurantWorkflow.locator("summary").click();
  const restaurantSelector = restaurantPanel.locator("#restaurant-workflow-select");
  const restaurantIds = await restaurantSelector.locator("option").evaluateAll((options) => options.map((option) => option.value).filter(Boolean));
  assert.equal(restaurantIds.length, 4, "Admin should list all four restaurants in the menu manager.");
  let adminMenuItems = 0;
  const adminMenuStatuses = [];
  for (const restaurantId of restaurantIds) {
    if (await restaurantSelector.inputValue() !== restaurantId) {
      const menusResponse = admin.waitForResponse((response) =>
        response.url().includes(`/restaurants/${restaurantId}/menus`) && response.status() === 200);
      await restaurantSelector.selectOption(restaurantId);
      await menusResponse;
    }
    await admin.waitForFunction((expectedId) =>
      document.querySelector("#restaurant-workflow-select")?.value === expectedId
      && document.querySelectorAll("#restaurant-menu-list .menu-item-row").length > 0, restaurantId);
    adminMenuItems += await restaurantPanel.locator("#restaurant-menu-list .menu-item-row").count();
    adminMenuStatuses.push(...await restaurantPanel.locator("#restaurant-menu-list .compact-row:not(.menu-item-row)").allTextContents());
  }
  assert.equal(adminMenuItems, 40, `Admin should show all 40 imported menu items; found ${adminMenuItems}.`);
  assert.ok(adminMenuStatuses.length > 0 && adminMenuStatuses.every((row) => /published/i.test(row)), "Admin menus should be published for guest use.");
  await screenshot(admin, "v2-12-admin-restaurants");
  check("Admin Restaurants panel lists four venues and all forty published menu items", true, `${restaurantIds.length} restaurants; ${adminMenuItems} menu items`);

  await clickAdminNav(admin, "facilities");
  const facilityPanel = admin.locator("#facilities");
  await facilityPanel.waitFor({ state: "visible" });
  await facilityPanel.getByText("Infinity Pool", { exact: false }).first().waitFor({ state: "visible" });
  const adminFacilityCount = await facilityPanel.locator("#facility-list tr").count();
  assert.equal(adminFacilityCount, 11, `Admin should list all 11 V2 hotel facilities; found ${adminFacilityCount}.`);
  await screenshot(admin, "v2-13-admin-facilities");
  check("Admin Facilities panel lists all eleven imported facilities", true, `${adminFacilityCount} facility records`);

  await clickAdminNav(admin, "hotel-information");
  const checkoutInput = admin.locator("#hotel-info-checkout");
  await checkoutInput.waitFor({ state: "visible" });
  const originalCheckout = await checkoutInput.inputValue();
  const saveHotelInfo = async (value) => {
    await checkoutInput.fill(value);
    const responsePromise = admin.waitForResponse((response) =>
      response.url().endsWith("/api/admin/properties/hotel-de-luna-demo") && response.request().method() === "PUT");
    await admin.locator("#save-hotel-information").click();
    const response = await responsePromise;
    assert.ok(response.ok(), `Hotel Information save failed: HTTP ${response.status()}`);
  };
  try {
    await saveHotelInfo("12:30");
    reply = await sendGuest(guest, "What time is checkout?");
    assert.match(reply, /12:30/);
    check("Admin Hotel Information edits are published to guest answers", true, "Checkout changed to 12:30 and was retrieved by the guest UI");
  } finally {
    await saveHotelInfo(originalCheckout);
  }
  reply = await sendGuest(guest, "What time is checkout?");
  assert.match(reply, /12:00/);
  check("the original imported checkout policy is restored after the edit check", true, reply.slice(0, 160));

  await clickAdminNav(admin, "zones-maps");
  const mapsPanel = admin.locator("#zones");
  await mapsPanel.waitFor({ state: "visible" });
  const buildingSelect = mapsPanel.locator("#zone-building-select");
  const buildingOption = buildingSelect.locator("option").filter({ hasText: "Hotel De Luna V2 — Conceptual Maps" }).first();
  const buildingValue = await buildingOption.getAttribute("value");
  assert.ok(buildingValue, "The V2 conceptual map building is missing from Admin.");
  await buildingSelect.selectOption(buildingValue);
  const floorSelect = mapsPanel.locator("#zone-floor-select");
  const v2FloorCount = await floorSelect.locator("option").count();
  assert.equal(v2FloorCount, 19, `Admin should list all 19 imported V2 conceptual floors; found ${v2FloorCount}.`);
  const groundOption = floorSelect.locator("option").filter({ hasText: "Ground Floor · conceptual demo" }).first();
  const groundValue = await groundOption.getAttribute("value");
  assert.ok(groundValue, "The V2 conceptual Ground Floor is missing from Admin.");
  await floorSelect.selectOption(groundValue);
  await admin.waitForFunction(() => document.querySelector("#map-plan-name")?.textContent?.includes("hotel-de-luna-v2-floor-G-conceptual.png"), null, { timeout: 15_000 });
  await admin.locator("#floor-map-canvas").waitFor({ state: "visible" });
  await screenshot(admin, "v2-14-admin-conceptual-map");
  check("Admin Maps panel lists all nineteen V2 floors and opens the Ground Floor image", true, `${v2FloorCount} floors; ${await mapsPanel.locator("#map-plan-name").innerText()}`);

  await clickAdminNav(admin, "guest-requests");
  const requestsPanel = admin.locator("#requests");
  await requestsPanel.waitFor({ state: "visible" });
  const createdRequest = requestsPanel.locator(".service-request-card").filter({ hasText: "Extra Pillows" });
  await createdRequest.first().waitFor({ state: "visible", timeout: 15_000 });
  await screenshot(admin, "v2-15-admin-service-request");
  check("Admin request queue shows the confirmed guest request", true, requestReference);

  const deniedContext = await browser.newContext();
  const deniedAdmin = await deniedContext.request.get(`${baseUrl}/api/admin/properties/hotel-de-luna-demo`);
  check("unauthenticated Admin property read is denied", deniedAdmin.status() === 401, `HTTP ${deniedAdmin.status()}`);
  await deniedContext.close();

  for (const viewport of [
    { name: "mobile-390", width: 390, height: 844, device: devices["iPhone 13"] },
    { name: "mobile-412", width: 412, height: 915, device: devices["Pixel 7"] },
  ]) {
    const mobileContext = await browser.newContext({ ...viewport.device, viewport: { width: viewport.width, height: viewport.height } });
    const mobile = await mobileContext.newPage();
    watchPage(mobile);
    await mobile.goto(`${baseUrl}/?experience=intelligent`, { waitUntil: "domcontentloaded" });
    await mobile.locator("#app-shell").waitFor({ state: "visible", timeout: 20_000 });
    await sendGuest(mobile, "I'm hungry.");
    const cards = mobile.locator("#message-list .message-row.assistant:last-child .entity-card-restaurant");
    assert.equal(await cards.count(), 4, `${viewport.name} should show all four restaurant cards.`);
    await assertNoHorizontalOverflow(mobile, viewport.name);
    await screenshot(mobile, `v2-${viewport.name}`);
    await mobileContext.close();
  }
  check("mobile guest layout has no horizontal overflow", report.responsive.length === 2, "390px and 412px viewports");

  await adminContext.close();
  await guestContext.close();
  check("browser made no external requests", report.externalRequests.length === 0, report.externalRequests.join(", ") || "loopback only");
  check("browser has no JavaScript page errors", report.pageErrors.length === 0, report.pageErrors.join(" | ") || "none");
  check("browser has no failed local requests", report.failedLocalRequests.length === 0, report.failedLocalRequests.join(" | ") || "none");
  report.finishedAt = new Date().toISOString();
  report.consoleErrors = [...new Set(report.consoleErrors)];
  const reportPath = resolve(outputDir, "hotel-de-luna-v2-results.json");
  await writeFile(reportPath, JSON.stringify(report, null, 2));
  console.log(JSON.stringify({
    status: "PASS",
    checks: report.checks.length,
    decodedImages: report.images.length,
    screenshots: report.screenshots.length,
    report: reportPath,
    consoleErrors: report.consoleErrors,
    pageErrors: report.pageErrors,
    failedLocalRequests: report.failedLocalRequests,
    externalRequests: report.externalRequests,
  }, null, 2));
} finally {
  await browser.close();
}
