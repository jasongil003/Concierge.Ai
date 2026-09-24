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
  await expect(page.locator("#reset-form")).toBeHidden();
});

test("password reset link shows only the reset form", async ({ page }) => {
  await page.goto("/admin/login?reset_token=test-token");

  await expect(page.locator("#login-form")).toBeHidden();
  await expect(page.locator("#reset-form")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
  await expect(page.locator("#reset-password")).toBeVisible();
  await expect(page.getByRole("button", { name: "Update Password" })).toBeVisible();
});

test("invalid username and password remain on login", async ({ page }) => {
  await page.goto("/admin/login");
  await page.locator("#username").fill("unknown.user");
  await page.getByLabel("Password", { exact: true }).fill("IncorrectPass123!");
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page.getByRole("alert")).toContainText("Invalid username or password");
  await expect(page).toHaveURL(/\/admin\/login$/);
});

test("password visibility button toggles the password field", async ({ page }) => {
  await page.goto("/admin/login");
  const password = page.getByLabel("Password", { exact: true });
  const toggle = page.getByRole("button", { name: "Show password" });

  await expect(password).toHaveAttribute("type", "password");
  await toggle.click();
  await expect(password).toHaveAttribute("type", "text");
  await expect(page.getByRole("button", { name: "Hide password" })).toBeVisible();
  await page.getByRole("button", { name: "Hide password" }).click();
  await expect(password).toHaveAttribute("type", "password");
});

test("password recovery buttons open, submit, and close the dialog", async ({ page }) => {
  await page.goto("/admin/login");
  await page.locator("#username").fill("admin");
  await page.getByRole("button", { name: "Forgot password?" }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(page.locator("#recovery-username")).toHaveValue("admin");
  await page.getByRole("button", { name: "Request reset" }).click();
  await expect(page.locator("#recovery-message")).toContainText("reset instructions will be sent");
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).not.toBeVisible();
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
