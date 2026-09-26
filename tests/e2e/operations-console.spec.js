import { expect, test } from "@playwright/test";
import { ensureTestProperty } from "./support.js";


async function login(page) {
  const response = await page.request.post("/api/admin/auth/login", {
    data: { username: "admin", password: "ChangeMe123!", remember_me: false },
  });
  expect(response.ok()).toBeTruthy();
  const csrf = (await response.json()).user.csrf_token;
  await ensureTestProperty(page.request, csrf);
}


test.beforeEach(async ({ page }) => {
  await login(page);
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();
});


test("role-aware overview renders truthful telemetry and alerts", async ({ page }) => {
  await expect(page.locator("#operations-profile-label")).toContainText("Super Admin");
  await expect(page.locator("#operations-health-banner")).toBeVisible();
  await expect(page.locator("#operations-metrics .operations-metric")).toHaveCount(4);
  await expect(page.locator("#overview-charts .chart-card")).toHaveCount(6);
  await expect(page.locator("#overview")).toContainText(/no synthetic telemetry/i);
});


test("alert investigation uses the assistant drawer", async ({ page }) => {
  const investigate = page.locator("#overview-alerts .investigate-alert").first();
  if (await investigate.count()) {
    await page.route("**/assistant/query", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        question: "Investigate this alert",
        conversation_id: "test-conversation-0001",
        answer: "The provider error rate is elevated in the selected period. The evidence does not identify a confirmed root cause.",
        finding: "2 diagnostic checks completed.",
        component: "ai_providers",
        timeframe: "24h",
        evidence: [{ tool: "check_ai_provider", result: { state: "warning", evidence: "Provider connection test failed." } }],
        tool: "check_ai_provider",
        tool_activity: ["check_ai_provider"],
        recommendations: ["Review provider connection status."],
        links: [{ label: "Open AI settings", panel: "ai-models" }],
        confirmation_required: false,
        action_status: "No changes were made.",
        request_id: "request-test-0001",
      }),
    }));
    await investigate.click();
    await expect(page.locator("#assistant-drawer")).toBeVisible();
    await page.locator("#assistant-drawer-form button").click();
    await expect(page.locator("#assistant-drawer-messages .assistant-message.answer")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("#assistant-drawer-messages")).toContainText(/Evidence/);
    await expect(page.locator("#assistant-drawer-messages")).toContainText(/Diagnostic tool/);
  }
});


test("health, analytics, reports, and assistant pages are navigable", async ({ page }) => {
  for (const label of ["System Health", "AI Assistant", "Analytics", "Reports"]) {
    if ((page.viewportSize()?.width || 1200) <= 620) await page.locator("#sidebar-toggle").click();
    const button = page.locator(".nav-item").filter({ hasText: label }).first();
    await button.evaluate((element) => { const details = element.closest("details"); if (details) details.open = true; });
    await button.click();
  }
  await expect(page.locator("#reports")).toBeVisible();
  await expect(page.locator('[data-export="xlsx"]').first()).toBeVisible();
  await expect(page.locator('[data-export="pdf"]').first()).toBeVisible();
});
