import { expect, test } from "@playwright/test";

test("unauthenticated admin access redirects to username login", async ({ page }) => {
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/admin\/login$/);
  await expect(page.getByText("Concierge.AI")).toBeVisible();
  await expect(page.getByText("Admin Portal")).toBeVisible();
  await expect(page.locator("#username")).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign In" })).toBeVisible();
  await expect(page.getByText("Remember me")).toBeVisible();
  await expect(page.getByRole("button", { name: "Forgot password?" })).toBeVisible();
});

test("invalid username and password remain on login", async ({ page }) => {
  await page.goto("/admin/login");
  await page.locator("#username").fill("unknown.user");
  await page.getByLabel("Password", { exact: true }).fill("IncorrectPass123!");
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page.getByRole("alert")).toContainText("Invalid username or password");
  await expect(page).toHaveURL(/\/admin\/login$/);
});

test("username login opens admin and logout revokes the session", async ({ page }) => {
  await page.goto("/admin/login");
  await page.locator("#username").fill("admin");
  await page.getByLabel("Password", { exact: true }).fill("ChangeMe123!");
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.locator("#overview-title")).toBeVisible();
  await page.locator("#profile-button").click();
  await page.getByRole("button", { name: "Logout" }).click();
  await expect(page).toHaveURL(/\/admin\/login$/);
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/admin\/login$/);
});
