import { expect, test } from "@playwright/test";
import { ensureTestProperty } from "./support.js";

const csrfByRequest = new WeakMap();

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

async function openPanel(page, label) {
  await page.locator('body[data-admin-ready="true"]').waitFor();
  const button = page.locator(".nav-item").filter({ hasText: label }).first();
  await button.evaluate((element) => {
    const group = element.closest("details");
    if (group) group.open = true;
  });
  await button.click();
}

async function openHiddenPanel(page, panelId) {
  await page.locator('body[data-admin-ready="true"]').waitFor();
  await page.evaluate((id) => window.activatePanel(id), panelId);
  await expect(page.locator(`#${panelId}`)).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await loginAdmin(page.request);
});

test("admin data buttons: catalog, request, and recommendation workflows", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The mutation workflow only needs one browser profile.");
  const suffix = Date.now().toString(36);
  const departmentName = `Button Audit ${suffix}`;
  const serviceName = `Audit Service ${suffix}`;
  const recommendationName = `Audit Place ${suffix}`;

  await page.goto("/admin");
  await openPanel(page, "Service Catalog");

  await page.locator("#department-name").fill(departmentName);
  await page.getByRole("button", { name: "Save Department" }).click();
  const departmentRow = page.locator("#department-list .compact-row").filter({ hasText: departmentName });
  await expect(departmentRow).toBeVisible();
  await departmentRow.getByRole("button", { name: "Edit" }).click();
  await expect(page.locator("#department-name")).toHaveValue(departmentName);

  await page.locator("#catalog-service-name").fill(serviceName);
  await page.locator("#catalog-service-department").selectOption({ label: departmentName });
  await page.locator("#catalog-service-keywords").fill(`audit-${suffix}`);
  await page.getByRole("button", { name: "Save Service" }).click();
  let serviceRow = page.locator("#catalog-service-list .compact-row").filter({ hasText: serviceName }).first();
  await expect(serviceRow).toBeVisible();
  await serviceRow.getByRole("button", { name: "Edit" }).click();
  await expect(page.locator("#catalog-service-name")).toHaveValue(serviceName);
  await serviceRow.getByRole("button", { name: "Duplicate" }).click();
  await expect(page.locator("#catalog-service-list .compact-row").filter({ hasText: serviceName })).toHaveCount(2);

  await openPanel(page, "Guest Requests");
  await expect(page.locator("#request-last-updated")).toContainText("Updated");
  await page.getByRole("button", { name: "New request" }).click();
  await page.locator("#service-room").fill("1503");
  await page.locator("#service-type").selectOption({ label: serviceName });
  await page.locator("#service-description").fill("Button workflow verification");
  await page.getByRole("button", { name: "Create Request" }).click();
  const requestRow = page.locator("#service-request-list article").filter({ hasText: serviceName }).first();
  await expect(requestRow).toBeVisible();
  await requestRow.getByRole("button", { name: /Open details for request/ }).click();
  await page.locator("#service-request-details-content").getByRole("button", { name: "Mark Assigned", exact: true }).click();
  await expect(requestRow).toContainText("Assigned");

  await openPanel(page, "Recommendations");
  await page.locator("#recommendation-name").fill(recommendationName);
  await page.locator("#recommendation-category").fill("Audit");
  await page.locator("#recommendation-description").fill("Created by the button workflow test.");
  await page.getByRole("button", { name: "Save Recommendation" }).click();
  const recommendationRow = page.locator("#recommendation-list .compact-row").filter({ hasText: recommendationName });
  await expect(recommendationRow).toBeVisible();
  await recommendationRow.getByRole("button", { name: "Edit" }).click();
  await expect(page.locator("#recommendation-name")).toHaveValue(recommendationName);
  await recommendationRow.getByRole("button", { name: "Delete" }).click();
  await expect(recommendationRow).toHaveCount(0);

  await openPanel(page, "Service Catalog");
  serviceRow = page.locator("#catalog-service-list .compact-row").filter({ hasText: serviceName }).first();
  await serviceRow.getByRole("button", { name: "Archive" }).click();
  serviceRow = page.locator("#catalog-service-list .compact-row").filter({ hasText: serviceName }).first();
  await expect(serviceRow).toContainText("Unavailable");
  await serviceRow.getByRole("button", { name: "Delete" }).click();
});

test("room types can be created, edited, and deleted with confirmation", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The room inventory workflow only needs one browser.");
  const roomName = `Room type audit ${Date.now().toString(36)}`;
  await page.goto("/admin");
  await openPanel(page, "Rooms");
  await page.locator("#room-name").fill(roomName);
  await page.locator("#room-description").fill("Guest-facing room type created by the admin workflow check.");
  await page.locator("#room-capacity").fill("2");
  await page.getByRole("button", { name: "Save Room" }).click();
  const roomRow = page.locator("#room-list .compact-row").filter({ hasText: roomName });
  await expect(roomRow).toBeVisible();
  await roomRow.getByRole("button", { name: "Edit" }).click();
  await page.locator("#room-description").fill("Updated guest-facing room description.");
  await page.getByRole("button", { name: "Save Room" }).click();
  await expect(roomRow).toContainText("Updated guest-facing room description.");
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain(roomName);
    await dialog.dismiss();
  });
  await roomRow.getByRole("button", { name: "Delete" }).click();
  await expect(roomRow).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await roomRow.getByRole("button", { name: "Delete" }).click();
  await expect(roomRow).toHaveCount(0);
});

test("admin restaurant workflow creates, approves, publishes, edits, and archives venue content", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The mutation workflow only needs one browser profile.");
  const suffix = Date.now().toString(36);
  const restaurantName = `Button Restaurant ${suffix}`;
  const menuName = `Button Menu ${suffix}`;
  const itemName = `Button Item ${suffix}`;
  const promotionName = `Button Promotion ${suffix}`;

  await page.goto("/admin");
  await openPanel(page, "Restaurants");
  await page.locator("#add-restaurant").click();
  await page.locator("#restaurant-name").fill(restaurantName);
  await page.locator("#restaurant-hours-monday").fill("06:30-22:00");
  await page.locator("#restaurant-meals").fill("breakfast, dinner");
  await page.locator("#restaurant-internal-notes").fill("Staff-only workflow test note.");
  await page.getByRole("button", { name: "Add Restaurant", exact: true }).last().click();

  const restaurantRow = page.locator("#restaurant-list .compact-row").filter({ hasText: restaurantName });
  await expect(restaurantRow).toBeVisible();
  await restaurantRow.getByRole("button", { name: "Edit" }).click();
  await expect(page.locator("#restaurant-hours-monday")).toHaveValue("06:30-22:00");
  await page.locator("#restaurant-location").fill("Test dining room");
  await page.getByRole("button", { name: "Save Changes" }).click();
  await expect(restaurantRow).toContainText("Test dining room");
  await page.locator("#restaurant-workflow-disclosure > summary").click();
  await page.locator("#restaurant-workflow-select").selectOption({ label: restaurantName });

  await page.locator("#restaurant-menu-name").fill(menuName);
  await page.locator("#restaurant-menu-period").fill("dinner");
  await page.getByRole("button", { name: "Add Menu", exact: true }).click();
  const menuRow = page.locator("#restaurant-menu-list .compact-row").filter({ hasText: menuName }).first();
  await expect(menuRow).toContainText("pending_approval");
  await page.locator("#restaurant-menu-select").selectOption({ index: 0 });
  await page.locator("#restaurant-item-name").fill(itemName);
  await page.locator("#restaurant-item-price").fill("24.00");
  await page.getByRole("button", { name: "Add Menu Item" }).click();
  await expect(page.locator("#restaurant-menu-list .compact-row").filter({ hasText: itemName })).toBeVisible();
  await menuRow.getByRole("button", { name: "Approve" }).click();
  await menuRow.getByRole("button", { name: "Publish" }).click();
  await expect(menuRow).toContainText("published");

  await page.locator("#restaurant-promotion-title").fill(promotionName);
  await page.locator("#restaurant-promotion-description").fill("Submitted through the restaurant admin workflow.");
  await page.getByRole("button", { name: "Submit for Approval" }).click();
  const promotionRow = page.locator("#restaurant-promotion-list .compact-row").filter({ hasText: promotionName });
  await expect(promotionRow).toContainText("pending_approval");
  await promotionRow.getByRole("button", { name: "Approve" }).click();
  await promotionRow.getByRole("button", { name: "Publish" }).click();
  await expect(promotionRow).toContainText("published");

  page.once("dialog", (dialog) => dialog.accept());
  await restaurantRow.getByRole("button", { name: "Delete" }).click();
  await expect(restaurantRow).toHaveCount(0);
});

test("admin restaurant assignment checkboxes save only the selected restaurant ids", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The mutation workflow only needs one browser profile.");
  const suffix = Date.now().toString(36);
  const propertyResponse = await page.request.get("/api/admin/properties");
  expect(propertyResponse.ok()).toBeTruthy();
  const propertyId = (await propertyResponse.json()).properties[0].property_id;
  const authResponse = await page.request.get("/api/admin/auth/me");
  expect(authResponse.ok()).toBeTruthy();
  const csrf = (await authResponse.json()).user.csrf_token;
  const headers = { "X-CSRF-Token": csrf };

  const createdRestaurants = [];
  for (const name of [`Assignment Grill ${suffix}`, `Assignment Cafe ${suffix}`]) {
    const response = await page.request.post(`/api/admin/properties/${propertyId}/restaurants`, {
      headers,
      data: { data: { name } },
    });
    expect(response.ok()).toBeTruthy();
    createdRestaurants.push(await response.json());
  }

  await page.goto("/admin");
  await openPanel(page, "Users");
  await page.locator("#create-user-button").click();
  await page.locator("#admin-property").selectOption(propertyId);
  await page.locator("#admin-role").selectOption({ label: "Restaurant Staff" });
  const assignmentList = page.locator("#restaurant-assignment-list");
  await page.waitForLoadState("networkidle");
  for (const restaurant of createdRestaurants) {
    await expect(assignmentList.getByText(restaurant.name, { exact: true })).toHaveCount(1);
  }

  const checkboxes = assignmentList.locator("input[type=checkbox]");
  await page.locator("#restaurant-assignment-select-all").click();
  await expect(assignmentList.locator("input:checked")).toHaveCount(await checkboxes.count());
  await page.locator("#restaurant-assignment-clear").click();
  await expect(assignmentList.locator("input:checked")).toHaveCount(0);
  await assignmentList.locator(`input[value="${createdRestaurants[0].restaurant_id}"]`).check();

  const username = `restaurant.staff.${suffix}`;
  await page.locator("#admin-username").fill(username);
  await page.locator("#admin-display-name").fill("Assigned Restaurant Staff");
  await page.locator("#admin-password").fill("RestaurantStaff123!");
  await page.locator("#admin-password-confirm").fill("RestaurantStaff123!");
  await page.locator("#save-user-button").click();
  await expect(page.locator("#user-dialog")).not.toBeVisible();

  const usersResponse = await page.request.get("/api/admin/users");
  expect(usersResponse.ok()).toBeTruthy();
  const createdUser = (await usersResponse.json()).users.find((user) => user.username === username);
  expect(createdUser.restaurant_ids).toEqual([createdRestaurants[0].restaurant_id]);
});

test("admin operations buttons: map, stay memory, location, and intro", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The mutation workflow only needs one browser profile.");
  test.setTimeout(90_000);
  const suffix = Date.now().toString(36);
  const mac = "AA:BB:CC:DD:EE:42";
  const accessPoint = `ap-audit-${suffix}`;

  await page.goto("/admin");
  await openPanel(page, "Zones & Maps");
  const buildingName = `Audit Building ${suffix}`;
  const floorName = `Audit Floor ${suffix}`;
  const zoneName = `Audit Zone ${suffix}`;
  await page.locator("#add-map-building").click();
  await page.locator("#map-structure-name").fill(buildingName);
  await page.locator("#map-structure-submit").click();
  await expect(page.locator("#zone-building-select")).toHaveValue(/.+/);
  await page.locator("#add-map-floor").click();
  await page.locator("#map-structure-name").fill(floorName);
  await page.locator("#map-floor-level").fill("1");
  await page.locator("#map-structure-submit").click();
  await expect(page.locator("#zone-floor-select")).toHaveValue(/.+/);
  await expect(page.locator("#map-canvas-empty")).toBeVisible();
  await page.locator("#map-empty-start-drawing").click();
  await expect(page.locator("#floor-map-canvas")).toHaveAttribute("data-tool", "rectangle");
  await expect(page.locator("#map-canvas-empty")).toBeHidden();

  await page.locator('[data-map-tool="rectangle"]').click();
  const canvas = page.locator("#floor-map-canvas");
  const canvasBounds = await canvas.boundingBox();
  expect(canvasBounds).not.toBeNull();
  await page.mouse.move(canvasBounds.x + canvasBounds.width * 0.1, canvasBounds.y + canvasBounds.height * 0.1);
  await page.mouse.down();
  await page.mouse.move(canvasBounds.x + canvasBounds.width * 0.8, canvasBounds.y + canvasBounds.height * 0.8);
  await page.mouse.up();
  await expect(page.locator("#map-object-form")).toBeVisible();
  await page.locator("#map-object-name").fill(zoneName);
  await page.locator("#save-map-object").click();
  await expect(page.locator("#toast")).toContainText("Map changes saved");

  await page.locator('[data-map-tool="access_point"]').click();
  await canvas.click({ position: { x: canvasBounds.width / 2, y: canvasBounds.height / 2 } });
  await expect(page.locator("#map-object-form")).toBeVisible();
  await page.locator("#map-linked-zone").selectOption({ label: zoneName });
  await page.locator("#map-object-name").fill(`Audit AP ${suffix}`);
  await page.locator("#map-ap-identifier").fill(accessPoint);
  await page.locator("#save-map-object").click();
  await expect(page.locator("#toast")).toContainText("Map changes saved");

  await page.locator("#floor-map-upload").setInputFiles({
    name: `audit-${suffix}.svg`,
    mimeType: "image/svg+xml",
    buffer: Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'),
  });
  await expect(page.locator("#toast")).toContainText("Floor plan uploaded");
  await page.locator("#map-save-draft").click();
  await expect(page.locator("#toast")).toContainText("Map draft saved");
  await expect(page.locator("#map-revision-preview")).toContainText("Preview revision");
  await page.locator("#map-preview-draft").click();
  await expect(page.locator("#toast")).toContainText("Map draft preview is ready");
  await page.locator("#map-publish-draft").click();
  await expect(page.locator("#map-publish-status")).toContainText("Published revision");

  await openPanel(page, "Guest Sessions");
  await expect(page.locator("#session-last-refreshed")).toContainText("Updated");
  let sessionReads = 0;
  page.on("request", (request) => { if (/\/sessions$/.test(new URL(request.url()).pathname)) sessionReads += 1; });
  const sessionReadsBeforeRefresh = sessionReads;
  await page.getByRole("button", { name: "Refresh guest session records" }).click();
  await expect.poll(() => sessionReads).toBeGreaterThan(sessionReadsBeforeRefresh);
  const guestSessionResponse = await page.request.post("/api/session/start", {
    data: { client_id: `location-audit-${suffix}`, property_id: "e2e-property" },
  });
  expect(guestSessionResponse.ok(), await guestSessionResponse.text()).toBeTruthy();
  const guestSessionId = (await guestSessionResponse.json()).session_id;
  await page.getByRole("button", { name: "Link a device" }).click();
  await page.locator("#session-raw-mac").fill(mac);
  await page.locator("#session-room").fill("1503");
  await page.locator(".session-advanced-fields").evaluate((element) => { element.open = true; });
  await page.locator("#session-concierge-id").fill(guestSessionId);
  await page.getByRole("button", { name: "Create / Restore Stay" }).click();
  await expect(page.locator("#toast")).toContainText("Guest stay created or restored");
  await expect(page.locator("#memory-stay-id")).not.toHaveValue("");
  await page.locator("#memory-summary").fill("Verified through the admin button workflow.");
  await page.locator("#save-stay-memory").click();
  await expect(page.locator("#toast")).toContainText("Stay notes saved");
  await page.locator("#session-guest360-close").click();

  await openPanel(page, "Location");
  await expect(page.locator("#location-analytics-unavailable-copy")).toContainText("Property location collection is off");
  await page.getByRole("button", { name: "Load report" }).click();
  await expect(page.locator("#location-report")).toContainText("No zone activity was recorded in this period.");
  await page.locator('[data-location-panel="zones"]').first().click();
  await expect(page.locator("#zones")).toBeVisible();

  await openHiddenPanel(page, "intro");
  const originalMode = await page.locator("#intro-mode").inputValue();
  const originalMessage = await page.locator("#intro-message").inputValue();
  await page.locator("#intro-mode").selectOption("generate_from_logo");
  await page.locator("#intro-message").fill(`Welcome ${suffix}`);
  await page.locator("#save-intro").click();
  await expect(page.locator("#toast")).toContainText("Intro experience saved");
  if (originalMode === "none") {
    await page.locator("#intro-mode").selectOption("none");
  } else {
    await page.locator("#intro-message").fill(originalMessage);
  }
  await page.locator("#save-intro").click();
});

test("map editor creates and edits explicit cross-floor route transitions", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The route editor workflow only needs one browser profile.");
  const suffix = Date.now().toString(36);
  const csrf = csrfByRequest.get(page.request);
  const propertyId = await ensureTestProperty(page.request, csrf);
  const headers = { "X-CSRF-Token": csrf };
  const apiBase = `/api/admin/properties/${propertyId}`;
  const create = async (path, data) => {
    const response = await page.request.post(`${apiBase}${path}`, { headers, data: { data } });
    expect(response.ok(), await response.text()).toBeTruthy();
    return response.json();
  };

  const building = await create("/buildings", { name: `Route Building ${suffix}` });
  const lowerFloor = await create("/floors", { building_id: building.building_id, name: `Route Level 1 ${suffix}`, level: 1 });
  const upperFloor = await create("/floors", { building_id: building.building_id, name: `Route Level 2 ${suffix}`, level: 2 });
  const lowerStart = await create("/navigation/nodes", { floor_id: lowerFloor.floor_id, label: `Route Start ${suffix}`, x: 100, y: 100 });
  const lowerEnd = await create("/navigation/nodes", { floor_id: lowerFloor.floor_id, label: `Route Local ${suffix}`, x: 260, y: 100 });
  const upperEnd = await create("/navigation/nodes", { floor_id: upperFloor.floor_id, label: `Route Upstairs ${suffix}`, x: 120, y: 180 });

  await page.goto("/admin");
  await openPanel(page, "Zones & Maps");
  await page.locator("#zone-building-select").selectOption(building.building_id);
  await page.locator("#zone-floor-select").selectOption(lowerFloor.floor_id);
  await page.locator('[data-map-tool="connect"]').click();
  const canvas = page.locator("#floor-map-canvas");
  const bounds = await canvas.boundingBox();
  expect(bounds).not.toBeNull();
  const clickMapPoint = async (x, y) => page.mouse.click(bounds.x + (x / 1200) * bounds.width, bounds.y + (y / 720) * bounds.height);
  await clickMapPoint(lowerStart.x, lowerStart.y);
  await clickMapPoint(lowerEnd.x, lowerEnd.y);

  await expect(page.locator("#map-edge-fields")).toBeVisible();
  await page.locator("#map-edge-to-select").selectOption(upperEnd.node_id);
  await page.locator("#save-map-object").click();
  await expect(page.locator("#toast")).toContainText("Routes between floors require an explicit");

  await page.locator("#map-edge-transition").selectOption("stairs");
  await page.locator("#map-edge-accessible").check();
  await page.locator("#save-map-object").click();
  await expect(page.locator("#toast")).toContainText("Stair routes cannot be marked accessible");

  await page.locator("#map-edge-transition").selectOption("elevator");
  await page.locator("#map-edge-bidirectional").uncheck();
  await page.locator("#map-object-visible").uncheck();
  await page.locator("#save-map-object").click();
  await expect(page.locator("#toast")).toContainText("Map changes saved");

  const overview = await page.request.get(`${apiBase}/zones`).then((response) => response.json());
  const savedEdge = overview.navigation_edges.find((edge) => edge.from_node_id === lowerStart.node_id && edge.to_node_id === upperEnd.node_id);
  expect(savedEdge).toMatchObject({ transition_type: "elevator", accessible: true, bidirectional: false, guest_visible: false });

  await page.reload();
  await openPanel(page, "Zones & Maps");
  await page.locator("#zone-building-select").selectOption(building.building_id);
  await page.locator("#zone-floor-select").selectOption(lowerFloor.floor_id);
  const routeRow = page.locator("#zone-tree .map-object-row").filter({ hasText: `Route Start ${suffix}` }).filter({ hasText: `Route Upstairs ${suffix}` });
  await expect(routeRow).toBeVisible();
  await routeRow.click();
  await expect(page.locator("#map-edge-from-select")).toHaveValue(lowerStart.node_id);
  await expect(page.locator("#map-edge-to-select")).toHaveValue(upperEnd.node_id);
  await expect(page.locator("#map-edge-transition")).toHaveValue("elevator");
  await expect(page.locator("#map-edge-accessible")).toBeChecked();
  await expect(page.locator("#map-edge-bidirectional")).not.toBeChecked();
  await expect(page.locator("#map-object-visible")).not.toBeChecked();
});

test("admin account buttons: create, edit, reset, status, activity, revoke, and delete", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The mutation workflow only needs one browser profile.");
  const suffix = Date.now().toString(36);
  const username = `audit_${suffix}`;
  const password = "AuditPassword123!";

  await page.goto("/admin");
  await openPanel(page, "Users");
  await page.getByRole("button", { name: "Create User" }).click();
  await page.locator("#admin-username").fill(username);
  await page.locator("#admin-display-name").fill("Button Audit User");
  await page.locator("#admin-password").fill(password);
  await page.locator("#admin-password-confirm").fill(password);
  await page.locator("#save-user-button").click();

  let row = page.locator("#users-table-body tr").filter({ hasText: `@${username}` });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Edit" }).click();
  await page.locator("#admin-display-name").fill("Button Audit User Updated");
  await page.locator("#save-user-button").click();
  row = page.locator("#users-table-body tr").filter({ hasText: `@${username}` });
  await expect(row).toContainText("Button Audit User Updated");

  await row.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Reset Password" }).click();
  await page.locator("#password-reset-value").fill(password);
  await page.locator("#password-reset-confirm").fill(password);
  await page.locator("#password-reset-dialog").getByRole("button", { name: "Reset Password" }).click();
  await expect(page.locator("#toast")).toContainText("Temporary password created");

  await page.locator("#profile-button").click();
  await page.getByRole("button", { name: "Logout" }).click();
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page.locator("#security")).toBeVisible();
  const changePasswordButton = page.getByRole("button", { name: "Change Password" });
  await expect(changePasswordButton).toHaveClass(/btn-primary/);
  expect(await changePasswordButton.evaluate((element) => element.getBoundingClientRect().height)).toBeGreaterThanOrEqual(42);
  await page.locator("#current-password").fill(password);
  await page.locator("#new-password").fill("AuditPassword456!");
  await page.locator("#confirm-new-password").fill("AuditPassword456!");
  await page.getByRole("button", { name: "Change Password" }).click();
  await expect(page.locator("#toast")).toContainText("Password changed");

  await page.locator("#profile-button").click();
  await page.getByRole("button", { name: "Logout" }).click();
  await page.locator("#username").fill("admin");
  await page.locator("#password").fill("PlaywrightOnly-Admin-123!");
  await page.getByRole("button", { name: "Sign In" }).click();
  await openPanel(page, "Users");

  row = page.locator("#users-table-body tr").filter({ hasText: `@${username}` });
  await row.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Disable Account" }).click();
  await expect(row).toContainText("disabled");
  await row.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Enable Account" }).click();
  await expect(row).toContainText("active");

  await row.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Revoke Sessions" }).click();
  await expect(page.locator("#toast")).toContainText("Active sessions revoked");
  await row.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "View Activity" }).click();
  await expect(page.locator("#audit")).toBeVisible();
  await expect(page.locator("#audit-username")).toHaveValue(username);

  await openPanel(page, "Users");
  row = page.locator("#users-table-body tr").filter({ hasText: `@${username}` });
  await row.getByRole("button", { name: "Actions" }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete User" }).click();
  await expect(row).toHaveCount(0);
});

test("admin role buttons create and edit a custom role", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The mutation workflow only needs one browser profile.");
  const roleName = `Button Audit Role ${Date.now().toString(36)}`;

  await page.goto("/admin");
  await openPanel(page, "Roles");
  await page.getByRole("button", { name: "Create Role" }).click();
  await page.locator("#role-name").fill(roleName);
  await page.locator("#role-description").fill("Created by the admin button workflow.");
  await page.locator("#role-permissions input").first().check();
  await page.locator("#save-role-button").click();

  const roleRow = page.locator("#role-list .role-row").filter({ hasText: roleName });
  await expect(roleRow).toBeVisible();
  await roleRow.getByRole("button", { name: "Edit" }).click();
  await page.locator("#role-description").fill("Updated by the admin button workflow.");
  await page.locator("#save-role-button").click();
  await expect(roleRow).toContainText("Updated by the admin button workflow");
});

test("admin conversation buttons: takeover, staff response, and close", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The mutation workflow only needs one browser profile.");
  const property = (await (await page.request.get("/api/admin/properties")).json()).properties[0];
  property.contact_details = { ...(property.contact_details || {}), breakfast: "Breakfast is served from 7:00 to 10:00." };
  property.app_settings = {
    ...(property.app_settings || {}),
    guest_experience: {
      ...(property.app_settings?.guest_experience || {}),
      intelligent_ui: { enabled: true },
    },
  };
  const saved = await page.request.put(`/api/admin/properties/${property.property_id}`, {
    headers: { "X-CSRF-Token": csrfByRequest.get(page.request) }, data: property,
  });
  expect(saved.ok()).toBeTruthy();
  const sessionResponse = await page.request.post("/api/session/start", {
    data: { client_id: `conversation-audit-${Date.now()}`, property_id: property.property_id },
  });
  expect(sessionResponse.ok()).toBeTruthy();
  const sessionId = (await sessionResponse.json()).session_id;
  const chatResponse = await page.request.post("/api/guest/intelligent-chat", {
    data: { session_id: sessionId, turn_id: `conversation-turn-${Date.now()}`, message: "What time is breakfast?" },
  });
  expect(chatResponse.ok(), await chatResponse.text()).toBeTruthy();

  await page.goto("/admin");
  await openPanel(page, "Conversations");
  await page.locator(".conversation-retention > summary").click();
  await page.locator("#conversation-retention-days").fill("21");
  await page.getByRole("button", { name: "Save retention" }).click();
  await expect(page.locator("#conversation-retention-days")).toHaveValue("21");
  await page.getByRole("button", { name: "Refresh inbox" }).click();
  await expect(page.locator("#conversation-last-refreshed")).toContainText("Updated");
  await page.locator('[data-conversation-filter="ai_active"]').click();
  const conversation = page.locator("#conversation-list button").first();
  await conversation.click();
  await page.getByRole("button", { name: "Take over" }).click();
  await expect(page.getByRole("button", { name: "Return to AI" })).toBeVisible();
  await page.locator("#staff-response").fill("This is a verified staff response.");
  await page.getByRole("button", { name: "Send reply" }).click();
  await expect(page.locator("#conversation-messages")).toContainText("verified staff response");
  await page.getByRole("button", { name: "Resolve", exact: true }).click();
  await expect(page.locator("#conversation-detail-status")).toHaveText("Resolved");
  await page.locator("#conversation-search").fill("");
  await page.locator("#conversation-status-filter").selectOption("");
});

test("unified conversations workspace adapts from desktop to tablet and mobile", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The responsive visual check uses one browser profile.");
  const property = (await (await page.request.get("/api/admin/properties")).json()).properties[0];
  property.app_settings = {
    ...(property.app_settings || {}),
    guest_experience: {
      ...(property.app_settings?.guest_experience || {}),
      intelligent_ui: { enabled: true },
    },
  };
  const saved = await page.request.put(`/api/admin/properties/${property.property_id}`, {
    headers: { "X-CSRF-Token": csrfByRequest.get(page.request) }, data: property,
  });
  expect(saved.ok()).toBeTruthy();
  const sessionResponse = await page.request.post("/api/session/start", {
    data: { client_id: `conversation-responsive-${Date.now()}`, property_id: property.property_id },
  });
  expect(sessionResponse.ok()).toBeTruthy();
  const sessionId = (await sessionResponse.json()).session_id;
  const chatResponse = await page.request.post("/api/guest/intelligent-chat", {
    data: { session_id: sessionId, turn_id: `conversation-responsive-turn-${Date.now()}`, message: "Could you recommend a quiet breakfast spot?" },
  });
  expect(chatResponse.ok(), await chatResponse.text()).toBeTruthy();

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/admin");
  await openPanel(page, "Conversations");
  await expect(page.locator("#conversation-list")).toBeVisible();
  await expect(page.locator("#conversation-messages .conversation-message").first()).toBeVisible();
  await expect(page.locator("#conversation-context")).toBeVisible();
  await expect(page.locator("#refresh-conversations")).toBeEnabled();
  await page.screenshot({ path: "test-results/conversations-desktop.png", fullPage: true });

  await page.setViewportSize({ width: 768, height: 1024 });
  const tabletContext = page.locator("#conversation-show-context");
  await expect(tabletContext).toBeVisible();
  await tabletContext.click();
  await expect(page.locator("#conversation-context")).toHaveClass(/is-open/);
  await page.locator("#conversation-context").evaluate((element) => Promise.all(element.getAnimations().map((animation) => animation.finished)));
  const tabletBounds = await page.locator("#conversation-context").boundingBox();
  expect(tabletBounds.x + tabletBounds.width).toBeLessThanOrEqual(769);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(768);
  await page.screenshot({ path: "test-results/conversations-tablet-context.png", fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("#conversation-show-context")).toBeVisible();
  await page.locator("#conversation-context-close").click();
  await expect(page.locator("#conversation-context")).not.toHaveClass(/is-open/);
  await page.locator("#conversation-show-context").click();
  await expect(page.locator("#conversation-context")).toHaveClass(/is-open/);
  await page.locator("#conversation-context").evaluate((element) => Promise.all(element.getAnimations().map((animation) => animation.finished)));
  const mobileBounds = await page.locator("#conversation-context").boundingBox();
  expect(mobileBounds.x + mobileBounds.width).toBeLessThanOrEqual(391);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: "test-results/conversations-mobile-context.png", fullPage: true });
});

test("conversation inbox uses bounded server pages and keeps complete status counts", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The pagination control only needs one browser profile.");
  const records = Array.from({ length: 52 }, (_, index) => ({
    session_id: index < 50
      ? `first-page-${String(index).padStart(3, "0")}`
      : `next-page-${String(index).padStart(3, "0")}`,
    client_id: `pagination-guest-${index}`,
    created_at: 1_797_000_000 + index,
    last_message_at: null,
    message_count: 0,
    status: "open",
    state: "ai_active",
    human_takeover: false,
    restaurant_id: null,
    restaurant_name: index < 50 ? "Hotel team" : `Page two guest ${index}`,
    assigned_user_id: null,
    assigned_user_name: "",
    escalation_reason: "",
    messages: [],
  }));
  const offsets = [];
  await page.route("**/api/admin/properties/*/conversations?*", async (route) => {
    const url = new URL(route.request().url());
    const limit = Number(url.searchParams.get("limit"));
    const offset = Number(url.searchParams.get("offset"));
    offsets.push({ limit, offset });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        conversations: records.slice(offset, offset + limit),
        total: records.length,
        limit,
        offset,
        status_counts: { waiting_for_staff: 0, assigned: 0, human_active: 0, ai_active: 52, resolved: 0 },
        retention: { retention_days: 30 },
      }),
    });
  });

  await page.goto("/admin");
  await openPanel(page, "Conversations");
  await expect(page.locator("#conversation-page-info")).toHaveText("Page 1 of 2");
  await expect(page.locator("#conversation-count-all")).toHaveText("52");
  await expect(page.locator("#conversation-result-count")).toHaveText("1–50 of 52 conversations");
  await expect(page.locator("#conversation-list button")).toHaveCount(50);
  await expect(page.locator("#conversation-page-previous")).toBeDisabled();
  await page.locator("#conversation-page-next").click();
  await expect(page.locator("#conversation-page-info")).toHaveText("Page 2 of 2");
  await expect(page.locator("#conversation-result-count")).toHaveText("51–52 of 52 conversations");
  await expect(page.locator("#conversation-list button")).toHaveCount(2);
  await expect(page.locator("#conversation-list")).toContainText("Page two guest 51");
  await expect(page.locator("#conversation-page-previous")).toBeEnabled();
  await expect(page.locator("#conversation-page-next")).toBeDisabled();
  expect(offsets).toContainEqual({ limit: 50, offset: 0 });
  expect(offsets).toContainEqual({ limit: 50, offset: 50 });
});

test("admin conversation queue can assign an escalated conversation to staff", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The mutation workflow only needs one browser profile.");
  const suffix = Date.now().toString(36);
  const propertyId = (await (await page.request.get("/api/admin/properties")).json()).properties[0].property_id;
  const headers = { "X-CSRF-Token": csrfByRequest.get(page.request) };
  const restaurantResponse = await page.request.post(`/api/admin/properties/${propertyId}/restaurants`, {
    headers,
    data: { data: { name: `Queue Assignment ${suffix}` } },
  });
  expect(restaurantResponse.ok()).toBeTruthy();
  const restaurant = await restaurantResponse.json();
  const staffName = `Queue Staff ${suffix}`;
  const staffResponse = await page.request.post("/api/admin/users", {
    headers,
    data: {
      username: `queue.staff.${suffix}`,
      display_name: staffName,
      password: "QueueStaffPassword123!",
      property_id: propertyId,
      role_id: "role-restaurant-staff",
      status: "active",
      force_password_change: false,
      restaurant_ids: [restaurant.restaurant_id],
    },
  });
  expect(staffResponse.ok()).toBeTruthy();
  const staff = (await staffResponse.json()).user;
  const sessionResponse = await page.request.post("/api/session/start", {
    data: { client_id: `queue-assignment-${suffix}`, property_id: propertyId },
  });
  expect(sessionResponse.ok()).toBeTruthy();
  const sessionId = (await sessionResponse.json()).session_id;
  const escalationResponse = await page.request.post(`/api/guest/conversations/${sessionId}/escalate`, {
    data: { restaurant_id: restaurant.restaurant_id, reason: "Please connect me to restaurant staff." },
  });
  expect(escalationResponse.ok()).toBeTruthy();

  await page.goto("/admin");
  await openPanel(page, "Conversations");
  const row = page.locator("#conversation-list button").first();
  await row.click();
  const staffSelect = page.locator("#conversation-staff-select");
  await expect(staffSelect).toBeEnabled();
  await staffSelect.selectOption({ value: staff.id });
  await expect(staffSelect).toHaveValue(staff.id);
  await expect(page.locator("#assign-conversation")).toBeEnabled();
  await page.getByRole("button", { name: "Assign", exact: true }).click();
  await expect(page.locator("#conversation-detail-status")).toHaveText("Assigned");
  await expect(row).toContainText(staffName);
});

test("admin AI settings and usage reporting work", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The mutation workflow only needs one browser profile.");
  const suffix = Date.now().toString(36);

  await page.goto("/admin");
  await openPanel(page, "Models & Providers");
  await page.getByRole("button", { name: "Save AI Settings" }).click();
  await expect(page.locator("#toast")).toContainText("AI settings saved");
  await page.locator("article.provider-row [data-action='configure']").first().click();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.locator("#toast")).toContainText("Google Gemini saved");
  await page.locator("#drawer-secret").fill("");
  await page.getByRole("button", { name: "Add / Replace" }).click();
  await expect(page.locator("#toast")).toContainText("Paste a credential first");
  await page.locator("#drawer-secret").fill(`test-credential-${suffix}`);
  await page.getByRole("button", { name: "Add / Replace" }).click();
  await expect(page.locator("#toast")).toContainText("Credential saved");
  await page.getByRole("button", { name: "Remove", exact: true }).click();
  await expect(page.locator("#toast")).toContainText("Credential removed");
  await page.getByRole("button", { name: "Close", exact: true }).click();

  await openPanel(page, "Usage");
  await expect(page.locator("#ai-usage-metrics")).toContainText("Requests");
  await expect(page.locator("#ai-usage-list")).toBeVisible();
});
