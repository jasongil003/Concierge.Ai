import { expect, test } from "@playwright/test";

async function loginAdmin(api) {
  const response = await api.post("/api/admin/auth/login", {
    data: { username: "admin", password: "ChangeMe123!", remember_me: false },
  });
  expect(response.ok()).toBeTruthy();
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
  await page.locator("#service-room").fill("1503");
  await page.locator("#service-type").selectOption({ label: serviceName });
  await page.locator("#service-description").fill("Button workflow verification");
  await page.getByRole("button", { name: "Create Request" }).click();
  const requestRow = page.locator("#service-request-list .compact-row").filter({ hasText: serviceName }).first();
  await expect(requestRow).toBeVisible();
  await requestRow.getByRole("button", { name: "Mark assigned" }).click();
  await expect(requestRow).toContainText("assigned");

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

test("admin restaurant workflow creates, approves, publishes, edits, and archives venue content", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The mutation workflow only needs one browser profile.");
  const suffix = Date.now().toString(36);
  const restaurantName = `Button Restaurant ${suffix}`;
  const menuName = `Button Menu ${suffix}`;
  const itemName = `Button Item ${suffix}`;
  const promotionName = `Button Promotion ${suffix}`;

  await page.goto("/admin");
  await openPanel(page, "Restaurants");
  await page.locator("#restaurant-name").fill(restaurantName);
  await page.locator("#restaurant-hours-monday").fill("06:30-22:00");
  await page.locator("#restaurant-meals").fill("breakfast, dinner");
  await page.locator("#restaurant-internal-notes").fill("Staff-only workflow test note.");
  await page.getByRole("button", { name: "Save Restaurant" }).click();

  const restaurantRow = page.locator("#restaurant-list .compact-row").filter({ hasText: restaurantName });
  await expect(restaurantRow).toBeVisible();
  await restaurantRow.getByRole("button", { name: "Edit" }).click();
  await expect(page.locator("#restaurant-hours-monday")).toHaveValue("06:30-22:00");
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

  await restaurantRow.getByRole("button", { name: "Archive" }).click();
  await expect(restaurantRow).toContainText("archived");
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
  const suffix = Date.now().toString(36);
  const mac = "AA:BB:CC:DD:EE:42";
  const accessPoint = `ap-audit-${suffix}`;

  await page.goto("/admin");
  await openPanel(page, "Zones & Maps");
  await page.locator("#map-object-name").fill(`Audit Zone ${suffix}`);
  await page.getByRole("button", { name: "Save Object" }).click();
  await expect(page.locator("#toast")).toContainText("Map object saved");

  await page.locator("#map-object-type").selectOption("access_point");
  await page.locator("#map-object-name").fill(`Audit AP ${suffix}`);
  await page.locator("#map-ap-identifier").fill(accessPoint);
  await page.getByRole("button", { name: "Save Object" }).click();
  await expect(page.locator("#toast")).toContainText("Map object saved");

  await page.locator("#floor-map-upload").setInputFiles({
    name: `audit-${suffix}.svg`,
    mimeType: "image/svg+xml",
    buffer: Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'),
  });
  await expect(page.locator("#toast")).toContainText("Floor plan uploaded");

  await openPanel(page, "Guest Sessions");
  await page.locator("#session-raw-mac").fill(mac);
  await page.locator("#session-room").fill("1503");
  await page.getByRole("button", { name: "Create / Restore Stay" }).click();
  await expect(page.locator("#memory-stay-id")).not.toHaveValue("");
  await page.locator("#memory-summary").fill("Verified through the admin button workflow.");
  await page.getByRole("button", { name: "Save Compact Memory" }).click();
  await expect(page.locator("#toast")).toContainText("Compact stay memory saved");

  await openPanel(page, "Location");
  await page.locator("#obs-raw-mac").fill(mac);
  await page.locator("#obs-ap-id").fill(accessPoint);
  await page.getByRole("button", { name: "Record Observation" }).click();
  await expect(page.locator("#toast")).toContainText("Observation recorded");
  await page.getByRole("button", { name: "Load Report" }).click();
  await expect(page.locator("#location-report")).toContainText("visits");

  await openPanel(page, "Branding / Intro");
  const originalMessage = await page.locator("#intro-message").inputValue();
  await page.locator("#intro-message").fill(`Welcome ${suffix}`);
  await page.getByRole("button", { name: "Save Intro" }).click();
  await expect(page.locator("#toast")).toContainText("Intro experience saved");
  await page.locator("#intro-message").fill(originalMessage);
  await page.getByRole("button", { name: "Save Intro" }).click();
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
  await page.locator("#current-password").fill(password);
  await page.locator("#new-password").fill("AuditPassword456!");
  await page.locator("#confirm-new-password").fill("AuditPassword456!");
  await page.getByRole("button", { name: "Change Password" }).click();
  await expect(page.locator("#toast")).toContainText("Password changed");

  await page.locator("#profile-button").click();
  await page.getByRole("button", { name: "Logout" }).click();
  await page.locator("#username").fill("admin");
  await page.locator("#password").fill("ChangeMe123!");
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
  const sessionResponse = await page.request.post("/api/session/start", {
    data: { client_id: `conversation-audit-${Date.now()}` },
  });
  expect(sessionResponse.ok()).toBeTruthy();
  const sessionId = (await sessionResponse.json()).session_id;
  const chatResponse = await page.request.post("/api/chat", {
    data: { session_id: sessionId, message: "What time is breakfast?", mode: "auto" },
  });
  expect(chatResponse.ok()).toBeTruthy();

  await page.goto("/admin");
  await openPanel(page, "Conversations");
  const conversation = page.locator("#conversation-list button").filter({ hasText: sessionId.slice(0, 12) });
  await conversation.click();
  await page.getByRole("button", { name: "Take Over" }).click();
  await expect(page.getByRole("button", { name: "Return to AI" })).toBeVisible();
  await page.locator("#staff-response").fill("This is a verified staff response.");
  await page.getByRole("button", { name: "Send Response" }).click();
  await expect(page.locator("#conversation-messages")).toContainText("verified staff response");
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await expect(page.locator("#conversation-list")).toContainText("closed");
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
