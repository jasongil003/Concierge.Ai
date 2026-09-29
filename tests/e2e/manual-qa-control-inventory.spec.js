import { expect, test } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";

const CONTROL_SELECTOR = [
  "button", "a[href]", "input", "textarea", "select", "summary", "[contenteditable='true']",
  "[role='button']", "[role='tab']", "[role='switch']", "[role='checkbox']", "[role='radio']",
  "[role='combobox']", "[role='option']", "[role='menuitem']", "[tabindex]:not([tabindex='-1'])",
].join(",");

async function signIn(page) {
  const response = await page.request.post("/api/admin/auth/login", {
    data: { username: "admin", password: "PlaywrightOnly-Admin-123!", remember_me: false },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  const auth = (await response.json()).user;
  const properties = await page.request.get("/api/admin/properties");
  expect(properties.ok()).toBeTruthy();
  if (!(await properties.json()).properties.length) {
    const created = await page.request.put("/api/admin/properties/e2e-property", {
      headers: { "X-CSRF-Token": auth.csrf_token },
      data: { property_id: "e2e-property", hotel_name: "E2E Property", timezone: "Asia/Manila" },
    });
    expect(created.ok(), await created.text()).toBeTruthy();
  }
}

async function openPanel(page, panel) {
  const item = page.locator(`.nav-item[data-panel="${panel}"]`).first();
  await item.evaluate((element) => {
    const group = element.closest("details.nav-group");
    if (group) group.open = true;
  });
  await item.scrollIntoViewIfNeeded();
  await item.click();
  await expect(page.locator(".panel.active")).toHaveAttribute("id", panel);
}

async function inventoryVisibleControls(page, view) {
  return page.locator(CONTROL_SELECTOR).evaluateAll((elements, currentView) => {
    const counts = new Map();
    const rows = [];
    for (const element of elements) {
      let hiddenByAncestor = false;
      for (let ancestor = element; ancestor && ancestor !== document.documentElement; ancestor = ancestor.parentElement) {
        const ancestorStyle = window.getComputedStyle(ancestor);
        if (
          ancestor.hidden
          || ancestor.inert
          || ancestor.getAttribute("aria-hidden") === "true"
          || ancestor.classList?.contains("sr-only")
          || ancestorStyle.display === "none"
          || ancestorStyle.visibility === "hidden"
          || Number(ancestorStyle.opacity) === 0
        ) {
          hiddenByAncestor = true;
          break;
        }
      }
      if (hiddenByAncestor) continue;
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0 || rect.width === 0 || rect.height === 0) continue;
      const tag = element.tagName.toLowerCase();
      const type = tag === "input" ? (element.getAttribute("type") || "text").toLowerCase() : "";
      const associatedLabel = Array.from(element.labels || [])
        .map((labelElement) => labelElement.innerText || labelElement.textContent || "")
        .join(" ");
      const labelledBy = (element.getAttribute("aria-labelledby") || "")
        .split(/\s+/)
        .map((id) => document.getElementById(id)?.innerText || "")
        .join(" ");
      const label = (
        element.getAttribute("aria-label")
        || labelledBy
        || associatedLabel
        || element.getAttribute("title")
        || element.innerText
        || element.getAttribute("placeholder")
        || element.getAttribute("name")
        || element.id
        || ""
      ).replace(/\s+/g, " ").trim().slice(0, 180);
      const panel = element.closest(".panel.active")?.id;
      const scope = panel || (element.closest(".platform-shell") ? "admin-shell" : "guest-interface");
      const base = [scope, tag, type, element.getAttribute("role") || "", element.id || "", element.getAttribute("name") || "", label].join("|");
      const occurrence = counts.get(base) || 0;
      counts.set(base, occurrence + 1);
      const wasFocused = document.activeElement === element;
      if (!element.disabled && element.tabIndex >= 0) element.focus({ preventScroll: true });
      const focusable = document.activeElement === element || wasFocused;
      rows.push({
        view: currentView,
        scope,
        tag,
        type,
        role: element.getAttribute("role") || "",
        id: element.id || "",
        name: element.getAttribute("name") || "",
        label,
        occurrence,
        disabled: Boolean(element.disabled || element.getAttribute("aria-disabled") === "true"),
        readOnly: Boolean(element.readOnly),
        required: Boolean(element.required || element.getAttribute("aria-required") === "true"),
        checked: "checked" in element ? Boolean(element.checked) : null,
        focusable,
        behaviorStatus: "NOT_TESTED_BY_INVENTORY",
      });
    }
    return rows;
  }, view);
}

test("manual QA inventories visible controls on every admin destination and guest view", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The control inventory runs once in Chromium.");
  test.setTimeout(180_000);
  await signIn(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();

  const records = [];
  const panels = await page.locator(".nav-item[data-panel]").evaluateAll((items) => [...new Set(items.map((item) => item.dataset.panel))]);
  for (const panel of panels) {
    await openPanel(page, panel);
    records.push(...await inventoryVisibleControls(page, `admin:${panel}`));
  }

  await page.goto("/");
  await expect(page.locator("#home-view")).toBeVisible();
  records.push(...await inventoryVisibleControls(page, "guest:home"));
  for (const [label, panel] of [["Explore", "#explore-view"], ["Requests", "#requests-view"], ["My Stay", "#stay-view"], ["Concierge", "#concierge-view"], ["Home", "#home-view"]]) {
    await page.getByRole("button", { name: label, exact: true }).click();
    await expect(page.locator(panel)).toBeVisible();
    records.push(...await inventoryVisibleControls(page, `guest:${label.toLowerCase().replaceAll(" ", "-")}`));
  }

  const summary = {
    generatedAt: new Date().toISOString(),
    viewport: { width: 1440, height: 900 },
    adminDestinations: panels.length,
    guestViews: 5,
    visibleControlInstances: records.length,
    focusableControls: records.filter((item) => item.focusable).length,
    enabledControlsNotFocusable: records.filter((item) => !item.focusable && !item.disabled).length,
    controlsMissingAccessibleName: records.filter((item) => !item.label).length,
    behaviorStatus: "INVENTORY_WITH_FOCUS_CHECK; interactive behavior is covered by named Playwright workflows, not generically clicked.",
    controls: records,
  };
  const outputPath = resolve(process.cwd(), "audit", "CONTROL_INVENTORY_2026-09-29.json");
  writeFileSync(outputPath, `${JSON.stringify(summary)}\n`, "utf8");
  await testInfo.attach("visible-control-inventory.json", {
    body: Buffer.from(JSON.stringify(summary, null, 2)),
    contentType: "application/json",
  });
  console.log(JSON.stringify({
    controlInventoryPath: outputPath,
    adminDestinations: summary.adminDestinations,
    guestViews: summary.guestViews,
    visibleControlInstances: summary.visibleControlInstances,
    focusableControls: summary.focusableControls,
    enabledControlsNotFocusable: summary.enabledControlsNotFocusable,
    controlsMissingAccessibleName: summary.controlsMissingAccessibleName,
    controlsMissingAccessibleName: summary.controlsMissingAccessibleName,
    behaviorStatus: summary.behaviorStatus,
  }));
  expect(summary.adminDestinations).toBeGreaterThan(0);
  expect(summary.visibleControlInstances).toBeGreaterThan(0);
  expect(summary.enabledControlsNotFocusable).toBe(0);
  expect(summary.controlsMissingAccessibleName).toBe(0);
});
