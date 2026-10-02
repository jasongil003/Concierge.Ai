import { expect, test } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";

const CONTROL_SELECTOR = [
  "button", "a[href]", "input", "textarea", "select", "summary", "[contenteditable='true']",
  "[role='button']", "[role='tab']", "[role='switch']", "[role='checkbox']", "[role='radio']",
  "[role='combobox']", "[role='option']", "[role='menuitem']", "[role='menuitemcheckbox']",
  "[role='menuitemradio']", "[tabindex]:not([tabindex='-1'])",
].join(",");

function collectControlInventory(elements, currentView) {
  const ariaDisabledAncestor = (element) => {
    for (let ancestor = element; ancestor && ancestor !== document.documentElement; ancestor = ancestor.parentElement) {
      if (ancestor.getAttribute("aria-disabled")?.toLowerCase() === "true") return ancestor;
    }
    return null;
  };
  const isDisabled = (element) => Boolean(element?.matches?.(":disabled") || ariaDisabledAncestor(element));
  const isVisible = (element) => {
    for (let ancestor = element; ancestor && ancestor !== document.documentElement; ancestor = ancestor.parentElement) {
      const style = window.getComputedStyle(ancestor);
      if (
        ancestor.hidden
        || ancestor.inert
        || ancestor.getAttribute("aria-hidden") === "true"
        || ancestor.classList?.contains("sr-only")
        || style.display === "none"
        || style.visibility === "hidden"
        || Number(style.opacity) === 0
      ) return false;
    }
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity) !== 0 && rect.width > 0 && rect.height > 0;
  };
  const canReceiveTabFocus = (element) => {
    if (!element || !isVisible(element) || isDisabled(element) || element.tabIndex < 0) return false;
    const wasFocused = document.activeElement === element;
    try {
      element.focus({ preventScroll: true });
    } catch {
      return false;
    }
    return document.activeElement === element || wasFocused;
  };
  const getLabel = (element) => {
    const associatedLabel = Array.from(element.labels || [])
      .map((labelElement) => labelElement.innerText || labelElement.textContent || "")
      .join(" ");
    const labelledBy = (element.getAttribute("aria-labelledby") || "")
      .split(/\s+/)
      .map((id) => document.getElementById(id)?.innerText || "")
      .join(" ");
    return (
      element.getAttribute("aria-label")
      || labelledBy
      || associatedLabel
      || element.getAttribute("title")
      || element.innerText
      || (["button", "submit", "reset", "image"].includes((element.getAttribute("type") || "").toLowerCase()) ? element.value : "")
      || element.getAttribute("alt")
      || element.querySelector("img[alt]")?.getAttribute("alt")
      || ""
    ).replace(/\s+/g, " ").trim().slice(0, 180);
  };
  const disabledSource = (element, disabled) => {
    if (!disabled) return null;
    if (element.matches(":disabled")) {
      const fieldset = element.closest("fieldset[disabled]");
      if (fieldset) {
        return {
          tag: "fieldset",
          id: fieldset.id || "",
          role: fieldset.getAttribute("role") || "",
          html: fieldset.outerHTML.slice(0, 400),
        };
      }
      return { tag: element.tagName.toLowerCase(), id: element.id || "", reason: "native-disabled" };
    }
    const ancestor = ariaDisabledAncestor(element);
    if (ancestor) {
      return {
        tag: ancestor.tagName.toLowerCase(),
        id: ancestor.id || "",
        role: ancestor.getAttribute("role") || "",
        reason: "aria-disabled",
      };
    }
    return null;
  };

  const visibleElements = elements.filter(isVisible);
  const pendingRows = [];
  const counts = new Map();
  for (const element of visibleElements) {
    const tag = element.tagName.toLowerCase();
    const type = tag === "input" ? (element.getAttribute("type") || "text").toLowerCase() : "";
    const role = element.getAttribute("role") || "";
    const label = getLabel(element);
    const panel = element.closest(".panel.active")?.id || "";
    const scope = panel || (element.closest(".platform-shell") ? "admin-shell" : "guest-interface");
    const base = [scope, tag, type, role, element.id || "", element.getAttribute("name") || "", label].join("|");
    const occurrence = counts.get(base) || 0;
    counts.set(base, occurrence + 1);
    const disabled = isDisabled(element);
    const tabIndex = element.tabIndex;
    const focusable = !disabled && canReceiveTabFocus(element);
    const row = {
      view: currentView,
      panel,
      scope,
      tag,
      type,
      role,
      id: element.id || "",
      name: element.getAttribute("name") || "",
      label,
      occurrence,
      tabIndex,
      disabled,
      disabledBy: disabledSource(element, disabled),
      readOnly: Boolean(element.readOnly),
      required: Boolean(element.required || element.getAttribute("aria-required") === "true"),
      checked: "checked" in element ? Boolean(element.checked) : null,
      focusable,
      directlyFocusable: focusable,
      compositeRole: "",
      compositeId: "",
      managedFocus: false,
      managedFocusReason: "",
      focusabilityReason: disabled
        ? "disabled"
        : focusable
          ? "keyboard-tab-stop"
          : tabIndex < 0
            ? "tabindex-minus-one"
            : "focus() did not move document focus",
      behaviorStatus: "NOT_TESTED_BY_INVENTORY",
    };
    if (disabled || !focusable || !label) row.html = element.outerHTML.slice(0, 600);
    pendingRows.push({ element, row, group: null });
  }

  const elementIdentity = new WeakMap();
  let nextIdentity = 0;
  const identityOf = (element) => {
    if (!elementIdentity.has(element)) elementIdentity.set(element, ++nextIdentity);
    return elementIdentity.get(element);
  };
  const ownedByRole = (element, role) => {
    const selector = "[role='" + role + "']";
    const ancestor = element.closest(selector);
    if (ancestor) return ancestor;
    if (!element.id) return null;
    return Array.from(document.querySelectorAll(selector + "[aria-owns]"))
      .find((candidate) => (candidate.getAttribute("aria-owns") || "").split(/\s+/).includes(element.id)) || null;
  };
  const descriptorFor = (element) => {
    const role = element.getAttribute("role") || "";
    let owner = null;
    let compositeRole = "";
    let groupName = "";
    if (role === "tab") {
      owner = ownedByRole(element, "tablist");
      compositeRole = "tablist";
    } else if (role === "radio") {
      owner = ownedByRole(element, "radiogroup");
      compositeRole = owner ? "radiogroup" : "";
    } else if (role === "option") {
      owner = ownedByRole(element, "listbox");
      compositeRole = "listbox";
    } else if (["menuitem", "menuitemcheckbox", "menuitemradio"].includes(role)) {
      owner = ownedByRole(element, "menu") || ownedByRole(element, "menubar");
      compositeRole = owner?.getAttribute("role") || "";
    }
    if (!owner && element.tagName === "INPUT" && element.type === "radio" && element.name) {
      owner = element.form || document;
      compositeRole = "radio-group";
      groupName = element.name;
    }
    if (!owner || !compositeRole) return null;
    return {
      owner,
      compositeRole,
      key: compositeRole + ":" + identityOf(owner) + ":" + groupName,
    };
  };

  const groups = new Map();
  for (const pending of pendingRows) {
    const descriptor = descriptorFor(pending.element);
    if (!descriptor) continue;
    pending.group = descriptor;
    if (!groups.has(descriptor.key)) {
      groups.set(descriptor.key, { ...descriptor, members: [] });
    }
    groups.get(descriptor.key).members.push(pending);
  }

  const describeEntryPoint = (element) => ({
    tag: element.tagName.toLowerCase(),
    role: element.getAttribute("role") || "",
    id: element.id || "",
    label: getLabel(element),
  });
  const isGroupItemSelected = (pending, attribute) => pending.element.getAttribute(attribute)?.toLowerCase() === "true";
  const controlsOwner = (owner) => {
    if (!owner?.id) return [];
    const candidates = Array.from(document.querySelectorAll("[aria-controls], [aria-owns]"));
    return candidates.filter((candidate) => {
      const references = [
        ...(candidate.getAttribute("aria-controls") || "").split(/\s+/),
        ...(candidate.getAttribute("aria-owns") || "").split(/\s+/),
      ].filter(Boolean);
      return references.includes(owner.id) && canReceiveTabFocus(candidate);
    });
  };
  const evaluateGroup = (group) => {
    const enabled = group.members.filter(({ row }) => !row.disabled);
    const tabStops = enabled.filter(({ row }) => row.tabIndex >= 0 && row.focusable);
    let valid = false;
    let target = null;
    let entryPointModel = "";
    let reason = "";
    const owner = group.owner;
    if (enabled.length === 0) {
      return {
        view: currentView,
        compositeRole: group.compositeRole,
        id: owner.id || "",
        label: getLabel(owner),
        enabledItems: 0,
        entryPointModel: "no enabled items; all composite controls are disabled",
        entryPoint: null,
        valid: true,
        reason: "",
        memberIds: group.members.map(({ row }) => row.id).filter(Boolean),
      };
    }

    if (group.compositeRole === "tablist") {
      const selected = enabled.filter((pending) => isGroupItemSelected(pending, "aria-selected"));
      target = tabStops[0] || null;
      valid = tabStops.length === 1 && (selected.length === 0 || (selected.length === 1 && selected[0] === target));
      entryPointModel = "one enabled tab with tabindex=0";
      reason = valid
        ? ""
        : selected.length === 1 && selected[0] !== target
          ? "the selected tab is not the tablist's tabindex=0 entry point"
          : "tablist needs exactly one enabled tab with tabindex=0";
    } else if (group.compositeRole === "radiogroup") {
      const selected = enabled.filter((pending) => isGroupItemSelected(pending, "aria-checked"));
      target = tabStops[0] || null;
      valid = tabStops.length === 1 && (selected.length === 0 || (selected.length === 1 && selected[0] === target));
      entryPointModel = "one enabled radio with tabindex=0";
      reason = valid
        ? ""
        : selected.length === 1 && selected[0] !== target
          ? "the checked radio is not the radiogroup's tabindex=0 entry point"
          : "radiogroup needs exactly one enabled radio with tabindex=0";
    } else if (group.compositeRole === "radio-group") {
      const checked = enabled.filter(({ element }) => Boolean(element.checked));
      target = checked[0] || enabled[0] || null;
      valid = Boolean(target && target.row.tabIndex >= 0 && target.row.focusable);
      entryPointModel = "the checked native radio, or the first enabled radio, enters the group";
      reason = valid ? "" : "native radio group has no enabled keyboard entry point";
      if (valid) {
        for (const pending of enabled) {
          if (pending !== target) {
            pending.row.focusable = false;
            pending.row.managedFocus = true;
            pending.row.managedFocusReason = "native radio group arrow-key navigation";
            pending.row.focusabilityReason = "managed native radio group";
          }
        }
      }
    } else if (group.compositeRole === "listbox") {
      const relatedCombobox = controlsOwner(owner).find((candidate) => candidate.getAttribute("role") === "combobox");
      const focusEntry = canReceiveTabFocus(owner) ? owner : relatedCombobox || null;
      const activeId = focusEntry?.getAttribute("aria-activedescendant") || owner.getAttribute("aria-activedescendant") || "";
      const activeOption = activeId ? enabled.find(({ row }) => row.id === activeId) : null;
      const optionStops = enabled.filter(({ row }) => row.tabIndex >= 0 && row.focusable);
      if (focusEntry && optionStops.length === 0 && (!activeId || activeOption)) {
        valid = true;
        target = { element: focusEntry };
        entryPointModel = "focusable listbox or controlling combobox, with aria-activedescendant when present";
      } else if (!focusEntry && optionStops.length === 1) {
        valid = true;
        target = optionStops[0];
        entryPointModel = "one enabled option with tabindex=0";
      } else {
        reason = "listbox needs a focusable owner or controlling combobox, or one enabled option with tabindex=0";
        entryPointModel = "focusable listbox/combobox owner or roving option";
      }
    } else {
      const ownerFocusable = canReceiveTabFocus(owner);
      const activeId = owner.getAttribute("aria-activedescendant") || "";
      const activeItem = activeId ? enabled.find(({ row }) => row.id === activeId) : null;
      const itemStops = enabled.filter(({ row }) => row.tabIndex >= 0 && row.focusable);
      const relatedTriggers = controlsOwner(owner).filter((candidate) =>
        ["menu", "true"].includes(candidate.getAttribute("aria-haspopup")?.toLowerCase() || ""),
      );
      const visibleMenus = Array.from(document.querySelectorAll("[role='menu']")).filter(isVisible);
      const expandedMenuTriggers = Array.from(document.querySelectorAll("[aria-haspopup]"))
        .filter((candidate) => ["menu", "true"].includes(candidate.getAttribute("aria-haspopup")?.toLowerCase() || ""))
        .filter((candidate) => candidate.getAttribute("aria-expanded") === "true" && canReceiveTabFocus(candidate));
      const implicitTrigger = visibleMenus.length === 1 && expandedMenuTriggers.length === 1
        ? expandedMenuTriggers[0]
        : null;
      if (ownerFocusable && itemStops.length <= 1 && (!activeId || activeItem || itemStops.length === 1)) {
        valid = true;
        target = { element: owner };
        entryPointModel = "focusable menu owner with active descendant or roving menu item";
      } else if (!ownerFocusable && itemStops.length === 1) {
        valid = true;
        target = itemStops[0];
        entryPointModel = "one enabled menu item with tabindex=0";
      } else if (relatedTriggers.length > 0 || implicitTrigger) {
        valid = itemStops.length <= 1;
        target = { element: relatedTriggers[0] || implicitTrigger };
        entryPointModel = "keyboard-focusable menu trigger controls the menu";
        if (!valid) reason = "menu has more than one tabindex=0 item";
      } else {
        entryPointModel = "focusable menu owner, one roving menu item, or related keyboard-focusable trigger";
        reason = "menu has no keyboard entry point";
      }
    }

    const describedEntry = target
      ? describeEntryPoint(target.element)
      : null;
    return {
      view: currentView,
      compositeRole: group.compositeRole,
      id: owner.id || "",
      label: getLabel(owner),
      enabledItems: enabled.length,
      entryPointModel,
      entryPoint: describedEntry,
      valid,
      reason,
      memberIds: group.members.map(({ row }) => row.id).filter(Boolean),
    };
  };

  const compositeWidgets = [];
  for (const group of groups.values()) {
    const state = evaluateGroup(group);
    compositeWidgets.push(state);
    for (const pending of group.members) {
      const { row } = pending;
      row.compositeRole = group.compositeRole;
      row.compositeId = group.owner.id || "";
      row.compositeValid = state.valid;
      row.compositeEntryPoint = state.entryPoint;
      if (!row.disabled && !row.focusable && state.valid) {
        row.managedFocus = true;
        row.managedFocusReason = state.entryPointModel;
        row.focusabilityReason = "managed composite focus";
      } else if (!row.disabled && !row.focusable && !state.valid && !row.managedFocus) {
        row.focusabilityReason = state.reason || "composite widget has no keyboard entry point";
      }
    }
  }

  return {
    controls: pendingRows.map(({ row }) => row),
    compositeWidgets,
  };
}

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
  const item = page.locator(".nav-item[data-panel=" + JSON.stringify(panel) + "]").first();
  const networkAccessLoaded = panel === "network-access"
    ? page.waitForResponse((response) => response.url().includes("/network-access/status") && response.ok())
    : null;
  await item.evaluate((element) => {
    const group = element.closest("details.nav-group");
    if (group) group.open = true;
  });
  await item.scrollIntoViewIfNeeded();
  await item.click();
  await expect(page.locator(".panel.active")).toHaveAttribute("id", panel);
  if (networkAccessLoaded) {
    await networkAccessLoaded;
    await expect(page.locator("#guest-access-fields")).not.toHaveAttribute("aria-busy", "true");
  }
}

async function inventoryVisibleControls(page, view) {
  return page.locator(CONTROL_SELECTOR).evaluateAll(collectControlInventory, view);
}

function summarizeInventory(records, compositeWidgets) {
  return {
    visibleControlInstances: records.length,
    focusableControls: records.filter((item) => item.focusable).length,
    enabledControlsNotFocusable: records.filter((item) => !item.focusable && !item.managedFocus && !item.disabled).length,
    controlsMissingAccessibleName: records.filter((item) => !item.label).length,
    invalidCompositeWidgets: compositeWidgets.filter((item) => !item.valid),
  };
}

test("manual QA inventories visible controls on every admin destination and guest view", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "The control inventory runs once in Chromium.");
  test.setTimeout(180_000);
  await signIn(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/admin");
  await page.locator('body[data-admin-ready="true"]').waitFor();

  const records = [];
  const compositeWidgets = [];
  const panels = await page.locator(".nav-item[data-panel]").evaluateAll((items) => [...new Set(items.map((item) => item.dataset.panel))]);
  for (const panel of panels) {
    await openPanel(page, panel);
    const inventory = await inventoryVisibleControls(page, "admin:" + panel);
    records.push(...inventory.controls);
    compositeWidgets.push(...inventory.compositeWidgets);
  }

  await page.goto("/");
  await expect(page.locator("#home-view")).toBeVisible();
  let inventory = await inventoryVisibleControls(page, "guest:home");
  records.push(...inventory.controls);
  compositeWidgets.push(...inventory.compositeWidgets);
  const guestNavigation = page.locator(".experience-configured-navigation");
  await expect(guestNavigation).toBeVisible();
  for (const [label, panel] of [["Explore", "#explore-view"], ["Requests", "#requests-view"], ["My Stay", "#stay-view"], ["Concierge", "#concierge-view"], ["Home", "#home-view"]]) {
    await guestNavigation.getByRole("button", { name: label, exact: true }).click();
    await expect(page.locator(panel)).toBeVisible();
    inventory = await inventoryVisibleControls(page, "guest:" + label.toLowerCase().replaceAll(" ", "-"));
    records.push(...inventory.controls);
    compositeWidgets.push(...inventory.compositeWidgets);
  }

  const summary = {
    generatedAt: new Date().toISOString(),
    viewport: { width: 1440, height: 900 },
    adminDestinations: panels.length,
    guestViews: 5,
    ...summarizeInventory(records, compositeWidgets),
    behaviorStatus: "INVENTORY_WITH_KEYBOARD_ENTRY_VALIDATION; interactive behavior is covered by named Playwright workflows, not generically clicked.",
    controls: records,
    compositeWidgets,
  };
  const outputPath = resolve(process.cwd(), "audit", "CONTROL_INVENTORY_2026-09-29.json");
  writeFileSync(outputPath, JSON.stringify(summary) + "\n", "utf8");
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
    invalidCompositeWidgets: summary.invalidCompositeWidgets,
    nonFocusableControls: records.filter((item) => !item.focusable && !item.managedFocus && !item.disabled),
    controlsMissingNames: records.filter((item) => !item.label),
    behaviorStatus: summary.behaviorStatus,
  }));
  expect(summary.adminDestinations).toBeGreaterThan(0);
  expect(summary.visibleControlInstances).toBeGreaterThan(0);
  expect(summary.enabledControlsNotFocusable).toBe(0);
  expect(summary.invalidCompositeWidgets).toHaveLength(0);
  expect(summary.controlsMissingAccessibleName).toBe(0);
});

test("control inventory validates normal focus, disabled controls, names, and composite entry points", async ({ page }) => {
  await page.setContent([
    "<form>",
    '<button id="normal-button" type="button">Save</button>',
    '<label>Guest name<input id="normal-input" type="text"></label>',
    '<div id="valid-tabs" role="tablist" aria-label="Settings tabs">',
    '<button id="selected-tab" role="tab" aria-selected="true" tabindex="0">Profile</button>',
    '<button id="other-tab" role="tab" aria-selected="false" tabindex="-1">Security</button>',
    "</div>",
    '<div id="invalid-tabs" role="tablist" aria-label="Invalid tabs">',
    '<button id="invalid-selected-tab" role="tab" aria-selected="true" tabindex="-1">Overview</button>',
    '<button id="invalid-other-tab" role="tab" aria-selected="false" tabindex="-1">Advanced</button>',
    "</div>",
    '<div id="valid-radios" role="radiogroup" aria-label="Stay dates">',
    '<div id="selected-radio" role="radio" aria-checked="true" tabindex="0">Flexible dates</div>',
    '<div id="other-radio" role="radio" aria-checked="false" tabindex="-1">Exact dates</div>',
    "</div>",
    '<div id="valid-listbox" role="listbox" aria-label="Property options" tabindex="0" aria-activedescendant="active-option">',
    '<div id="active-option" role="option" aria-selected="true">Central</div>',
    '<div id="other-option" role="option">Coastal</div>',
    "</div>",
    '<button id="menu-trigger" type="button" aria-haspopup="menu" aria-controls="actions-menu" aria-expanded="true">Actions</button>',
    '<div id="actions-menu" role="menu" aria-label="Actions">',
    '<div id="menu-save" role="menuitem" tabindex="-1">Save</div>',
    '<div id="menu-cancel" role="menuitem" tabindex="-1">Cancel</div>',
    "</div>",
    '<div id="disabled-tabs" role="tablist"><button id="disabled-tab" role="tab" aria-disabled="true" tabindex="-1">Unavailable</button></div>',
    '<div id="aria-disabled-group" aria-disabled="true"><button id="aria-disabled-control" type="button">Unavailable action</button></div>',
    '<fieldset id="disabled-group" disabled><button id="inherited-disabled" type="button">Disabled action</button></fieldset>',
    '<button id="unnamed-control" type="button"></button>',
    "</form>",
  ].join(""));
  const inventory = await page.locator(CONTROL_SELECTOR).evaluateAll(collectControlInventory, "fixture");
  const summary = summarizeInventory(inventory.controls, inventory.compositeWidgets);
  const controlsById = new Map(inventory.controls.map((item) => [item.id, item]));
  const validTabs = inventory.compositeWidgets.find((item) => item.id === "valid-tabs");
  const invalidTabs = inventory.compositeWidgets.find((item) => item.id === "invalid-tabs");
  const validRadios = inventory.compositeWidgets.find((item) => item.id === "valid-radios");
  const validListbox = inventory.compositeWidgets.find((item) => item.id === "valid-listbox");
  const validMenu = inventory.compositeWidgets.find((item) => item.id === "actions-menu");
  const disabledTabs = inventory.compositeWidgets.find((item) => item.id === "disabled-tabs");

  expect(controlsById.get("normal-button").focusable).toBe(true);
  expect(controlsById.get("normal-input").focusable).toBe(true);
  expect(controlsById.get("other-tab").managedFocus).toBe(true);
  expect(controlsById.get("other-tab").compositeRole).toBe("tablist");
  expect(validTabs.valid).toBe(true);
  expect(invalidTabs.valid).toBe(false);
  expect(validRadios.valid).toBe(true);
  expect(controlsById.get("other-radio").managedFocus).toBe(true);
  expect(validListbox.valid).toBe(true);
  expect(controlsById.get("other-option").managedFocus).toBe(true);
  expect(validMenu.valid).toBe(true);
  expect(controlsById.get("menu-save").managedFocus).toBe(true);
  expect(summary.invalidCompositeWidgets).toHaveLength(1);
  expect(summary.enabledControlsNotFocusable).toBe(2);
  expect(disabledTabs.valid).toBe(true);
  expect(controlsById.get("disabled-tab").disabled).toBe(true);
  expect(controlsById.get("aria-disabled-control").disabled).toBe(true);
  expect(controlsById.get("inherited-disabled").disabled).toBe(true);
  expect(summary.controlsMissingAccessibleName).toBe(1);
});
