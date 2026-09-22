const state = {
  auth: null,
  properties: [],
  users: [],
  roles: [],
  permissions: [],
  property: null,
  designDraft: null,
  designPublished: null,
  versions: [],
  ai: null,
  improvementLoop: null,
  activeProvider: null,
  providerDirty: false,
  zones: null,
  mapTool: "select",
  mapObjects: [],
  selectedMapObject: null,
  mapHistory: [],
  mapRedo: [],
  intro: null,
  catalog: { departments: [], services: [] },
  recommendations: [],
  conversations: [],
  selectedConversation: null,
  hospitality: null,
  mapBackgrounds: new Map(),
  freeformDraft: null,
  knowledge: { items: [], documents: [], faqs: [] },
  webhooks: { webhooks: [], deliveries: [] },
  deployment: null,
};

const $ = (id) => document.getElementById(id);

const authTypeDefinitions = [
  { id: "complimentary", label: "Complimentary", description: "Free internet codes or access plans issued by the hotel." },
  { id: "local", label: "Local", description: "Username and password managed locally on the gateway." },
  { id: "radius", label: "RADIUS", description: "External RADIUS username and password authentication." },
  { id: "pms", label: "PMS / Room Login", description: "Guest room, name, or reservation based authentication." },
  { id: "credit_card", label: "Credit Card", description: "Paid access through credit card charging." },
  { id: "access_code", label: "Access Code", description: "Guests enter a shared or assigned access code." },
  { id: "global_account", label: "Global Account", description: "Guests sign in with an existing global account." },
  { id: "global_code", label: "Global Code", description: "Global code based login for roaming or group access." },
  { id: "user_form", label: "User Form", description: "Guest registration form with configurable fields." },
  { id: "social_network", label: "Social Network", description: "Social login such as Facebook, Google, Line, or WeChat." },
];

const FEATURE_STATUS = {
  live: { label: "Live", className: "live" },
  partial: { label: "Partial", className: "partial" },
  coming_soon: { label: "Coming Soon", className: "soon" },
  configuration_required: { label: "Configuration Required", className: "required" },
};

const NAV_SECTIONS = [
  {
    title: "Core",
    items: [
      { id: "dashboard", label: "Dashboard", panel: "overview", permission: "dashboard.view", status: "live", icon: "⌂" },
    ],
  },
  {
    title: "Guest Experience",
    open: true,
    items: [
      { id: "conversations", label: "Conversations", panel: "conversations", permission: "conversations.view", status: "live", icon: "◫" },
      { id: "guest-requests", label: "Guest Requests", panel: "requests", permission: "requests.view", status: "live", icon: "☷" },
      { id: "guest-sessions", label: "Guest Sessions", panel: "sessions", permission: "conversations.view", status: "live", icon: "◉" },
      { id: "guest-preview", label: "Preview", panel: "guest", permission: "concierge.view", status: "live", icon: "◐" },
    ],
  },
  {
    title: "Property",
    open: true,
    items: [
      { id: "hotel-information", label: "Hotel Information", panel: "hotel-information", permission: "properties.view", status: "live", icon: "□" },
      { id: "rooms", label: "Rooms", panel: "rooms", permission: "properties.view", status: "live", icon: "▤" },
      { id: "facilities", label: "Facilities", panel: "facilities", permission: "properties.view", status: "live", icon: "◇" },
      { id: "restaurants", label: "Restaurants", panel: "restaurants", permission: "properties.view", status: "live", icon: "○" },
      { id: "service-catalog", label: "Service Catalog", panel: "service-catalog", permission: "requests.view", status: "live", icon: "＋" },
      { id: "recommendations", label: "Recommendations", panel: "recommendations", permission: "properties.view", status: "live", icon: "⌖" },
      { id: "zones-maps", label: "Zones & Maps", panel: "zones", permission: "properties.view", status: "live", icon: "⌗" },
    ],
  },
  {
    title: "Knowledge",
    items: [
      { id: "knowledge-overview", label: "Overview", panel: "knowledge", permission: "knowledge.view", status: "live", icon: "▣" },
      { id: "documents", label: "Documents", panel: "documents", permission: "knowledge.view", status: "live", icon: "▧" },
      { id: "faqs", label: "FAQs", panel: "faqs", permission: "knowledge.view", status: "live", icon: "?" },
    ],
  },
  {
    title: "AI",
    open: true,
    items: [
      { id: "models-providers", label: "Models & Providers", panel: "ai", permission: "ai.view", status: "live", icon: "◈" },
      { id: "ai-personality", label: "Personality", panel: "ai-personality", permission: "ai.view", status: "live", icon: "✦" },
      { id: "guardrails", label: "Guardrails", panel: "guardrails", permission: "ai.view", status: "live", icon: "⊡" },
      { id: "ai-usage", label: "Usage", panel: "ai-usage", permission: "analytics.view", status: "live", icon: "◫" },
    ],
  },
  {
    title: "Integrations",
    items: [
      { id: "antlabs-wifi", label: "ANTlabs / Wi-Fi", panel: "wifi", permission: "integrations.view", status: "live", icon: "⌁" },
      { id: "webhooks", label: "Webhooks", panel: "webhooks", permission: "integrations.view", status: "live", icon: "↗" },
    ],
  },
  {
    title: "Appearance",
    items: [
      { id: "design", label: "Design", panel: "appearance", permission: "concierge.view", status: "live", icon: "◐" },
      { id: "branding-intro", label: "Branding / Intro", panel: "intro", permission: "concierge.view", status: "live", icon: "A" },
    ],
  },
  {
    title: "Analytics",
    items: [
      { id: "guest-usage", label: "Guest Usage", panel: "guest-usage", permission: "analytics.view", status: "coming_soon", icon: "◎", superAdminOnly: true, description: "Guest usage analytics are tracked in Issue #28." },
      { id: "questions", label: "Questions", panel: "questions", permission: "analytics.view", status: "coming_soon", icon: "?", superAdminOnly: true },
      { id: "requests-analytics", label: "Requests", panel: "request-analytics", permission: "analytics.view", status: "coming_soon", icon: "▥", superAdminOnly: true },
      { id: "location", label: "Location", panel: "location", permission: "analytics.view", status: "live", icon: "⌖" },
      { id: "analytics-ai-usage", label: "AI Usage", panel: "ai-usage", permission: "analytics.view", status: "live", icon: "◫" },
    ],
  },
  {
    title: "Users & Access",
    open: true,
    items: [
      { id: "users", label: "Users", panel: "users", permission: "users.view", status: "live", icon: "◎" },
      { id: "roles", label: "Roles", panel: "roles", permission: "roles.view", status: "live", icon: "◇" },
      { id: "permissions", label: "Permissions", panel: "permissions", permission: "roles.view", status: "live", icon: "✓" },
    ],
  },
  {
    title: "Deployment",
    items: [
      { id: "domain", label: "Domain", panel: "domain", permission: "domains.view", status: "live", icon: "◌" },
      { id: "ssl", label: "SSL", panel: "ssl", permission: "domains.view", status: "live", icon: "⌑" },
      { id: "network", label: "Network", panel: "network", permission: "domains.view", status: "live", icon: "⌁" },
    ],
  },
  {
    title: "System",
    items: [
      { id: "audit", label: "Audit", panel: "audit", permission: "audit.view", status: "live", icon: "☷" },
      { id: "security", label: "Security", panel: "security", permission: "security.view", status: "live", icon: "⊡" },
      { id: "settings", label: "Settings", panel: "system-settings", permission: "system.configure", status: "live", icon: "⌘", superAdminOnly: true },
    ],
  },
];

async function jsonFetch(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && state.auth?.csrf_token) {
    headers["X-CSRF-Token"] = state.auth.csrf_token;
  }
  const response = await fetch(url, {
    headers,
    ...options,
  });
  if (response.status === 401) {
    window.location.assign("/admin/login");
    throw new Error("Administrator session expired.");
  }
  const data = await response.json().catch(() => ({}));
  if (response.status === 428) activatePanel("security");
  if (!response.ok) throw new Error(data.detail || "Request failed");
  return data;
}

function showToast(message, tone = "default") {
  const toast = $("toast");
  toast.textContent = message;
  toast.className = "toast show " + tone;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    toast.className = "toast";
  }, 2800);
}

function escapeHTML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function can(permission) {
  return Boolean(state.auth?.permissions?.includes(permission));
}

function isSuperAdmin() {
  return state.auth?.role?.slug === "super-admin";
}

function allNavItems() {
  return NAV_SECTIONS.flatMap((section) => section.items);
}

function applyPermissionVisibility() {
  for (const element of document.querySelectorAll("[data-permission]")) {
    element.hidden = !can(element.dataset.permission);
  }
}

function renderNavigation() {
  const nav = document.querySelector(".sidebar-nav");
  if (!nav) return;
  nav.innerHTML = "";
  for (const section of NAV_SECTIONS) {
    const visibleItems = section.items.filter((item) => {
      if (!can(item.permission)) return false;
      return !item.superAdminOnly || isSuperAdmin();
    });
    if (!visibleItems.length) continue;
    if (section.title === "Core") {
      for (const item of visibleItems) nav.appendChild(createNavButton(item));
      continue;
    }
    const group = document.createElement("details");
    group.className = "nav-group";
    group.open = Boolean(section.open);
    const summary = document.createElement("summary");
    summary.innerHTML = `<span class="nav-label">${escapeHTML(section.title)}</span>`;
    group.appendChild(summary);
    for (const item of visibleItems) group.appendChild(createNavButton(item));
    nav.appendChild(group);
  }
}

function createNavButton(item) {
  const status = FEATURE_STATUS[item.status] || FEATURE_STATUS.coming_soon;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "nav-item";
  button.dataset.navId = item.id;
  button.dataset.panel = item.panel;
  button.dataset.permission = item.permission;
  button.title = `${item.label}: ${status.label}`;
  button.innerHTML = `
    <span class="nav-icon" aria-hidden="true">${escapeHTML(item.icon || "•")}</span>
    <span class="nav-label">${escapeHTML(item.label)}</span>
    <span class="nav-status ${status.className}" aria-label="${status.label}" title="${status.label}">${escapeHTML(status.label)}</span>
  `;
  button.addEventListener("click", () => {
    activatePanel(item.panel, item.id);
    document.querySelector(".platform-shell")?.classList.remove("mobile-nav-open");
  });
  return button;
}

function createPlaceholderPanel(item) {
  const status = FEATURE_STATUS[item.status] || FEATURE_STATUS.coming_soon;
  const panel = document.createElement("section");
  panel.className = "panel placeholder-panel";
  panel.id = item.panel;
  panel.innerHTML = `
    <div class="page-title">
      <div>
        <p>${escapeHTML(status.label)}</p>
        <h1>${escapeHTML(item.label)}</h1>
        <span>${escapeHTML(item.description || "This capability is intentionally unavailable until its backend workflow is implemented.")}</span>
      </div>
      <span class="feature-status ${status.className}">${escapeHTML(status.label)}</span>
    </div>
    <div class="empty-state">
      <strong>${escapeHTML(status.label)}</strong>
      <p>${escapeHTML(item.description || "This tab is visible for roadmap validation, but it is not presented as a working production feature.")}</p>
    </div>
  `;
  document.querySelector(".platform-main")?.appendChild(panel);
  return panel;
}

function ensurePanel(panelId) {
  let panel = $(panelId);
  if (panel) return panel;
  const item = allNavItems().find((candidate) => candidate.panel === panelId);
  if (!item) return null;
  return createPlaceholderPanel(item);
}

async function loadCurrentAdmin() {
  const payload = await jsonFetch("/api/admin/auth/me");
  state.auth = payload.user;
  const initial = state.auth.display_name?.trim()?.[0] || state.auth.username[0] || "A";
  $("profile-avatar").textContent = initial.toUpperCase();
  $("profile-name").textContent = state.auth.display_name;
  $("profile-role").textContent = state.auth.role.name;
  $("profile-menu-name").textContent = state.auth.display_name;
  $("profile-username").textContent = `@${state.auth.username}`;
  $("profile-menu-role").textContent = state.auth.role.name;
  $("profile-detail-name").textContent = state.auth.display_name;
  $("profile-detail-username").textContent = `@${state.auth.username}`;
  $("profile-detail-role").textContent = state.auth.role.name;
  $("profile-detail-property").textContent = state.auth.property_id || "All properties";
  $("profile-detail-email").textContent = state.auth.email || "Not configured";
  $("session-expiry").textContent = formatDate(state.auth.session_expires_at);
  renderNavigation();
  applyPermissionVisibility();
  activatePanel(state.activeNavId ? allNavItems().find((item) => item.id === state.activeNavId)?.panel || "overview" : "overview", state.activeNavId || "dashboard");
  if (state.auth.force_password_change) {
    activatePanel("security");
    showToast("Change your temporary password to continue.");
  }
}

function activatePanel(panelId, navId = null) {
  ensurePanel(panelId);
  for (const panel of document.querySelectorAll(".panel")) {
    panel.classList.toggle("active", panel.id === panelId);
  }
  if (navId) state.activeNavId = navId;
  if (!navId) state.activeNavId = allNavItems().find((item) => item.panel === panelId)?.id || null;
  for (const item of document.querySelectorAll(".nav-item")) {
    item.classList.toggle("active", item.dataset.navId === state.activeNavId);
  }
  if (panelId === "overview" && currentPropertyId()) loadDashboard().catch((error) => showToast(error.message, "error"));
  if (panelId === "ai" && currentPropertyId()) {
    loadAI().catch((error) => showToast(error.message, "error"));
  }
  if (panelId === "improvement-loop" && currentPropertyId()) {
    loadImprovementLoop().catch((error) => showToast(error.message, "error"));
  }
  if (panelId === "zones" && currentPropertyId()) loadZones().catch((error) => showToast(error.message, "error"));
  if (panelId === "sessions" && currentPropertyId()) loadSessions().catch((error) => showToast(error.message, "error"));
  if (panelId === "location" && currentPropertyId()) loadLocationLive().catch((error) => showToast(error.message, "error"));
  if (panelId === "intro" && currentPropertyId()) loadIntro().catch((error) => showToast(error.message, "error"));
  if (panelId === "requests" && currentPropertyId()) loadServiceRequests().catch((error) => showToast(error.message, "error"));
  if (panelId === "conversations" && currentPropertyId()) loadConversations().catch((error) => showToast(error.message, "error"));
  if (panelId === "service-catalog" && currentPropertyId()) loadServiceCatalog().catch((error) => showToast(error.message, "error"));
  if (panelId === "recommendations" && currentPropertyId()) loadRecommendations().catch((error) => showToast(error.message, "error"));
  if (panelId === "hotel-information" && currentPropertyId()) loadHotelInformation();
  if (panelId === "rooms" && currentPropertyId()) renderRooms();
  if (panelId === "guest" && currentPropertyId()) renderGuestModules();
  if (["facilities", "restaurants"].includes(panelId) && currentPropertyId()) loadHospitalityManagement().catch((error) => showToast(error.message, "error"));
  if (panelId === "ai-usage" && currentPropertyId()) loadAIUsage().catch((error) => showToast(error.message, "error"));
  if (panelId === "wifi" && currentPropertyId()) loadAntlabsStatus().catch((error) => showToast(error.message, "error"));
  if (["knowledge", "documents", "faqs"].includes(panelId) && currentPropertyId()) loadKnowledge().catch((error) => showToast(error.message, "error"));
  if (["ai-personality", "guardrails"].includes(panelId) && currentPropertyId()) loadAIPolicy();
  if (panelId === "webhooks" && currentPropertyId()) loadWebhooks().catch((error) => showToast(error.message, "error"));
  if (["domain", "ssl", "network"].includes(panelId) && currentPropertyId()) loadDeployment().catch((error) => showToast(error.message, "error"));
  if (panelId === "system-settings") loadSystemSettings().catch((error) => showToast(error.message, "error"));
  if (panelId === "users") loadUsers().catch((error) => showToast(error.message, "error"));
  if (panelId === "roles") loadRoles().catch((error) => showToast(error.message, "error"));
  if (panelId === "permissions") loadPermissions().catch((error) => showToast(error.message, "error"));
  if (panelId === "audit") loadAudit().catch((error) => showToast(error.message, "error"));
}

function currentPropertyId() {
  return state.property?.property_id || $("property-id").value;
}

async function loadDashboard() {
  const metrics = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/dashboard`);
  $("metric-active-guests").textContent = metrics.active_guests;
  $("metric-ai-requests").textContent = metrics.ai_requests_today;
  $("metric-open-requests").textContent = metrics.open_requests;
  $("metric-overdue-requests").textContent = `${metrics.overdue_requests} overdue`;
  $("metric-auth-success").textContent = metrics.auth_success_rate === null ? "No attempts" : `${metrics.auth_success_rate}%`;
  $("metric-auth-attempts").textContent = `${metrics.auth_attempts_today} attempts today`;
  $("dashboard-ai-status").textContent = `${metrics.ai.default_provider || "None"} · ${metrics.ai.credentialed_providers}/${metrics.ai.enabled_providers} ready`;
  $("dashboard-antlabs-status").textContent = metrics.antlabs.status.replaceAll("_", " ");
  $("dashboard-session-status").textContent = `${metrics.active_guests} active`;
  $("dashboard-request-status").textContent = `${metrics.open_requests} open · ${metrics.overdue_requests} overdue`;
  $("dashboard-version").textContent = metrics.application.version;
  $("dashboard-environment").textContent = metrics.application.environment;
  const healthy = metrics.overdue_requests === 0 && metrics.usage.errors === 0;
  $("dashboard-health-chip").textContent = healthy ? "Healthy" : "Attention";
  $("dashboard-health-chip").classList.toggle("healthy", healthy);
  const activity = $("dashboard-activity");
  activity.innerHTML = metrics.usage.recent_activity.map((item) => `<div class="compact-row"><strong>${escapeHTML(item.role)} · ${escapeHTML(item.provider || "application")}</strong><span>${escapeHTML(formatDate(item.created_at))}${item.error ? ` · ${escapeHTML(item.error)}` : ""}</span></div>`).join("");
  if (!activity.children.length) activity.textContent = "No operational activity has been recorded yet.";
}

function loadHotelInformation() {
  const property = state.property;
  $("hotel-info-name").value = property.hotel_name || "";
  $("hotel-info-description").value = property.description || "";
  $("hotel-info-address").value = property.address || "";
  $("hotel-info-phone").value = property.contact_details?.phone || "";
  $("hotel-info-email").value = property.contact_details?.email || "";
  $("hotel-info-website").value = property.contact_details?.website || "";
  $("hotel-info-checkin").value = property.contact_details?.check_in || "";
  $("hotel-info-checkout").value = property.contact_details?.checkout || "";
  $("hotel-info-breakfast").value = property.contact_details?.breakfast || "";
  $("hotel-info-wifi").value = property.contact_details?.wifi_guidance || "";
  $("hotel-info-policies").value = (property.policies || []).map((item) => typeof item === "string" ? item : item.text || item.name || "").filter(Boolean).join("\n");
}

async function saveHotelInformation() {
  const name = $("hotel-info-name").value.trim();
  if (!name) throw new Error("Hotel name is required.");
  state.property = {
    ...state.property,
    hotel_name: name,
    description: $("hotel-info-description").value.trim(),
    address: $("hotel-info-address").value.trim(),
    contact_details: {
      ...(state.property.contact_details || {}),
      phone: $("hotel-info-phone").value.trim(), email: $("hotel-info-email").value.trim(), website: $("hotel-info-website").value.trim(),
      check_in: $("hotel-info-checkin").value.trim(), checkout: $("hotel-info-checkout").value.trim(),
      breakfast: $("hotel-info-breakfast").value.trim(), wifi_guidance: $("hotel-info-wifi").value.trim(),
    },
    policies: $("hotel-info-policies").value.split("\n").map((text) => text.trim()).filter(Boolean).map((text) => ({ text })),
  };
  $("hotel-name-input").value = name;
  await savePropertyBasics();
  showToast("Hotel information saved and published to the guest profile.");
}

function renderRooms() {
  const list = $("room-list");
  list.innerHTML = "";
  for (const room of state.property.rooms || []) {
    const row = document.createElement("div"); row.className = "compact-row";
    row.innerHTML = `<strong>${escapeHTML(room.name)}</strong><span>${escapeHTML(room.status)} · capacity ${Number(room.capacity || 1)}</span><span>${escapeHTML(room.description || "")}</span>`;
    const edit = document.createElement("button"); edit.type = "button"; edit.textContent = "Edit"; edit.addEventListener("click", () => {
      $("room-id").value = room.id; $("room-name").value = room.name; $("room-description").value = room.description || ""; $("room-capacity").value = room.capacity || 1; $("room-status").value = room.status || "available";
    });
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "Delete"; remove.addEventListener("click", () => deleteRoom(room.id).catch((error) => showToast(error.message, "error")));
    row.append(edit, remove); list.appendChild(row);
  }
  if (!list.children.length) list.textContent = "No rooms configured.";
}

async function saveRoom() {
  const name = $("room-name").value.trim();
  if (!name) throw new Error("Room name or type is required.");
  const id = $("room-id").value || `room_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
  const rooms = [...(state.property.rooms || [])];
  const record = { id, name, description: $("room-description").value.trim(), capacity: Number($("room-capacity").value || 1), status: $("room-status").value };
  const index = rooms.findIndex((item) => item.id === id);
  if (index >= 0) rooms[index] = record; else rooms.push(record);
  state.property.rooms = rooms;
  await savePropertyBasics();
  $("room-id").value = ""; $("room-name").value = ""; $("room-description").value = "";
  renderRooms(); showToast("Room saved.");
}

async function deleteRoom(id) {
  state.property.rooms = (state.property.rooms || []).filter((item) => item.id !== id);
  await savePropertyBasics(); renderRooms(); showToast("Room deleted.");
}

function renderGuestModules() {
  const list = $("guest-module-list"); list.innerHTML = "";
  const modules = [...(state.property.guest_modules || [])].sort((a, b) => Number(a.order || 0) - Number(b.order || 0));
  for (const module of modules) {
    const row = document.createElement("div"); row.className = "compact-row"; row.innerHTML = `<strong>${escapeHTML(module.name)}</strong><span>${module.enabled ? "Enabled" : "Disabled"} · order ${Number(module.order || 0)}</span><span>${escapeHTML(module.prompt || "")}</span>`;
    const edit = document.createElement("button"); edit.type = "button"; edit.textContent = "Edit"; edit.addEventListener("click", () => { $("guest-module-id").value = module.id; $("guest-module-name").value = module.name; $("guest-module-prompt").value = module.prompt || ""; $("guest-module-order").value = module.order || 0; $("guest-module-enabled").checked = module.enabled !== false; });
    const toggle = document.createElement("button"); toggle.type = "button"; toggle.textContent = module.enabled ? "Disable" : "Enable"; toggle.addEventListener("click", () => toggleGuestModule(module.id).catch((error) => showToast(error.message, "error")));
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "Delete"; remove.addEventListener("click", () => deleteGuestModule(module.id).catch((error) => showToast(error.message, "error")));
    row.append(edit, toggle, remove); list.appendChild(row);
  }
  if (!list.children.length) list.textContent = "No guest modules configured.";
}

async function saveGuestModule() {
  const name = $("guest-module-name").value.trim(); const prompt = $("guest-module-prompt").value.trim();
  if (!name || !prompt) throw new Error("Module name and guest prompt are required.");
  const id = $("guest-module-id").value || `module_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
  const modules = [...(state.property.guest_modules || [])]; const record = { id, name, prompt, order: Number($("guest-module-order").value || 0), enabled: $("guest-module-enabled").checked };
  const index = modules.findIndex((item) => item.id === id); if (index >= 0) modules[index] = record; else modules.push(record);
  state.property.guest_modules = modules; await savePropertyBasics(); $("guest-module-id").value = ""; $("guest-module-name").value = ""; $("guest-module-prompt").value = ""; renderGuestModules(); showToast("Guest module published.");
}

async function toggleGuestModule(id) { state.property.guest_modules = (state.property.guest_modules || []).map((item) => item.id === id ? { ...item, enabled: !item.enabled } : item); await savePropertyBasics(); renderGuestModules(); showToast("Guest module updated."); }
async function deleteGuestModule(id) { state.property.guest_modules = (state.property.guest_modules || []).filter((item) => item.id !== id); await savePropertyBasics(); renderGuestModules(); showToast("Guest module deleted."); }

async function loadHospitalityManagement() {
  state.hospitality = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/hospitality`);
  renderFacilities(); renderRestaurants();
}

function renderFacilities() {
  const list = $("facility-list"); if (!list) return; list.innerHTML = "";
  for (const item of state.hospitality?.facilities || []) {
    const row = document.createElement("div"); row.className = "compact-row"; row.innerHTML = `<strong>${escapeHTML(item.name)}</strong><span>${escapeHTML(item.facility_type)} · ${escapeHTML(item.live_status)}</span><span>${escapeHTML(item.description || "")}</span>`;
    const edit = document.createElement("button"); edit.type = "button"; edit.textContent = "Edit"; edit.addEventListener("click", () => editFacility(item));
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "Delete"; remove.addEventListener("click", () => deleteFacility(item.facility_id).catch((error) => showToast(error.message, "error")));
    row.append(edit, remove); list.appendChild(row);
  }
  if (!list.children.length) list.textContent = "No facilities configured.";
}

function editFacility(item) {
  $("facility-id").value = item.facility_id; $("facility-name").value = item.name; $("facility-type").value = item.facility_type; $("facility-location").value = item.status_note || ""; $("facility-hours").value = item.opening_hours?.display || ""; $("facility-status").value = item.live_status; $("facility-description").value = item.description || "";
}

async function saveFacility() {
  const name = $("facility-name").value.trim(); if (!name) throw new Error("Facility name is required.");
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/hospitality/facilities`, { method: "PUT", body: JSON.stringify({ data: { facility_id: $("facility-id").value || undefined, name, facility_type: $("facility-type").value.trim() || "amenity", opening_hours: { display: $("facility-hours").value.trim() }, description: $("facility-description").value.trim(), live_status: $("facility-status").value, status_note: $("facility-location").value.trim() } }) });
  $("facility-id").value = ""; $("facility-name").value = ""; await loadHospitalityManagement(); showToast("Facility saved.");
}

async function deleteFacility(id) { await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/hospitality/facilities/${encodeURIComponent(id)}`, { method: "DELETE" }); await loadHospitalityManagement(); showToast("Facility deleted."); }

function renderRestaurants() {
  const list = $("restaurant-list"); if (!list) return; list.innerHTML = "";
  for (const item of state.hospitality?.restaurants || []) {
    const row = document.createElement("div"); row.className = "compact-row"; row.innerHTML = `<strong>${escapeHTML(item.name)}</strong><span>${escapeHTML(item.location || "No location")} · ${escapeHTML(item.status)}</span><span>${escapeHTML(item.description || "")}</span>`;
    const edit = document.createElement("button"); edit.type = "button"; edit.textContent = "Edit"; edit.addEventListener("click", () => editRestaurant(item));
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "Delete"; remove.addEventListener("click", () => deleteRestaurant(item.restaurant_id).catch((error) => showToast(error.message, "error")));
    row.append(edit, remove); list.appendChild(row);
  }
  if (!list.children.length) list.textContent = "No restaurants configured.";
}

function editRestaurant(item) {
  $("restaurant-id").value = item.restaurant_id; $("restaurant-name").value = item.name; $("restaurant-location").value = item.location || ""; $("restaurant-hours").value = item.opening_hours?.display || ""; $("restaurant-meals").value = (item.meal_periods || []).join(", "); $("restaurant-status").value = item.status; $("restaurant-description").value = item.description || ""; $("restaurant-reservations").checked = item.reservation_available;
}

async function saveRestaurant() {
  const name = $("restaurant-name").value.trim(); if (!name) throw new Error("Restaurant name is required.");
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/restaurants`, { method: "POST", body: JSON.stringify({ data: { restaurant_id: $("restaurant-id").value || undefined, name, location: $("restaurant-location").value.trim(), opening_hours: { display: $("restaurant-hours").value.trim() }, meal_periods: $("restaurant-meals").value.split(",").map((item) => item.trim()).filter(Boolean), status: $("restaurant-status").value, description: $("restaurant-description").value.trim(), reservation_available: $("restaurant-reservations").checked } }) });
  $("restaurant-id").value = ""; $("restaurant-name").value = ""; await loadHospitalityManagement(); showToast("Restaurant saved.");
}

async function deleteRestaurant(id) { await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/restaurants/${encodeURIComponent(id)}`, { method: "DELETE" }); await loadHospitalityManagement(); showToast("Restaurant deleted."); }

async function loadKnowledge() {
  state.knowledge = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge`);
  renderKnowledge();
}

function makeActionButton(label, handler, secondary = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  if (secondary) button.className = "secondary";
  button.addEventListener("click", () => Promise.resolve(handler()).catch((error) => showToast(error.message, "error")));
  return button;
}

function renderKnowledge() {
  const entryList = $("knowledge-list"); entryList.innerHTML = "";
  for (const item of state.knowledge.items || []) {
    const row = document.createElement("div"); row.className = "compact-row";
    row.innerHTML = `<strong>${escapeHTML(item.title)}</strong><span>${item.enabled ? "Available to AI" : "Disabled"} · ${escapeHTML(formatDate(item.updated_at))}</span><span>${escapeHTML((item.body || "").slice(0, 180))}</span>`;
    row.append(
      makeActionButton("Edit", () => { $("knowledge-id").value = item.item_id; $("knowledge-title").value = item.title; $("knowledge-body").value = item.body; $("knowledge-enabled").checked = item.enabled; }),
      makeActionButton("Delete", () => deleteKnowledgeItem(item.item_id), true),
    );
    entryList.appendChild(row);
  }
  if (!entryList.children.length) entryList.textContent = "No managed knowledge entries.";

  const documentList = $("document-list"); documentList.innerHTML = "";
  for (const item of state.knowledge.documents || []) {
    const row = document.createElement("div"); row.className = "compact-row";
    row.innerHTML = `<strong>${escapeHTML(item.source_name || item.title)}</strong><span>${escapeHTML(item.status)} · ${escapeHTML(item.content_type || "unknown type")}</span><span>${escapeHTML(item.error || "Ready for verified retrieval")}</span>`;
    row.append(makeActionButton("Delete", () => deleteKnowledgeItem(item.item_id), true)); documentList.appendChild(row);
  }
  if (!documentList.children.length) documentList.textContent = "No documents uploaded.";

  const faqList = $("faq-list"); faqList.innerHTML = "";
  for (const item of state.knowledge.faqs || []) {
    const row = document.createElement("div"); row.className = "compact-row";
    row.innerHTML = `<strong>${escapeHTML(item.question)}</strong><span>${item.enabled ? "Available to AI" : "Disabled"}</span><span>${escapeHTML(item.answer)}</span>`;
    row.append(
      makeActionButton("Edit", () => { $("faq-id").value = item.item_id; $("faq-question").value = item.question; $("faq-answer").value = item.answer; $("faq-enabled").checked = item.enabled; }),
      makeActionButton("Delete", () => deleteKnowledgeItem(item.item_id), true),
    );
    faqList.appendChild(row);
  }
  if (!faqList.children.length) faqList.textContent = "No managed FAQs.";
}

async function saveKnowledgeEntry() {
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge`, { method: "PUT", body: JSON.stringify({ item_id: $("knowledge-id").value || null, kind: "entry", title: $("knowledge-title").value.trim(), body: $("knowledge-body").value.trim(), enabled: $("knowledge-enabled").checked }) });
  $("knowledge-id").value = ""; $("knowledge-title").value = ""; $("knowledge-body").value = ""; await loadKnowledge(); showToast("Knowledge entry saved.");
}

async function saveFAQ() {
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge`, { method: "PUT", body: JSON.stringify({ item_id: $("faq-id").value || null, kind: "faq", question: $("faq-question").value.trim(), answer: $("faq-answer").value.trim(), enabled: $("faq-enabled").checked }) });
  $("faq-id").value = ""; $("faq-question").value = ""; $("faq-answer").value = ""; await loadKnowledge(); showToast("FAQ saved.");
}

async function uploadKnowledgeDocument(file) {
  if (!file) return;
  const content = new Uint8Array(await file.arrayBuffer()); let binary = "";
  for (const byte of content) binary += String.fromCharCode(byte);
  const item = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge/documents`, { method: "POST", body: JSON.stringify({ filename: file.name, content_type: file.type || "application/octet-stream", content_base64: btoa(binary) }) });
  await loadKnowledge(); showToast(item.status === "ready" ? "Document ingested." : item.error, item.status === "ready" ? "default" : "error");
}

async function deleteKnowledgeItem(itemId) { await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge/${encodeURIComponent(itemId)}`, { method: "DELETE" }); await loadKnowledge(); showToast("Knowledge item deleted."); }

function loadAIPolicy() {
  const personality = state.property.personality || {};
  $("personality-name").value = personality.name || state.property.concierge_name || "Concierge";
  $("personality-tone").value = personality.tone || "warm";
  $("personality-formality").value = personality.formality || "balanced";
  $("personality-length").value = personality.response_length || "concise";
  $("personality-greeting").value = personality.greeting_behavior || "first_message";
  $("personality-instructions").value = personality.property_instructions || "";
  const guardrails = state.property.guardrails || {};
  $("guardrail-unknown").value = guardrails.unknown_answer || "state_unavailable";
  $("guardrail-escalation").value = guardrails.escalation_behavior || "offer_human";
  $("guardrail-allowed").value = (guardrails.allowed_topics || []).join("\n");
  $("guardrail-restricted").value = (guardrails.restricted_topics || []).join("\n");
  $("guardrail-sensitive").value = guardrails.sensitive_information || "Never expose credentials, payment data, private guest records, or infrastructure identifiers.";
  $("guardrail-human").value = guardrails.human_escalation || "Offer hotel staff assistance when a request cannot be completed safely or from verified data.";
}

const readLines = (id) => $(id).value.split("\n").map((value) => value.trim()).filter(Boolean);

async function savePersonality() {
  state.property.personality = { name: $("personality-name").value.trim(), tone: $("personality-tone").value, formality: $("personality-formality").value, response_length: $("personality-length").value, greeting_behavior: $("personality-greeting").value, property_instructions: $("personality-instructions").value.trim() };
  state.property.concierge_name = state.property.personality.name || state.property.concierge_name; $("concierge-name-input").value = state.property.concierge_name;
  await savePropertyBasics(); showToast("AI personality saved.");
}

async function saveGuardrails() {
  state.property.guardrails = { allowed_topics: readLines("guardrail-allowed"), restricted_topics: readLines("guardrail-restricted"), unknown_answer: $("guardrail-unknown").value, escalation_behavior: $("guardrail-escalation").value, sensitive_information: $("guardrail-sensitive").value.trim(), human_escalation: $("guardrail-human").value.trim() };
  await savePropertyBasics(); showToast("Guardrails saved.");
}

async function loadWebhooks() { state.webhooks = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/webhooks`); renderWebhooks(); }

function renderWebhooks() {
  const list = $("webhook-list"); list.innerHTML = "";
  for (const item of state.webhooks.webhooks || []) {
    const row = document.createElement("div"); row.className = "compact-row";
    row.innerHTML = `<strong>${escapeHTML(item.name)}</strong><span>${item.enabled ? "Enabled" : "Disabled"} · ${escapeHTML(item.last_status.replaceAll("_", " "))}</span><span>${escapeHTML(item.endpoint_url)}${item.last_error ? ` · ${escapeHTML(item.last_error)}` : ""}</span>`;
    row.append(
      makeActionButton("Edit", () => { $("webhook-id").value = item.webhook_id; $("webhook-name").value = item.name; $("webhook-url").value = item.endpoint_url; $("webhook-enabled").checked = item.enabled; for (const option of $("webhook-events").options) option.selected = item.events.includes(option.value); $("webhook-secret").placeholder = item.secret_configured ? "Saved securely; leave blank to keep" : "Optional signing secret"; }),
      makeActionButton("Test", () => testWebhook(item.webhook_id)),
      makeActionButton("Delete", () => deleteWebhook(item.webhook_id), true),
    ); list.appendChild(row);
  }
  if (!list.children.length) list.textContent = "No webhook endpoints configured.";
  $("webhook-deliveries").innerHTML = (state.webhooks.deliveries || []).slice(0, 20).map((item) => `<div class="compact-row"><strong>${escapeHTML(item.event_name)}</strong><span>${escapeHTML(item.status)} · ${escapeHTML(formatDate(item.attempted_at))}</span><span>${escapeHTML(item.error || (item.response_status ? `HTTP ${item.response_status}` : ""))}</span></div>`).join("") || "No delivery attempts recorded.";
}

async function saveWebhook() {
  const events = [...$("webhook-events").selectedOptions].map((option) => option.value);
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/webhooks`, { method: "PUT", body: JSON.stringify({ webhook_id: $("webhook-id").value || null, name: $("webhook-name").value.trim(), endpoint_url: $("webhook-url").value.trim(), events, enabled: $("webhook-enabled").checked, secret: $("webhook-secret").value }) });
  $("webhook-id").value = ""; $("webhook-name").value = ""; $("webhook-url").value = ""; $("webhook-secret").value = ""; await loadWebhooks(); showToast("Webhook saved.");
}
async function testWebhook(id) { const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/webhooks/${encodeURIComponent(id)}/test`, { method: "POST" }); await loadWebhooks(); showToast(result.status === "delivered" ? "Webhook delivered." : result.error, result.status === "delivered" ? "default" : "error"); }
async function deleteWebhook(id) { await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/webhooks/${encodeURIComponent(id)}`, { method: "DELETE" }); await loadWebhooks(); showToast("Webhook deleted."); }

function renderManagedLocations() {
  const list = $("managed-location-list"); list.innerHTML = "";
  for (const item of state.property.app_settings?.locations || []) {
    const row = document.createElement("div"); row.className = "compact-row"; row.innerHTML = `<strong>${escapeHTML(item.name)}</strong><span>${escapeHTML(item.type || "location")} · ${item.guest_visible ? "Guest visible" : "Operations only"}</span><span>${escapeHTML(item.description || "")}</span>`;
    row.append(makeActionButton("Edit", () => { $("location-id").value = item.id; $("location-name").value = item.name; $("location-type").value = item.type || ""; $("location-description").value = item.description || ""; $("location-latitude").value = item.latitude ?? ""; $("location-longitude").value = item.longitude ?? ""; $("location-visible").checked = item.guest_visible !== false; }), makeActionButton("Delete", () => deleteManagedLocation(item.id), true)); list.appendChild(row);
  }
  if (!list.children.length) list.textContent = "No managed locations.";
}

async function saveManagedLocation() {
  const name = $("location-name").value.trim(); if (!name) throw new Error("Location name is required.");
  const appSettings = { ...(state.property.app_settings || {}) }; const locations = [...(appSettings.locations || [])]; const id = $("location-id").value || `location_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
  const record = { id, name, type: $("location-type").value.trim(), description: $("location-description").value.trim(), latitude: $("location-latitude").value === "" ? null : Number($("location-latitude").value), longitude: $("location-longitude").value === "" ? null : Number($("location-longitude").value), guest_visible: $("location-visible").checked };
  const index = locations.findIndex((item) => item.id === id); if (index >= 0) locations[index] = record; else locations.push(record); appSettings.locations = locations; state.property.app_settings = appSettings; await savePropertyBasics(); $("location-id").value = ""; $("location-name").value = ""; $("location-description").value = ""; renderManagedLocations(); showToast("Location saved.");
}
async function deleteManagedLocation(id) { state.property.app_settings = { ...(state.property.app_settings || {}), locations: (state.property.app_settings?.locations || []).filter((item) => item.id !== id) }; await savePropertyBasics(); renderManagedLocations(); showToast("Location deleted."); }

async function loadDeployment() {
  state.deployment = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/deployment/status`);
  const deployment = state.property.app_settings?.deployment || {};
  $("deployment-domain").value = state.property.domain || ""; $("deployment-public-url").value = deployment.public_base_url || ""; $("network-reverse-proxy").checked = Boolean(deployment.reverse_proxy); $("network-https-required").checked = deployment.https_required !== false; $("network-trusted-proxy").value = deployment.trusted_proxy || "";
  $("domain-status").textContent = state.deployment.domain.status.replaceAll("_", " "); $("domain-addresses").textContent = state.deployment.domain.resolved_addresses.join(", ") || "—"; $("deployment-last-checked").textContent = state.deployment.last_checked_at ? formatDate(state.deployment.last_checked_at) : "Never";
  $("ssl-status").textContent = state.deployment.ssl.status.replaceAll("_", " "); $("ssl-issuer").textContent = state.deployment.ssl.issuer || "—"; $("ssl-expiration").textContent = state.deployment.ssl.expires_at ? formatDate(state.deployment.ssl.expires_at) : "—"; $("ssl-days").textContent = state.deployment.ssl.days_remaining ?? "—"; $("ssl-error").textContent = state.deployment.ssl.error || "—";
}

async function saveDeploymentSettings() { state.property.domain = $("deployment-domain").value.trim().toLowerCase(); $("domain-input").value = state.property.domain; state.property.app_settings = { ...(state.property.app_settings || {}), deployment: { ...(state.property.app_settings?.deployment || {}), public_base_url: $("deployment-public-url").value.trim(), reverse_proxy: $("network-reverse-proxy").checked, https_required: $("network-https-required").checked, trusted_proxy: $("network-trusted-proxy").value.trim() } }; await savePropertyBasics(); await loadDeployment(); showToast("Deployment settings saved."); }
async function verifyDeployment() { const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/deployment/verify`, { method: "POST" }); await loadDeployment(); showToast(result.domain_status === "verified" ? "Domain verification completed." : result.detail || "Verification remains pending.", result.domain_status === "verified" ? "default" : "error"); }

async function loadSystemSettings() {
  const application = state.property.app_settings?.application || {};
  $("setting-language").value = application.default_language || state.property.languages?.[0] || "en"; $("setting-timezone").value = application.timezone || state.property.timezone || "UTC"; $("setting-maintenance").checked = Boolean(application.maintenance_enabled); $("setting-maintenance-message").value = application.maintenance_message || "";
  const smtp = await jsonFetch("/api/admin/system/email"); $("smtp-enabled").checked = smtp.enabled; $("smtp-host").value = smtp.host; $("smtp-port").value = smtp.port; $("smtp-security").value = smtp.security; $("smtp-username").value = smtp.username; $("smtp-from").value = smtp.from_address; $("smtp-password").value = ""; $("smtp-password").placeholder = smtp.password_configured ? `Saved securely (${smtp.password_masked})` : "Not configured"; $("smtp-status").textContent = smtp.enabled ? "SMTP enabled. Use Test Connection to verify reachability." : "SMTP is disabled; password-reset requests remain generic and do not send email.";
}
async function saveApplicationSettings() { const application = { default_language: $("setting-language").value.trim() || "en", timezone: $("setting-timezone").value.trim() || "UTC", maintenance_enabled: $("setting-maintenance").checked, maintenance_message: $("setting-maintenance-message").value.trim() }; state.property.languages = [application.default_language]; state.property.timezone = application.timezone; state.property.app_settings = { ...(state.property.app_settings || {}), application }; await savePropertyBasics(); showToast("Application settings saved."); }
async function saveSMTPSettings() { await jsonFetch("/api/admin/system/email", { method: "PUT", body: JSON.stringify({ enabled: $("smtp-enabled").checked, host: $("smtp-host").value.trim(), port: Number($("smtp-port").value || 587), security: $("smtp-security").value, username: $("smtp-username").value.trim(), password: $("smtp-password").value, from_address: $("smtp-from").value.trim() }) }); await loadSystemSettings(); showToast("Email settings saved securely."); }
async function testSMTP() { const result = await jsonFetch("/api/admin/system/email/test", { method: "POST" }); $("smtp-status").textContent = result.detail; showToast(result.detail, result.status === "connected" ? "default" : "error"); }

async function loadAIUsage() {
  const data = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/ai/usage?days=${encodeURIComponent($("ai-usage-period").value)}`);
  $("ai-usage-metrics").innerHTML = `<article><span>Requests</span><strong>${data.requests}</strong></article><article><span>Errors</span><strong>${data.errors}</strong></article><article><span>Average latency</span><strong>${data.average_latency_ms} ms</strong></article><article><span>Time range</span><strong>${data.days} days</strong></article>`;
  $("ai-usage-list").innerHTML = data.providers.map((item) => `<div class="compact-row"><strong>${escapeHTML(item.provider || "unknown")} · ${escapeHTML(item.model || "unknown")}</strong><span>${item.requests} requests · ${Math.round(item.average_latency_ms || 0)} ms · ${item.errors} errors</span></div>`).join("") || "No AI usage recorded for this range.";
}

async function loadAntlabsStatus() {
  const data = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/antlabs/status`);
  renderAntlabsStatus(data);
}

function renderAntlabsStatus(data) {
  $("antlabs-configured").textContent = data.configured ? "Configured" : "Not configured"; $("antlabs-mode").textContent = data.mode; $("antlabs-status").textContent = data.status.replaceAll("_", " "); $("antlabs-endpoint").textContent = data.endpoint || "Not configured";
  if (data.detail) $("antlabs-detail").textContent = data.detail;
}

async function testAntlabs() {
  const data = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/antlabs/test`, { method: "POST" }); renderAntlabsStatus(data); $("antlabs-last-check").textContent = new Date().toLocaleString(); showToast(data.detail, data.ok ? "default" : "error");
}

function setPublishState(text) {
  $("publish-state").textContent = text;
}

function hydrateProperty(property) {
  state.property = property;
  $("property-id").value = property.property_id;
  $("hotel-name-input").value = property.hotel_name;
  $("overview-title").textContent = property.hotel_name;
  $("concierge-name-input").value = property.concierge_name;
  $("domain-input").value = property.domain || "";
  $("deployment-mode").value = property.deployment_mode || "on-prem";
  renderAuthTypes(property.antlabs_config?.authentication_types || {});
  loadAIPolicy();
  renderManagedLocations();
}

function renderAuthTypes(config = {}) {
  const list = $("auth-type-list");
  if (!list) return;
  list.innerHTML = "";
  for (const type of authTypeDefinitions) {
    const row = document.createElement("article");
    row.className = "auth-type-row";
    row.innerHTML = `
      <div>
        <h3>${type.label}</h3>
        <p>${type.description}</p>
      </div>
      <label class="toggle-switch">
        <input type="checkbox" data-auth-type="${type.id}" ${config[type.id]?.enabled ? "checked" : ""}>
        <span></span>
      </label>
    `;
    row.querySelector("input").addEventListener("change", () => {
      const enabled = readAuthTypes().filter((item) => item.enabled).length;
      showToast(`${enabled} authentication type${enabled === 1 ? "" : "s"} enabled.`);
    });
    row.querySelector(".toggle-switch").addEventListener("click", (event) => {
      event.preventDefault();
      const input = row.querySelector("input");
      input.checked = !input.checked;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    list.appendChild(row);
  }
}

function readAuthTypes() {
  return authTypeDefinitions.map((type) => ({
    id: type.id,
    label: type.label,
    enabled: Boolean(document.querySelector(`[data-auth-type="${type.id}"]`)?.checked),
  }));
}

function providerLabel(provider) {
  const icons = {
    gemini: "G",
    groq: "Gr",
    openai: "O",
    openrouter: "OR",
    claude: "C",
    copilot: "GH",
    local: "L",
  };
  return icons[provider.provider_id] || "AI";
}

function statusLabel(status) {
  return String(status || "not_configured").replaceAll("_", " ");
}

function statusClass(status) {
  if (["connected", "local"].includes(status)) return "good";
  if (["connection_failed", "authentication_expired"].includes(status)) return "bad";
  if (status === "disabled") return "muted";
  return "neutral";
}

function modelOptions(provider) {
  const models = new Set(provider.model_catalog || []);
  if (provider.selected_model) models.add(provider.selected_model);
  return [...models].filter(Boolean);
}

function namedModelOptions(provider) {
  const names = new Map((provider.model_options || []).map((item) => [item.id, item.name || item.id]));
  return modelOptions(provider).map((id) => ({ id, name: names.get(id) || id }));
}

function renderModelChips(provider) {
  const models = modelOptions(provider);
  if (!models.length) return '<p class="model-empty">No public model list available yet.</p>';
  return models
    .map((model) => `<span class="model-chip${model === provider.selected_model ? " selected" : ""}">${model}</span>`)
    .join("");
}

function hydrateAI(payload) {
  state.ai = payload;
  const defaultSelect = $("ai-default-provider");
  defaultSelect.innerHTML = "";
  for (const provider of payload.providers) {
    const option = document.createElement("option");
    option.value = provider.provider_id;
    option.textContent = provider.name;
    option.disabled = provider.unavailable;
    defaultSelect.appendChild(option);
  }
  defaultSelect.value = payload.settings.default_provider;
  $("ai-routing-mode").value = payload.settings.routing_mode || "fixed";
  $("ai-local-only").checked = Boolean(payload.settings.local_only);
  renderProviderCards();
}

function renderProviderCards() {
  const grid = $("provider-grid");
  grid.innerHTML = "";
  const providers = state.ai?.providers || [];
  const healthy = providers.filter((provider) => ["connected", "local"].includes(provider.status)).length;
  $("ai-health-summary").textContent = `${healthy} ready · ${providers.length} providers`;

  const header = document.createElement("div");
  header.className = "provider-row provider-header-row";
  header.innerHTML = `
    <span class="col-header">Provider</span>
    <span class="col-header">Status</span>
    <span class="col-header text-right">Configuration</span>
  `;
  grid.appendChild(header);

  for (const provider of providers) {
    const row = document.createElement("article");
    row.className = "provider-row";
    const statusType = statusClass(provider.status);
    row.innerHTML = `
      <div class="provider-name-cell">
        <span class="provider-icon">${providerLabel(provider)}</span>
        <div>
          <h3>${provider.name}</h3>
          <p>${provider.auth_method.replaceAll("_", " ")}</p>
        </div>
      </div>
      <div class="provider-status ${statusType}">
        <span class="status-dot ${statusType}"></span>
        <span class="status-text">${statusLabel(provider.status)}</span>
      </div>
      <div class="provider-actions">
        <button type="button" data-action="configure" class="configure-btn">${provider.unavailable ? "Details" : "Configure"}</button>
        <button type="button" data-action="test" class="test-btn">Test</button>
      </div>
    `;
    row.querySelector('[data-action="configure"]').addEventListener("click", () => openProviderDrawer(provider.provider_id));
    row.querySelector('[data-action="test"]').addEventListener("click", () => testProvider(provider.provider_id));
    grid.appendChild(row);
  }
}

function openProviderDrawer(providerId) {
  const provider = state.ai.providers.find((item) => item.provider_id === providerId);
  state.activeProvider = provider;
  $("drawer-provider-name").textContent = provider.name;
  $("drawer-provider-status").textContent = statusLabel(provider.status);
  $("drawer-provider-note").textContent = provider.status_note;
  $("drawer-status").value = statusLabel(provider.status);
  renderDrawerModelList(provider);
  $("drawer-model").value = provider.selected_model || "";
  $("drawer-endpoint").value = provider.endpoint_url || "";
  $("drawer-temperature").value = provider.temperature ?? 0.2;
  $("drawer-max-tokens").value = provider.max_output_tokens ?? 160;
  $("drawer-timeout").value = provider.timeout_seconds ?? 45;
  $("drawer-enabled").checked = Boolean(provider.enabled);
  $("drawer-enabled").disabled = Boolean(provider.unavailable);
  const auth = $("drawer-auth-method");
  auth.innerHTML = "";
  for (const method of provider.auth_methods) {
    const option = document.createElement("option");
    option.value = method;
    option.textContent = method.replaceAll("_", " ");
    auth.appendChild(option);
  }
  auth.value = provider.auth_method;
  const hint = provider.credentials?.[0]?.display_hint;
  $("drawer-credential-hint").textContent = hint ? `Stored credential: ${hint}` : (provider.provider_id === "local" ? "No cloud credential required." : "No credential stored.");
  $("drawer-secret").value = "";
  $("drawer-test-result").textContent = "";
  setProviderDirty(false);
  $("provider-drawer-backdrop").hidden = false;
  $("provider-drawer").hidden = false;
}

function renderDrawerModelList(provider) {
  const list = $("drawer-model");
  list.innerHTML = "";
  for (const model of namedModelOptions(provider)) {
    list.appendChild(new Option(model.name === model.id ? model.id : `${model.name} · ${model.id}`, model.id));
  }
}

function closeProviderDrawer() {
  if (state.providerDirty && !window.confirm("You have changes not yet saved. Close without saving?")) {
    return;
  }
  $("provider-drawer-backdrop").hidden = true;
  $("provider-drawer").hidden = true;
  state.activeProvider = null;
  setProviderDirty(false);
}

function setProviderDirty(isDirty) {
  state.providerDirty = isDirty;
  $("provider-unsaved-note").hidden = !isDirty;
}

function markProviderDirty() {
  if (state.activeProvider) setProviderDirty(true);
}

async function loadAI() {
  const payload = await jsonFetch("/api/admin/properties/" + encodeURIComponent(currentPropertyId()) + "/ai");
  hydrateAI(payload);
}

async function saveAISettings() {
  const selectedProvider = state.ai?.providers.find((provider) => provider.provider_id === $("ai-default-provider").value);
  if ($("ai-local-only").checked && selectedProvider?.cloud) {
    $("ai-local-only").checked = false;
  }
  const payload = {
    default_provider: $("ai-default-provider").value,
    routing_mode: $("ai-routing-mode").value,
    local_only: $("ai-local-only").checked,
  };
  const result = await jsonFetch("/api/admin/properties/" + encodeURIComponent(currentPropertyId()) + "/ai/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  hydrateAI(result);
  showToast("AI settings saved.");
}

function handleDefaultProviderChange() {
  const selectedProvider = state.ai?.providers.find((provider) => provider.provider_id === $("ai-default-provider").value);
  if (selectedProvider?.cloud && $("ai-local-only").checked) {
    $("ai-local-only").checked = false;
    showToast("Local-Only Mode turned off for cloud provider selection.");
  }
}

function handleLocalOnlyChange() {
  const selectedProvider = state.ai?.providers.find((provider) => provider.provider_id === $("ai-default-provider").value);
  if ($("ai-local-only").checked && selectedProvider?.cloud) {
    $("ai-default-provider").value = "local";
    showToast("Default provider changed to Local AI.");
  }
}

function providerPayloadFromDrawer() {
  return {
    enabled: $("drawer-enabled").checked,
    auth_method: $("drawer-auth-method").value,
    selected_model: $("drawer-model").value.trim(),
    endpoint_url: $("drawer-endpoint").value.trim(),
    temperature: Number($("drawer-temperature").value || 0.2),
    max_output_tokens: Number($("drawer-max-tokens").value || 160),
    timeout_seconds: Number($("drawer-timeout").value || 45),
    config: {
      engine: state.activeProvider?.provider_id === "local" ? "ollama" : undefined,
    },
  };
}

async function saveProvider() {
  const providerId = state.activeProvider.provider_id;
  const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/ai/providers/${providerId}`, {
    method: "PUT",
    body: JSON.stringify(providerPayloadFromDrawer()),
  });
  await loadAI();
  openProviderDrawer(result.provider.provider_id);
  setProviderDirty(false);
  showToast(`${result.provider.name} saved.`);
}

async function saveProviderSecret() {
  const value = $("drawer-secret").value.trim();
  if (!value) {
    showToast("Paste a credential first.", "error");
    return;
  }
  const providerId = state.activeProvider.provider_id;
  const credentialType = $("drawer-auth-method").value === "oauth" ? "oauth_access_token" : "api_key";
  const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/ai/providers/${providerId}/credentials`, {
    method: "POST",
    body: JSON.stringify({ credential_type: credentialType, value }),
  });
  await loadAI();
  openProviderDrawer(result.provider.provider_id);
  showToast("Credential saved.");
}

async function removeProviderSecret() {
  const providerId = state.activeProvider.provider_id;
  const credential = state.activeProvider.credentials?.[0];
  if (!credential) return;
  const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/ai/providers/${providerId}/credentials/${credential.type}`, {
    method: "DELETE",
  });
  await loadAI();
  openProviderDrawer(result.provider.provider_id);
  showToast("Credential removed.");
}

async function refreshProviderModels() {
  const providerId = state.activeProvider.provider_id;
  const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/ai/providers/${providerId}/models/refresh`, {
    method: "POST",
  });
  await loadAI();
  state.activeProvider = state.ai.providers.find((provider) => provider.provider_id === providerId);
  renderDrawerModelList(state.activeProvider);
  $("drawer-model").value = state.activeProvider.selected_model || "";
  showToast(`${result.models.length} models detected.`);
}

async function testProvider(providerId = state.activeProvider?.provider_id) {
  const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/ai/providers/${providerId}/test`, {
    method: "POST",
  });
  await loadAI();
  const message = result.ok
    ? `Connection successful · ${result.latency_ms ?? 0} ms · ${result.models_detected ?? 0} models`
    : `Connection failed · ${result.error || "Check configuration"}`;
  if (state.activeProvider?.provider_id === providerId) {
    $("drawer-test-result").textContent = message;
  }
  showToast(message, result.ok ? "default" : "error");
}

function providerName(providerId) {
  return state.ai?.providers.find((item) => item.provider_id === providerId)?.name || providerId;
}

function loopModelOptions(selectedModel = "") {
  const provider = state.ai?.providers.find((item) => item.provider_id === $("loop-provider").value);
  const select = $("loop-model");
  const current = selectedModel || select.value || provider?.selected_model || "";
  select.innerHTML = "";
  const models = new Set(modelOptions(provider || {}));
  if (current) models.add(current);
  for (const model of models) select.appendChild(new Option(model, model));
  select.value = current || provider?.selected_model || "";
}

function loopProviderOptions(providerId, model) {
  const select = $("loop-provider");
  select.innerHTML = "";
  for (const provider of state.ai?.providers || []) {
    if (provider.unavailable) continue;
    select.appendChild(new Option(`${provider.name}${provider.enabled ? "" : " · disabled"}`, provider.provider_id));
  }
  select.value = providerId || state.ai?.settings?.default_provider || "local";
  if (!select.value && select.options.length) select.selectedIndex = 0;
  loopModelOptions(model);
}

async function loadImprovementLoop(preserveForm = false) {
  if (!state.ai) await loadAI();
  const payload = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/improvement-loop`);
  hydrateImprovementLoop(payload, preserveForm);
}

function hydrateImprovementLoop(payload, preserveForm = false) {
  state.improvementLoop = payload;
  const loop = payload.loop;
  if (!preserveForm) {
    $("loop-objective").value = loop.objective || "";
    $("loop-criteria").value = loop.satisfaction_criteria || "";
    $("loop-evidence").value = loop.evidence || "";
    loopProviderOptions(loop.provider_id, loop.model);
    $("loop-approval-mode").value = loop.approval_mode || "manual";
    $("loop-interval").value = loop.interval_seconds ?? 60;
    $("loop-max-iterations").value = loop.max_iterations ?? 0;
    $("loop-failure-limit").value = loop.max_consecutive_failures ?? 3;
  }
  renderLoopStatus(loop);
  renderLoopLatest(payload.iterations || []);
  renderLoopHistory(payload.iterations || []);
}

function renderLoopStatus(loop) {
  const badge = $("loop-status-badge");
  badge.className = `loop-status-badge ${loop.status}`;
  badge.querySelector("span").textContent = statusLabel(loop.status);
  $("loop-iteration-count").textContent = `${loop.iteration_count} iteration${loop.iteration_count === 1 ? "" : "s"}`;
  const copy = {
    draft: ["Ready to configure", "Choose an enabled provider and define exactly what satisfaction means."],
    running: ["Loop is running", `${providerName(loop.provider_id)} · ${loop.model} · iteration ${loop.iteration_count + 1}`],
    awaiting_approval: ["Waiting for your decision", "Approve the latest result or request a revision with feedback."],
    paused: ["Loop is paused", "You can change its evidence and controls before resuming."],
    stopped: ["Loop is stopped", "History is preserved and the loop can be resumed."],
    satisfied: ["Marked satisfied by operator", "Only an operator can set this state."],
    error: ["Loop needs attention", loop.last_error || "The selected provider could not complete the iteration."],
  }[loop.status] || ["Ready", "Configure the loop to begin."];
  $("loop-command-title").textContent = copy[0];
  $("loop-command-detail").textContent = copy[1];
  const active = ["running", "awaiting_approval"].includes(loop.status);
  $("loop-save").disabled = active;
  $("loop-run-once").disabled = active;
  $("loop-start").disabled = active;
  $("loop-pause").disabled = loop.status !== "running";
  $("loop-resume").disabled = !["paused", "stopped", "error"].includes(loop.status);
  $("loop-stop").disabled = ["draft", "stopped", "satisfied"].includes(loop.status);
  $("loop-satisfied").disabled = loop.status === "satisfied";
  $("loop-approve").disabled = loop.status !== "awaiting_approval";
  $("loop-revise").disabled = loop.status !== "awaiting_approval";
  for (const input of document.querySelectorAll("#improvement-loop .loop-config input, #improvement-loop .loop-config select, #improvement-loop .loop-config textarea")) {
    input.disabled = active;
  }
}

function renderLoopLatest(iterations) {
  const latest = iterations[0];
  if (!latest) {
    $("loop-latest").innerHTML = "<p>No iteration has run yet.</p>";
    $("loop-review-state").textContent = "No review";
    return;
  }
  $("loop-review-state").textContent = statusLabel(latest.operator_decision || latest.status);
  if (latest.status === "error") {
    $("loop-latest").innerHTML = `<p><strong>Provider error</strong></p><p>${escapeHTML(latest.error)}</p>`;
    return;
  }
  const response = latest.response || {};
  const findings = Array.isArray(response.findings) ? response.findings : [];
  const score = latest.score == null ? "—" : latest.score;
  $("loop-latest").innerHTML = `
    <div class="loop-score-row"><strong>${escapeHTML(score)}</strong><div class="loop-score-track" aria-label="Quality score ${escapeHTML(score)}"><i style="width:${latest.score == null ? 0 : latest.score}%"></i></div></div>
    <p><strong>${escapeHTML(latest.summary || "Iteration completed")}</strong></p>
    ${findings.length ? `<ul class="loop-finding-list">${findings.map((item) => `<li>${escapeHTML(item)}</li>`).join("")}</ul>` : ""}
    <p><strong>Next action:</strong> ${escapeHTML(response.next_action || "Review this iteration.")}</p>
    ${latest.model_recommends_satisfied ? "<p>The model recommends readiness. You still decide when the loop is satisfied.</p>" : ""}
  `;
}

function renderLoopHistory(iterations) {
  const history = $("loop-history");
  history.innerHTML = "";
  if (!iterations.length) {
    history.innerHTML = '<div class="loop-history-empty">Iterations will appear here with their model, score, decision, and timestamp.</div>';
    return;
  }
  for (const iteration of iterations) {
    const row = document.createElement("article");
    row.className = "loop-history-row";
    const when = iteration.finished_at || iteration.started_at;
    row.innerHTML = `
      <strong>#${iteration.iteration_number}</strong>
      <div><strong>${escapeHTML(iteration.summary || iteration.error || "In progress")}</strong><p>${escapeHTML(providerName(iteration.provider_id))} · ${escapeHTML(iteration.model)}</p></div>
      <span class="status-pill ${iteration.status === "error" ? "bad" : "good"}">${escapeHTML(statusLabel(iteration.operator_decision || iteration.status))}</span>
      <time>${when ? new Date(when * 1000).toLocaleString() : "Running"}</time>
    `;
    history.appendChild(row);
  }
}

function improvementLoopPayload() {
  return {
    objective: $("loop-objective").value.trim(),
    satisfaction_criteria: $("loop-criteria").value.trim(),
    evidence: $("loop-evidence").value.trim(),
    provider_id: $("loop-provider").value,
    model: $("loop-model").value,
    approval_mode: $("loop-approval-mode").value,
    interval_seconds: Number($("loop-interval").value || 60),
    max_iterations: Number($("loop-max-iterations").value || 0),
    max_consecutive_failures: Number($("loop-failure-limit").value || 3),
  };
}

async function saveImprovementLoop({ quiet = false } = {}) {
  const payload = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/improvement-loop`, {
    method: "PUT",
    body: JSON.stringify(improvementLoopPayload()),
  });
  hydrateImprovementLoop(payload);
  if (!quiet) showToast("Improvement loop saved.");
}

async function improvementLoopAction(action, message) {
  const payload = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/improvement-loop/${action}`, { method: "POST" });
  hydrateImprovementLoop(payload, ["start", "resume"].includes(action));
  showToast(message);
}

async function startImprovementLoop(action = "start") {
  await saveImprovementLoop({ quiet: true });
  await improvementLoopAction(action, action === "start" ? "Improvement loop started." : "Improvement loop resumed.");
}

async function runImprovementLoopOnce() {
  await saveImprovementLoop({ quiet: true });
  const button = $("loop-run-once");
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Running...";
  try {
    const payload = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/improvement-loop/run-next`, { method: "POST" });
    hydrateImprovementLoop(payload);
    showToast("Iteration completed.");
  } finally {
    button.textContent = label;
  }
}

async function decideImprovementLoop(decision) {
  const payload = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/improvement-loop/decision`, {
    method: "POST",
    body: JSON.stringify({ decision, feedback: $("loop-feedback").value.trim() }),
  });
  $("loop-feedback").value = "";
  hydrateImprovementLoop(payload, true);
  showToast(decision === "approved" ? "Approved. The loop will continue." : "Revision requested and feedback recorded.");
}

function hydrateDesign(design) {
  state.designDraft = structuredClone(design.draft);
  state.designPublished = structuredClone(design.published);
  state.versions = design.versions || [];
  fillDesignForm(state.designDraft);
  renderVersions();
  updatePreview();
  setPublishState(state.versions.length ? `Published v${state.versions.at(-1).version}` : "No published version");
}

function fillDesignForm(config) {
  $("design-hotel-name").value = config.branding?.hotelName || "";
  $("design-concierge-name").value = config.branding?.conciergeName || "";
  $("logo-display-input").value = config.branding?.logoDisplay || "mark_name";
  $("logo-url-input").value = config.branding?.logoUrl || "";
  $("greeting-input").value = config.welcome?.greeting || "";
  $("welcome-input").value = config.welcome?.headline || "";
  $("composer-placeholder-input").value = config.composer?.placeholder || "";
  $("background-input").value = normalizeColor(config.theme?.background || "#fbfbfa");
  $("surface-input").value = normalizeColor(config.theme?.surface || "#ffffff");
  $("text-color-input").value = normalizeColor(config.theme?.textPrimary || "#18181b");
  $("secondary-text-color-input").value = normalizeColor(config.theme?.textSecondary || "#71717a");
  $("accent-input").value = normalizeColor(config.theme?.accent || "#18181b");
  $("user-message-input").value = normalizeColor(config.theme?.userMessageBackground || "#eeeeee");
  $("button-color-input").value = normalizeColor(config.theme?.buttonColor || config.theme?.accent || "#18181b");
  $("composer-background-input").value = normalizeColor(config.composer?.background || config.theme?.composerBackground || "#ffffff");
  $("background-image-url-input").value = config.theme?.backgroundImageUrl || "";
  $("background-overlay-input").value = config.theme?.backgroundOverlay ?? 0;
  $("font-input").value = config.typography?.fontFamily || "Geist";
  $("density-input").value = config.theme?.density || "comfortable";
  $("content-width-input").value = config.layout?.contentWidth || 840;
  $("message-width-input").value = config.layout?.messageWidth || 680;
  $("composer-width-input").value = config.layout?.composerWidth || 840;
  $("base-font-size-input").value = config.typography?.baseFontSize || 15;
  $("message-spacing-input").value = config.layout?.messageSpacing || config.messages?.messageSpacing || 24;
  $("radius-input").value = config.theme?.radius ?? 14;
  $("suggestion-layout-input").value = config.layout?.suggestionLayout || "stack";
  $("user-style-input").value = config.messages?.userStyle || "bubble";
  $("assistant-style-input").value = config.messages?.assistantStyle || "minimal";
  $("header-enabled-input").checked = config.header?.enabled !== false;
  $("show-logo-input").checked = config.header?.showLogo !== false;
  $("show-name-input").checked = config.header?.showHotelName !== false;
  $("show-concierge-input").checked = config.header?.showConciergeName !== false;
  renderPrompts(config.suggestions || []);
}

function designPayload() {
  const base = structuredClone(state.designDraft || {});
  base.branding = {
    ...(base.branding || {}),
    hotelName: $("design-hotel-name").value.trim() || "Hotel",
    conciergeName: $("design-concierge-name").value.trim() || "Concierge",
    logoUrl: $("logo-url-input").value,
    logoDisplay: $("logo-display-input").value,
  };
  base.theme = {
    ...(base.theme || {}),
    font: $("font-input").value,
    background: $("background-input").value,
    surface: $("surface-input").value,
    textPrimary: $("text-color-input").value,
    textSecondary: $("secondary-text-color-input").value,
    accent: $("accent-input").value,
    accentText: base.theme?.accentText || "#ffffff",
    border: base.theme?.border || "#e4e4e7",
    userMessageBackground: $("user-message-input").value,
    userMessageText: base.theme?.userMessageText || "#18181b",
    assistantText: base.theme?.assistantText || "#18181b",
    composerBackground: $("composer-background-input").value,
    buttonColor: $("button-color-input").value,
    radius: Number($("radius-input").value || 0),
    density: $("density-input").value,
    backgroundImageUrl: $("background-image-url-input").value,
    backgroundOverlay: Number($("background-overlay-input").value || 0),
  };
  base.typography = {
    ...(base.typography || {}),
    fontFamily: $("font-input").value,
    baseFontSize: Number($("base-font-size-input").value || 15),
  };
  base.layout = {
    ...(base.layout || {}),
    contentWidth: Number($("content-width-input").value || 840),
    messageWidth: Number($("message-width-input").value || 680),
    composerWidth: Number($("composer-width-input").value || 840),
    messageSpacing: Number($("message-spacing-input").value || 24),
    suggestionLayout: $("suggestion-layout-input").value,
  };
  base.header = {
    ...(base.header || {}),
    enabled: $("header-enabled-input").checked,
    showLogo: $("show-logo-input").checked,
    showHotelName: $("show-name-input").checked,
    showConciergeName: $("show-concierge-input").checked,
  };
  base.welcome = {
    ...(base.welcome || {}),
    greeting: $("greeting-input").value.trim() || "Good evening.",
    headline: $("welcome-input").value.trim() || "How can I help with your stay?",
  };
  base.composer = {
    ...(base.composer || {}),
    placeholder: $("composer-placeholder-input").value.trim() || "Ask your concierge...",
    background: $("composer-background-input").value,
  };
  base.messages = {
    ...(base.messages || {}),
    userStyle: $("user-style-input").value,
    assistantStyle: $("assistant-style-input").value,
    messageSpacing: Number($("message-spacing-input").value || 24),
  };
  base.suggestions = readPrompts();
  return base;
}

function propertyPayload() {
  const property = state.property || {};
  const antlabsConfig = {
    ...(property.antlabs_config || {}),
    authentication_types: Object.fromEntries(
      readAuthTypes().map((type) => [type.id, { label: type.label, enabled: type.enabled }])
    ),
  };
  return {
    property_id: $("property-id").value,
    hotel_name: $("hotel-name-input").value,
    description: property.description || "",
    domain: $("domain-input").value,
    deployment_mode: $("deployment-mode").value,
    timezone: property.timezone || "UTC",
    latitude: property.latitude,
    longitude: property.longitude,
    address: property.address || "",
    contact_details: property.contact_details || {},
    logo_url: property.logo_url || "",
    brand_assets: property.brand_assets || {},
    concierge_name: $("concierge-name-input").value,
    concierge_avatar_url: property.concierge_avatar_url || "",
    primary_color: $("accent-input").value,
    secondary_color: $("surface-input").value,
    background: property.background || "",
    languages: property.languages || ["en"],
    facilities: property.facilities || [],
    dining: property.dining || [],
    spa: property.spa || {},
    pool: property.pool || {},
    gym: property.gym || {},
    policies: property.policies || [],
    support_contacts: property.support_contacts || [],
    quick_actions: readPrompts().map((item) => ({ label: item.label, prompt: item.prompt })),
    ai_settings: property.ai_settings || {},
    antlabs_config: antlabsConfig,
    knowledge_sources: property.knowledge_sources || [],
    rooms: property.rooms || [],
    guest_modules: property.guest_modules || [],
    personality: property.personality || {},
    guardrails: property.guardrails || {},
    app_settings: property.app_settings || {},
    welcome: $("welcome-input").value,
  };
}

function renderPrompts(suggestions) {
  const list = $("prompt-list");
  list.innerHTML = "";
  for (const suggestion of suggestions) {
    addPromptRow(suggestion.label || suggestion.prompt || "", suggestion.prompt || suggestion.label || "", suggestion.enabled !== false);
  }
  renderPreviewPrompts();
}

function addPromptRow(label = "New prompt", prompt = "New prompt", enabled = true) {
  const row = document.createElement("div");
  row.className = "prompt-row";

  const labelInput = document.createElement("input");
  labelInput.className = "prompt-label";
  labelInput.setAttribute("aria-label", "Suggested prompt label");
  labelInput.value = label;

  const promptInput = document.createElement("input");
  promptInput.className = "prompt-text";
  promptInput.setAttribute("aria-label", "Suggested prompt text");
  promptInput.value = prompt;

  const enabledLabel = document.createElement("label");
  enabledLabel.className = "prompt-enabled";
  const enabledCheckbox = document.createElement("input");
  enabledCheckbox.type = "checkbox";
  enabledCheckbox.checked = enabled;
  enabledLabel.appendChild(enabledCheckbox);
  enabledLabel.appendChild(document.createTextNode(" Enabled"));

  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.setAttribute("aria-label", "Remove prompt");
  removeButton.textContent = "x";
  removeButton.addEventListener("click", () => {
    row.remove();
    updatePreview();
  });

  row.appendChild(labelInput);
  row.appendChild(promptInput);
  row.appendChild(enabledLabel);
  row.appendChild(removeButton);

  for (const input of row.querySelectorAll("input")) {
    input.addEventListener("input", updatePreview);
    input.addEventListener("change", updatePreview);
  }
  $("prompt-list").appendChild(row);
}

function readPrompts() {
  return [...document.querySelectorAll(".prompt-row")]
    .map((row, index) => {
      const label = row.querySelector(".prompt-label").value.trim();
      const prompt = row.querySelector(".prompt-text").value.trim();
      return {
        label,
        prompt: prompt || label,
        icon: "",
        enabled: row.querySelector(".prompt-enabled input").checked,
        order: index,
      };
    })
    .filter((item) => item.label && item.prompt);
}

function renderPreviewPrompts() {
  const preview = $("preview-prompts");
  preview.innerHTML = "";
  for (const item of readPrompts().filter((candidate) => candidate.enabled)) {
    const element = document.createElement("span");
    element.textContent = item.label;
    preview.appendChild(element);
  }
}

function renderVersions() {
  const list = $("version-list");
  list.innerHTML = "";
  if (!state.versions.length) {
    list.textContent = "No published versions yet.";
    return;
  }
  for (const item of [...state.versions].reverse()) {
    const row = document.createElement("div");
    row.className = "version-row";
    const date = item.published_at ? new Date(item.published_at * 1000).toLocaleString() : "Unknown date";
    const label = document.createElement("span");
    label.textContent = `v${item.version} · ${date}`;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Restore to draft";
    button.addEventListener("click", () => restoreVersion(item.version));
    row.appendChild(label);
    row.appendChild(button);
    list.appendChild(row);
  }
}

function updatePreview() {
  const config = designPayload();
  const accent = config.theme.accent;
  const logo = $("preview-logo");
  $("preview-hotel").textContent = config.branding.hotelName;
  $("preview-concierge").textContent = config.branding.conciergeName;
  logo.textContent = config.branding.hotelName.slice(0, 1).toUpperCase();
  logo.style.backgroundImage = config.branding.logoUrl ? `url("${config.branding.logoUrl}")` : "";
  logo.classList.toggle("has-image", Boolean(config.branding.logoUrl));
  $("chat-preview").dataset.logoDisplay = config.branding.logoDisplay || "mark_name";
  $("preview-greeting").textContent = config.welcome.greeting;
  $("preview-welcome").textContent = config.welcome.headline;
  $("preview-placeholder").textContent = config.composer.placeholder;
  $("chat-preview").style.setProperty("--preview-bg", config.theme.background);
  $("chat-preview").style.setProperty("--preview-surface", config.theme.surface);
  $("chat-preview").style.setProperty("--preview-text", config.theme.textPrimary);
  $("chat-preview").style.setProperty("--preview-subtle", config.theme.textSecondary);
  $("chat-preview").style.setProperty("--preview-bg-image", config.theme.backgroundImageUrl ? `url("${config.theme.backgroundImageUrl}")` : "none");
  $("chat-preview").style.setProperty("--preview-overlay", (config.theme.backgroundOverlay || 0) / 100);
  $("chat-preview").style.setProperty("--preview-font", previewFontStack(config.typography.fontFamily || config.theme.font || "Geist"));
  $("chat-preview").style.setProperty("--preview-button", config.theme.buttonColor || accent);
  $("chat-preview").style.setProperty("--preview-composer", config.composer.background || config.theme.composerBackground || config.theme.surface);
  $("chat-preview").style.setProperty("--preview-radius", `${config.theme.radius ?? 14}px`);
  $("chat-preview").style.setProperty("--preview-font-size", `${config.typography.baseFontSize || 15}px`);
  $("chat-preview").style.setProperty("--preview-message-spacing", `${config.layout.messageSpacing || 24}px`);
  $("chat-preview").style.setProperty("--preview-content-width", `${config.layout.contentWidth || 840}px`);
  document.documentElement.style.setProperty("--accent", accent);
  renderPreviewPrompts();
}

function previewFontStack(font) {
  const stacks = {
    Geist: '"Geist Sans", Inter, system-ui, sans-serif',
    Inter: 'Inter, system-ui, sans-serif',
    Manrope: 'Manrope, Inter, system-ui, sans-serif',
    "DM Sans": '"DM Sans", Inter, system-ui, sans-serif',
    Poppins: 'Poppins, Inter, system-ui, sans-serif',
    Montserrat: 'Montserrat, Inter, system-ui, sans-serif',
    Lato: 'Lato, Inter, system-ui, sans-serif',
    Merriweather: 'Merriweather, Georgia, serif',
    "Playfair Display": '"Playfair Display", Georgia, serif',
    "system-ui": 'system-ui, sans-serif',
  };
  return stacks[font] || stacks.Geist;
}

function handleImageUpload(input, targetId, { maxBytes, recommended }) {
  const file = input.files?.[0];
  if (!file) return;
  if (file.size > maxBytes) {
    showToast(`${recommended} Try a smaller file.`, "error");
    input.value = "";
    return;
  }
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    $(targetId).value = reader.result;
    updatePreview();
  });
  reader.readAsDataURL(file);
}

async function savePropertyBasics() {
  const payload = propertyPayload();
  state.property = await jsonFetch("/api/admin/properties/" + encodeURIComponent(payload.property_id), {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  hydrateProperty(state.property);
}

async function saveDraft({ quiet = false } = {}) {
  const activePanel = document.querySelector(".panel.active")?.id;
  if (activePanel === "appearance") {
    $("hotel-name-input").value = $("design-hotel-name").value || $("hotel-name-input").value;
    $("concierge-name-input").value = $("design-concierge-name").value || $("concierge-name-input").value;
  } else if (activePanel === "overview") {
    $("design-hotel-name").value = $("hotel-name-input").value || $("design-hotel-name").value;
    $("design-concierge-name").value = $("concierge-name-input").value || $("design-concierge-name").value;
  }
  await savePropertyBasics();
  const result = await jsonFetch("/api/admin/properties/" + encodeURIComponent(currentPropertyId()) + "/design/draft", {
    method: "PUT",
    body: JSON.stringify({ config: designPayload() }),
  });
  state.designDraft = structuredClone(result.draft);
  fillDesignForm(state.designDraft);
  updatePreview();
  setPublishState("Draft saved");
  if (!quiet) showToast("Draft saved.");
}

async function publishDesign() {
  await saveDraft({ quiet: true });
  const result = await jsonFetch("/api/admin/properties/" + encodeURIComponent(currentPropertyId()) + "/design/publish", {
    method: "POST",
  });
  state.designPublished = structuredClone(result.published);
  await loadDesign();
  showToast(`Published guest chat v${result.version}.`);
}

async function discardDesign() {
  const result = await jsonFetch("/api/admin/properties/" + encodeURIComponent(currentPropertyId()) + "/design/discard", {
    method: "POST",
  });
  state.designDraft = structuredClone(result.draft);
  fillDesignForm(state.designDraft);
  updatePreview();
  setPublishState("Draft discarded");
  showToast("Draft reset to the published design.");
}

async function restoreVersion(version) {
  const result = await jsonFetch("/api/admin/properties/" + encodeURIComponent(currentPropertyId()) + "/design/restore", {
    method: "POST",
    body: JSON.stringify({ version }),
  });
  state.designDraft = structuredClone(result.draft);
  fillDesignForm(state.designDraft);
  updatePreview();
  setPublishState(`Restored v${version} to draft`);
  showToast(`Version ${version} restored to draft. Publish when ready.`);
}

async function loadDesign() {
  const design = await jsonFetch("/api/admin/properties/" + encodeURIComponent(currentPropertyId()) + "/design");
  hydrateDesign(design);
}

async function loadProperty() {
  const data = await jsonFetch("/api/admin/properties");
  if (!data.properties.length) throw new Error("No property configured.");
  state.properties = data.properties;
  const switcher = $("property-switcher");
  switcher.innerHTML = "";
  for (const property of state.properties) {
    switcher.appendChild(new Option(property.hotel_name, property.property_id));
  }
  const selectedId = state.property?.property_id || state.auth?.property_id || state.properties[0].property_id;
  const selected = state.properties.find((property) => property.property_id === selectedId) || state.properties[0];
  switcher.value = selected.property_id;
  hydrateProperty(selected);
  hydratePropertyOptions();
  if (can("concierge.view")) await loadDesign();
  if (can("ai.view")) await loadAI();
  if (can("dashboard.view")) await loadDashboard();
}

async function switchProperty(propertyId) {
  const property = state.properties.find((item) => item.property_id === propertyId);
  if (!property || property.property_id === currentPropertyId()) return;
  hydrateProperty(property);
  state.ai = null;
  state.improvementLoop = null;
  state.catalog = { departments: [], services: [] };
  state.recommendations = [];
  state.knowledge = { items: [], documents: [], faqs: [] };
  state.webhooks = { webhooks: [], deliveries: [] };
  state.deployment = null;
  const tasks = [];
  if (can("concierge.view")) tasks.push(loadDesign());
  if (can("ai.view")) tasks.push(loadAI());
  if (can("dashboard.view")) tasks.push(loadDashboard());
  await Promise.all(tasks);
  showToast(`Switched to ${property.hotel_name}.`);
}

function hydratePropertyOptions() {
  for (const id of ["admin-property", "role-property", "audit-property"]) {
    const select = $(id);
    if (!select) continue;
    const current = select.value;
    select.innerHTML = id === "audit-property" ? '<option value="">All properties</option>' : "";
    if (id === "role-property" && can("properties.all")) select.appendChild(new Option("Global", ""));
    for (const property of state.properties) select.appendChild(new Option(property.hotel_name, property.property_id));
    select.value = current || state.auth?.property_id || (id === "role-property" && can("properties.all") ? "" : state.properties[0]?.property_id || "");
  }
}

async function loadZones() {
  state.zones = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/zones`);
  hydrateZoneSelectors();
  renderZoneTree();
  renderMapCanvas();
}

function hydrateZoneSelectors() {
  const buildingSelect = $("zone-building-select");
  const floorSelect = $("zone-floor-select");
  buildingSelect.innerHTML = "";
  floorSelect.innerHTML = "";
  for (const building of state.zones.buildings) {
    buildingSelect.appendChild(new Option(building.name, building.building_id));
  }
  if (!state.zones.buildings.length) {
    buildingSelect.appendChild(new Option("No building yet", ""));
  }
  const floors = state.zones.floors.filter((floor) => !buildingSelect.value || floor.building_id === buildingSelect.value);
  for (const floor of floors) floorSelect.appendChild(new Option(floor.name, floor.floor_id));
  if (!floors.length) floorSelect.appendChild(new Option("No floor yet", ""));
}

function renderZoneTree() {
  const list = $("zone-tree");
  list.innerHTML = "";
  if (!state.zones.buildings.length) {
    const row = document.createElement("div");
    row.className = "compact-row";
    row.innerHTML = "<strong>No zones yet</strong><span>Use Save Object to create the first building, floor, and zone.</span>";
    list.appendChild(row);
    return;
  }
  for (const zone of state.zones.zones) {
    const row = document.createElement("div");
    row.className = "compact-row";
    row.innerHTML = `<strong>${zone.name}</strong><span>${zone.category || "common"} · ${zone.guest_visible ? "guest visible" : "operations only"}</span>`;
    row.addEventListener("click", () => {
      state.selectedMapObject = { ...zone, objectType: "zone" };
      $("map-object-name").value = zone.name;
      $("map-object-type").value = "zone";
      $("map-object-visible").value = String(zone.guest_visible);
      renderMapCanvas();
    });
    list.appendChild(row);
  }
}

function renderMapCanvas() {
  const canvas = $("floor-map-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#fbfbfa";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const layers = Object.fromEntries([...document.querySelectorAll(".layer-toggle")].map((input) => [input.dataset.layer, input.checked]));
  const floorId = $("zone-floor-select")?.value;
  const floorMap = state.zones?.maps?.find((item) => item.floor_id === floorId);
  if (layers.floor_plan && floorMap) {
    if (floorMap.content_type === "application/pdf") {
      ctx.fillStyle = "#f4f4f5"; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.fillStyle = "#52525b"; ctx.font = "16px system-ui"; ctx.fillText("PDF floor plan uploaded. Use PNG, JPEG, or SVG for an editable canvas background.", 28, 42);
    } else {
      let image = state.mapBackgrounds.get(floorMap.map_id);
      if (!image) {
        image = new Image();
        image.addEventListener("load", renderMapCanvas, { once: true });
        image.src = floorMap.url;
        state.mapBackgrounds.set(floorMap.map_id, image);
      }
      if (image.complete && image.naturalWidth) ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    }
  }
  ctx.strokeStyle = "#d4d4d8";
  ctx.lineWidth = 1;
  for (let x = 0; x < canvas.width; x += 40) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
  }
  for (let y = 0; y < canvas.height; y += 40) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
  }
  if (layers.zones) {
    for (const zone of state.zones?.zones || []) drawGeometry(ctx, zone.geometry, zone === state.selectedMapObject ? "#0f766e" : "#2563eb", zone.name);
  }
  if (layers.facilities) {
    for (const facility of state.zones?.facilities || []) {
      const zone = state.zones.zones.find((item) => item.zone_id === facility.zone_id);
      if (zone) drawLabel(ctx, zone.geometry, facility.name, "#7c2d12");
    }
  }
  if (layers.access_points) {
    for (const ap of state.zones?.access_points || []) {
      ctx.fillStyle = "#dc2626";
      ctx.beginPath(); ctx.arc(ap.x || 40, ap.y || 40, 6, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#18181b"; ctx.fillText(ap.name, (ap.x || 40) + 9, (ap.y || 40) + 4);
    }
  }
  for (const object of state.mapObjects) drawGeometry(ctx, object.geometry, "#16a34a", object.name || "Draft");
}

function drawGeometry(ctx, geometry, color, label) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color + "22";
  ctx.lineWidth = 2;
  if (geometry.type === "rectangle") {
    ctx.fillRect(geometry.x, geometry.y, geometry.width, geometry.height);
    ctx.strokeRect(geometry.x, geometry.y, geometry.width, geometry.height);
  } else if (geometry.type === "ellipse") {
    ctx.beginPath(); ctx.ellipse(geometry.cx, geometry.cy, geometry.rx, geometry.ry, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  } else if (geometry.type === "polygon" && geometry.points?.length) {
    ctx.beginPath();
    ctx.moveTo(geometry.points[0][0], geometry.points[0][1]);
    for (const point of geometry.points.slice(1)) ctx.lineTo(point[0], point[1]);
    ctx.closePath(); ctx.fill(); ctx.stroke();
  }
  drawLabel(ctx, geometry, label, color);
  ctx.restore();
}

function drawLabel(ctx, geometry, label, color) {
  const point = geometry.points?.[0] || [geometry.x || geometry.cx || 30, geometry.y || geometry.cy || 30];
  ctx.fillStyle = color;
  ctx.font = "13px system-ui";
  ctx.fillText(label || "", point[0] + 8, point[1] + 18);
}

async function ensureDefaultBuildingAndFloor() {
  if (!state.zones?.buildings.length) {
    await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/buildings`, {
      method: "POST",
      body: JSON.stringify({ data: { name: "Main Building" } }),
    });
    await loadZones();
  }
  if (!state.zones?.floors.length) {
    await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/floors`, {
      method: "POST",
      body: JSON.stringify({ data: { building_id: state.zones.buildings[0].building_id, name: "Ground Floor", level: 0 } }),
    });
    await loadZones();
  }
}

async function saveMapObject() {
  await ensureDefaultBuildingAndFloor();
  const floorId = $("zone-floor-select").value || state.zones.floors[0].floor_id;
  const type = $("map-object-type").value;
  const name = $("map-object-name").value.trim() || type.replaceAll("_", " ");
  const visible = $("map-object-visible").value === "true";
  const draft = state.mapObjects.at(-1) || { geometry: { type: "rectangle", x: 120, y: 120, width: 180, height: 100 } };
  if (type === "facility") {
    const zone = state.zones.zones[0] || await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/zones`, {
      method: "PUT",
      body: JSON.stringify({ data: { floor_id: floorId, name: "Common Area", geometry: draft.geometry, guest_visible: true } }),
    });
    await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/facilities`, {
      method: "POST",
      body: JSON.stringify({ data: { zone_id: zone.zone_id, name, facility_type: type, guest_visible: visible } }),
    });
  } else if (type === "access_point") {
    const zone = state.zones.zones[0];
    if (!zone) throw new Error("Create a zone before adding an access point.");
    await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/access-points`, {
      method: "POST",
      body: JSON.stringify({ data: { zone_id: zone.zone_id, name, identifier: $("map-ap-identifier").value.trim(), x: draft.geometry.x || draft.geometry.cx || 80, y: draft.geometry.y || draft.geometry.cy || 80 } }),
    });
  } else {
    await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/zones`, {
      method: "PUT",
      body: JSON.stringify({ data: { floor_id: floorId, name, category: type, geometry: draft.geometry, guest_visible: visible } }),
    });
  }
  state.mapObjects = [];
  await loadZones();
  showToast("Map object saved.");
}

function handleCanvasPointer(event) {
  const canvas = $("floor-map-canvas");
  const rect = canvas.getBoundingClientRect();
  const x = Math.round((event.clientX - rect.left) * (canvas.width / rect.width));
  const y = Math.round((event.clientY - rect.top) * (canvas.height / rect.height));
  if (!["rectangle", "ellipse", "polygon", "freeform"].includes(state.mapTool)) return;
  state.mapHistory.push(structuredClone(state.mapObjects));
  const snap = (value) => Math.round(value / 10) * 10;
  if (state.mapTool === "freeform") {
    const object = { name: $("map-object-name").value || "Draft", geometry: { type: "polygon", points: [[x, y]] } };
    state.mapObjects.push(object); state.freeformDraft = object; canvas.setPointerCapture?.(event.pointerId); state.mapRedo = []; renderMapCanvas(); return;
  }
  const geometry = state.mapTool === "ellipse"
    ? { type: "ellipse", cx: snap(x), cy: snap(y), rx: 80, ry: 50 }
    : state.mapTool === "polygon"
      ? { type: "polygon", points: [[snap(x), snap(y)], [snap(x + 140), snap(y + 20)], [snap(x + 80), snap(y + 100)]] }
      : { type: "rectangle", x: snap(x), y: snap(y), width: 180, height: 110 };
  state.mapObjects.push({ name: $("map-object-name").value || "Draft", geometry });
  state.mapRedo = [];
  renderMapCanvas();
}

function handleCanvasPointerMove(event) {
  if (!state.freeformDraft) return;
  const canvas = $("floor-map-canvas"); const rect = canvas.getBoundingClientRect();
  const point = [Math.round((event.clientX - rect.left) * (canvas.width / rect.width)), Math.round((event.clientY - rect.top) * (canvas.height / rect.height))];
  const points = state.freeformDraft.geometry.points; const last = points.at(-1);
  if (!last || Math.hypot(point[0] - last[0], point[1] - last[1]) >= 6) { points.push(point); renderMapCanvas(); }
}

function finishFreeform() {
  if (state.freeformDraft?.geometry.points.length < 3) state.mapObjects = state.mapObjects.filter((item) => item !== state.freeformDraft);
  state.freeformDraft = null; renderMapCanvas();
}

async function uploadFloorMap(file) {
  if (!file) return;
  const content = await file.arrayBuffer();
  const bytes = new Uint8Array(content);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  await ensureDefaultBuildingAndFloor();
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/floors/${$("zone-floor-select").value}/maps`, {
    method: "POST",
    body: JSON.stringify({ filename: file.name, content_type: file.type || "application/octet-stream", content_base64: btoa(binary) }),
  });
  await loadZones();
  showToast("Floor plan uploaded as locked background.");
}

async function loadSessions() {
  const data = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/sessions`);
  const list = $("session-list");
  list.innerHTML = "";
  for (const session of data.sessions || []) {
    const row = document.createElement("div"); row.className = "compact-row";
    row.innerHTML = `<strong>${escapeHTML(session.session_id)}</strong><span>${escapeHTML(session.session_status)} · ${session.authenticated ? "authenticated" : "not authenticated"} · ${escapeHTML(session.interaction_status)} · ${session.message_count} messages</span><span>Started ${escapeHTML(formatDate(session.created_at))} · last activity ${escapeHTML(formatDate(session.last_seen_at))}${session.last_provider ? ` · ${escapeHTML(session.last_provider)}` : ""}</span>`;
    list.appendChild(row);
  }
  for (const stay of data.stays) {
    const row = document.createElement("div");
    row.className = "compact-row";
    row.innerHTML = `<strong>Stay ${escapeHTML(stay.stay_id)}</strong><span>${escapeHTML(stay.status)} · room ${escapeHTML(stay.room || "none")} · memory ${stay.memory_summary ? "stored" : "empty"}</span>`;
    row.addEventListener("click", () => {
      $("memory-stay-id").value = stay.stay_id;
      $("memory-summary").value = stay.memory_summary?.conversation_summary || "";
    });
    list.appendChild(row);
  }
  if (!list.children.length) list.textContent = "No guest sessions or stays yet.";
}

async function createStaySession() {
  const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/sessions/reconnect`, {
    method: "POST",
    body: JSON.stringify({ raw_mac: $("session-raw-mac").value.trim(), room: $("session-room").value.trim() || null }),
  });
  $("memory-stay-id").value = result.stay.stay_id;
  await loadSessions();
  showToast("Stay restored with pseudonymous device identity.");
}

async function saveStayMemory() {
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/stays/${encodeURIComponent($("memory-stay-id").value)}/memory`, {
    method: "PUT",
    body: JSON.stringify({ memory: { conversation_summary: $("memory-summary").value } }),
  });
  await loadSessions();
  showToast("Compact stay memory saved.");
}

async function loadLocationLive() {
  renderManagedLocations();
  const data = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/location/live`);
  $("location-live-metrics").innerHTML = `
    <article><span>Detected devices</span><strong>${data.currently_detected}</strong></article>
    <article><span>Active stays</span><strong>${data.active_sessions}</strong></article>
    <article><span>Busiest zone</span><strong>${data.busiest_zone_id || "-"}</strong></article>
    <article><span>Zones occupied</span><strong>${Object.keys(data.occupancy_by_zone || {}).length}</strong></article>
  `;
}

async function recordObservation() {
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/location/observations`, {
    method: "POST",
    body: JSON.stringify({ raw_mac: $("obs-raw-mac").value.trim(), access_point_identifier: $("obs-ap-id").value.trim() }),
  });
  await loadLocationLive();
  showToast("Observation recorded.");
}

async function loadLocationReport() {
  const now = Math.floor(Date.now() / 1000);
  const period = $("analytics-period").value;
  const days = period === "30" ? 30 : period === "7" ? 7 : 1;
  const start = period === "yesterday" ? now - 2 * 86400 : now - days * 86400;
  const end = period === "yesterday" ? now - 86400 : now;
  const report = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/location/report`, {
    method: "POST",
    body: JSON.stringify({ start_at: start, end_at: end, filters: {} }),
  });
  $("location-report").innerHTML = `
    <div class="compact-row"><strong>${report.total_visits} visits · ${report.unique_visits} unique devices</strong><span>Zone occupancy heatmap uses aggregate AP-associated zones.</span></div>
    ${Object.entries(report.area_metrics).map(([zone, metric]) => `<div class="compact-row"><strong>${zone}</strong><span>${metric.total_visits} visits · ${metric.average_dwell_seconds}s avg dwell · ${metric.repeat_visits} repeat visits</span></div>`).join("")}
    ${report.movement_patterns.map((item) => `<div class="compact-row"><strong>${item.source_zone_id} -> ${item.destination_zone_id}</strong><span>${item.count} transitions · ${item.percentage}%</span></div>`).join("")}
  `;
}

async function loadIntro() {
  state.intro = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/intro`);
  $("intro-mode").value = state.intro.mode;
  $("intro-preset").value = state.intro.preset;
  $("intro-duration").value = state.intro.duration_ms;
  $("intro-message").value = state.intro.welcome_message;
  $("intro-background").value = normalizeColor(state.intro.background);
  $("intro-brand-color").value = normalizeColor(state.intro.brand_color);
  $("intro-first-visit").checked = state.intro.first_visit_only;
  $("intro-skip").checked = state.intro.allow_skip;
  updateIntroPreview();
}

function updateIntroPreview() {
  $("intro-preview-card").style.background = $("intro-background").value || "#fbfbfa";
  $("intro-preview-card").querySelector("strong").style.background = $("intro-brand-color").value || "#18181b";
  $("intro-preview-message").textContent = $("intro-message").value || "Welcome";
  $("intro-preview-card").querySelector("button").hidden = !$("intro-skip").checked;
}

async function saveIntro() {
  const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/intro`, {
    method: "PUT",
    body: JSON.stringify({ data: {
      mode: $("intro-mode").value,
      preset: $("intro-preset").value,
      duration_ms: Number($("intro-duration").value || 1400),
      background: $("intro-background").value,
      brand_color: $("intro-brand-color").value,
      welcome_message: $("intro-message").value,
      first_visit_only: $("intro-first-visit").checked,
      allow_skip: $("intro-skip").checked,
    } }),
  });
  state.intro = result;
  showToast("Intro experience saved.");
}

async function uploadIntroAsset(file) {
  if (!file) return;
  const content = await file.arrayBuffer();
  const bytes = new Uint8Array(content);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/intro/upload`, {
    method: "POST",
    body: JSON.stringify({ filename: file.name, content_type: file.type || (file.name.endsWith(".lottie") ? "application/octet-stream" : "application/json"), content_base64: btoa(binary) }),
  });
  await loadIntro();
  showToast("Intro animation uploaded.");
}

async function loadConversations() {
  const data = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/conversations`);
  state.conversations = data.conversations;
  $("conversation-retention-days").value = data.retention?.retention_days || 30;
  renderConversations();
  if (state.selectedConversation) {
    state.selectedConversation = state.conversations.find((item) => item.session_id === state.selectedConversation.session_id) || null;
    renderConversationMessages();
  }
}

async function saveConversationRetention() {
  const retentionDays = Number($("conversation-retention-days").value);
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/conversations/retention`, { method: "PUT", body: JSON.stringify({ retention_days: retentionDays }) });
  await loadConversations(); showToast("Conversation retention updated.");
}

function renderConversations() {
  const query = $("conversation-search").value.trim().toLowerCase();
  const status = $("conversation-status-filter").value;
  const list = $("conversation-list");
  list.innerHTML = "";
  for (const conversation of state.conversations.filter((item) => (!status || item.status === status) && (!query || item.session_id.toLowerCase().includes(query) || item.messages.some((message) => message.content.toLowerCase().includes(query))))) {
    const row = document.createElement("button");
    row.type = "button"; row.className = "compact-row";
    row.innerHTML = `<strong>${escapeHTML(conversation.session_id.slice(0, 12))}</strong><span>${escapeHTML(conversation.status)} · ${conversation.message_count} messages · ${conversation.human_takeover ? "Staff" : "AI"}</span>`;
    row.addEventListener("click", () => { state.selectedConversation = conversation; renderConversationMessages(); });
    list.appendChild(row);
  }
  if (!list.children.length) list.textContent = "No conversations match this view.";
}

function renderConversationMessages() {
  const conversation = state.selectedConversation;
  const list = $("conversation-messages");
  list.innerHTML = "";
  for (const message of conversation?.messages || []) {
    const row = document.createElement("div"); row.className = "compact-row";
    row.innerHTML = `<strong>${escapeHTML(message.role)}</strong><span>${escapeHTML(message.content)}</span><small>${escapeHTML(formatDate(message.created_at))}</small>`;
    list.appendChild(row);
  }
  if (!conversation) list.textContent = "Select a conversation.";
  $("toggle-takeover").disabled = !conversation;
  $("close-conversation").disabled = !conversation;
  $("send-staff-response").disabled = !conversation;
  $("toggle-takeover").textContent = conversation?.human_takeover ? "Return to AI" : "Take Over";
}

async function setConversationState(status, humanTakeover) {
  if (!state.selectedConversation) return;
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/conversations/${encodeURIComponent(state.selectedConversation.session_id)}`, { method: "PUT", body: JSON.stringify({ status, human_takeover: humanTakeover }) });
  await loadConversations(); showToast("Conversation updated.");
}

async function sendStaffResponse() {
  const message = $("staff-response").value.trim();
  if (!state.selectedConversation || !message) throw new Error("Enter a staff response.");
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/conversations/${encodeURIComponent(state.selectedConversation.session_id)}/messages`, { method: "POST", body: JSON.stringify({ message }) });
  $("staff-response").value = ""; await loadConversations(); showToast("Staff response sent.");
}

async function loadServiceCatalog() {
  state.catalog = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/service-catalog`);
  const departmentSelect = $("catalog-service-department");
  const requestSelect = $("service-type");
  const requestDepartment = $("service-department");
  departmentSelect.innerHTML = '<option value="">Unassigned</option>';
  requestSelect.innerHTML = '<option value="">Select a configured service</option>';
  requestDepartment.innerHTML = '<option value="">Select a department</option>';
  for (const department of state.catalog.departments) {
    departmentSelect.appendChild(new Option(department.name, department.department_id));
    requestDepartment.appendChild(new Option(department.name, department.name));
  }
  for (const service of state.catalog.services.filter((item) => item.enabled && !item.archived)) {
    requestSelect.appendChild(new Option(service.name, service.service_id));
  }
  renderDepartments();
  renderCatalogServices();
  syncRequestService();
}

function renderDepartments() {
  const list = $("department-list");
  list.innerHTML = "";
  for (const department of state.catalog.departments) {
    const row = document.createElement("div");
    row.className = "compact-row";
    row.innerHTML = `<strong>${escapeHTML(department.name)}</strong><span>${department.enabled ? "Enabled" : "Disabled"} · ${department.default_sla_minutes} min SLA</span>`;
    const edit = document.createElement("button");
    edit.type = "button";
    edit.textContent = "Edit";
    edit.addEventListener("click", () => {
      $("department-id").value = department.department_id;
      $("department-name").value = department.name;
      $("department-sla").value = department.default_sla_minutes;
      $("department-escalation").value = department.escalation_target || "";
      $("department-enabled").checked = department.enabled;
    });
    row.appendChild(edit);
    const remove = document.createElement("button");
    remove.type = "button"; remove.textContent = "Delete";
    remove.addEventListener("click", () => deleteDepartment(department.department_id).catch((error) => showToast(error.message, "error")));
    row.appendChild(remove);
    list.appendChild(row);
  }
  if (!list.children.length) list.textContent = "No departments configured.";
}

async function deleteDepartment(departmentId) {
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/departments/${encodeURIComponent(departmentId)}`, { method: "DELETE" });
  await loadServiceCatalog(); showToast("Department deleted. Existing services are now unassigned.");
}

function renderCatalogServices() {
  const list = $("catalog-service-list");
  list.innerHTML = "";
  for (const service of state.catalog.services) {
    const department = state.catalog.departments.find((item) => item.department_id === service.department_id);
    const row = document.createElement("div");
    row.className = "compact-row";
    row.innerHTML = `<strong>${escapeHTML(service.name)}</strong><span>${escapeHTML(department?.name || "Unassigned")} · ${service.sla_minutes} min · ${service.enabled && !service.archived ? "Enabled" : "Unavailable"}</span>`;
    const actions = document.createElement("div");
    for (const [label, handler] of [
      ["Edit", () => editCatalogService(service)],
      ["Duplicate", () => duplicateCatalogService(service.service_id)],
      [service.archived ? "Delete" : "Archive", () => service.archived ? deleteCatalogService(service.service_id) : archiveCatalogService(service)],
    ]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.addEventListener("click", () => Promise.resolve(handler()).catch((error) => showToast(error.message, "error")));
      actions.appendChild(button);
    }
    row.appendChild(actions);
    list.appendChild(row);
  }
  if (!list.children.length) list.textContent = "No services configured.";
}

function editCatalogService(service) {
  $("catalog-service-id").value = service.service_id;
  $("catalog-service-name").value = service.name;
  $("catalog-service-department").value = service.department_id || "";
  $("catalog-service-keywords").value = (service.keywords || []).join(", ");
  $("catalog-service-description").value = service.description || "";
  $("catalog-service-sla").value = service.sla_minutes;
  $("catalog-service-confirm").checked = service.confirmation_required;
  $("catalog-service-enabled").checked = service.enabled;
}

async function saveDepartment() {
  const name = $("department-name").value.trim();
  if (!name) throw new Error("Department name is required.");
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/departments`, {
    method: "PUT",
    body: JSON.stringify({ data: { department_id: $("department-id").value || undefined, name, default_sla_minutes: Number($("department-sla").value), escalation_target: $("department-escalation").value.trim(), enabled: $("department-enabled").checked } }),
  });
  $("department-id").value = "";
  $("department-name").value = "";
  await loadServiceCatalog();
  showToast("Department saved.");
}

async function saveCatalogService() {
  const name = $("catalog-service-name").value.trim();
  if (!name) throw new Error("Service name is required.");
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/service-catalog`, {
    method: "PUT",
    body: JSON.stringify({ data: {
      service_id: $("catalog-service-id").value || undefined,
      name, department_id: $("catalog-service-department").value || null,
      keywords: $("catalog-service-keywords").value.split(",").map((item) => item.trim()).filter(Boolean),
      description: $("catalog-service-description").value.trim(), sla_minutes: Number($("catalog-service-sla").value),
      confirmation_required: $("catalog-service-confirm").checked, enabled: $("catalog-service-enabled").checked,
    } }),
  });
  $("catalog-service-id").value = "";
  $("catalog-service-name").value = "";
  $("catalog-service-keywords").value = "";
  $("catalog-service-description").value = "";
  await loadServiceCatalog();
  showToast("Service saved.");
}

async function duplicateCatalogService(serviceId) {
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/service-catalog/${encodeURIComponent(serviceId)}/duplicate`, { method: "POST" });
  await loadServiceCatalog();
  showToast("Service duplicated.");
}

async function archiveCatalogService(service) {
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/service-catalog`, { method: "PUT", body: JSON.stringify({ data: { ...service, archived: true, enabled: false } }) });
  await loadServiceCatalog();
  showToast("Service archived.");
}

async function deleteCatalogService(serviceId) {
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/service-catalog/${encodeURIComponent(serviceId)}`, { method: "DELETE" });
  await loadServiceCatalog();
  showToast("Service deleted.");
}

function syncRequestService() {
  const service = state.catalog.services.find((item) => item.service_id === $("service-type").value);
  const department = state.catalog.departments.find((item) => item.department_id === service?.department_id);
  $("service-department").value = department?.name || "";
  if (service) $("service-sla").value = service.sla_minutes;
}

async function loadRecommendations() {
  const data = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/recommendations`);
  state.recommendations = data.recommendations;
  const list = $("recommendation-list");
  list.innerHTML = "";
  for (const recommendation of state.recommendations) {
    const row = document.createElement("div");
    row.className = "compact-row";
    row.innerHTML = `<strong>${escapeHTML(recommendation.name)}</strong><span>${escapeHTML(recommendation.category)} · ${recommendation.enabled ? "Visible" : "Disabled"}</span><span>${escapeHTML(recommendation.address || recommendation.description)}</span>`;
    const edit = document.createElement("button");
    edit.type = "button"; edit.textContent = "Edit"; edit.addEventListener("click", () => editRecommendation(recommendation));
    const remove = document.createElement("button");
    remove.type = "button"; remove.textContent = "Delete"; remove.addEventListener("click", () => deleteRecommendation(recommendation.recommendation_id).catch((error) => showToast(error.message, "error")));
    row.append(edit, remove); list.appendChild(row);
  }
  if (!list.children.length) list.textContent = "No curated recommendations yet.";
}

function editRecommendation(item) {
  $("recommendation-id").value = item.recommendation_id;
  $("recommendation-name").value = item.name;
  $("recommendation-category").value = item.category;
  $("recommendation-address").value = item.address;
  $("recommendation-map-url").value = item.map_url;
  $("recommendation-description").value = item.description;
  $("recommendation-source").value = item.source;
  $("recommendation-enabled").checked = item.enabled;
}

async function saveRecommendation() {
  const name = $("recommendation-name").value.trim();
  if (!name) throw new Error("Recommendation name is required.");
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/recommendations`, { method: "PUT", body: JSON.stringify({ data: {
    recommendation_id: $("recommendation-id").value || undefined, name,
    category: $("recommendation-category").value.trim() || "other", address: $("recommendation-address").value.trim(),
    map_url: $("recommendation-map-url").value.trim(), description: $("recommendation-description").value.trim(),
    source: $("recommendation-source").value.trim() || "property", enabled: $("recommendation-enabled").checked,
  } }) });
  $("recommendation-id").value = ""; $("recommendation-name").value = ""; $("recommendation-description").value = "";
  await loadRecommendations(); showToast("Recommendation saved.");
}

async function deleteRecommendation(recommendationId) {
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/recommendations/${encodeURIComponent(recommendationId)}`, { method: "DELETE" });
  await loadRecommendations(); showToast("Recommendation deleted.");
}

async function loadServiceRequests() {
  await loadServiceCatalog();
  const data = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/hospitality`);
  const list = $("service-request-list");
  list.innerHTML = "";
  for (const request of data.service_requests || []) {
    const row = document.createElement("div");
    row.className = "compact-row";
    const next = nextServiceStatus(request.status);
    row.innerHTML = `
      <strong>${request.request_type} · ${request.room || "no room"}</strong>
      <span>${request.status} · ${request.sla_state} · ${request.department} · ${request.priority}</span>
      <span>${request.description}</span>
    `;
    const controls = document.createElement("div"); controls.className = "request-controls";
    const department = document.createElement("select"); department.setAttribute("aria-label", `Department for ${request.request_id}`);
    department.appendChild(new Option("Unassigned", ""));
    for (const item of state.catalog.departments) department.appendChild(new Option(item.name, item.name));
    department.value = request.department || "";
    const assigned = document.createElement("input"); assigned.placeholder = "Assign to"; assigned.setAttribute("aria-label", `Assignee for ${request.request_id}`); assigned.value = request.assigned_to || "";
    const priority = document.createElement("select"); priority.setAttribute("aria-label", `Priority for ${request.request_id}`);
    for (const value of ["low", "normal", "high", "urgent"]) priority.appendChild(new Option(value[0].toUpperCase() + value.slice(1), value)); priority.value = request.priority;
    const note = document.createElement("input"); note.placeholder = "Add operational note"; note.setAttribute("aria-label", `Note for ${request.request_id}`);
    const save = document.createElement("button"); save.type = "button"; save.textContent = "Save"; save.addEventListener("click", () => updateServiceRequest(request.request_id, { department: department.value, assigned_to: assigned.value, priority: priority.value, note: note.value }).catch((error) => showToast(error.message, "error")));
    controls.append(department, assigned, priority, note, save);
    if (next) { const advance = document.createElement("button"); advance.type = "button"; advance.textContent = `Mark ${next.replaceAll("_", " ")}`; advance.addEventListener("click", () => updateServiceStatus(request.request_id, next)); controls.appendChild(advance); }
    if (request.status !== "completed") { const close = document.createElement("button"); close.type = "button"; close.textContent = "Close"; close.addEventListener("click", () => updateServiceStatus(request.request_id, "completed")); controls.appendChild(close); }
    row.appendChild(controls);
    list.appendChild(row);
  }
  if (!list.children.length) list.textContent = "No service requests yet.";
}

async function updateServiceRequest(requestId, payload) {
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/service-requests/${encodeURIComponent(requestId)}`, { method: "PUT", body: JSON.stringify(payload) });
  await loadServiceRequests(); showToast("Service request details saved.");
}

function nextServiceStatus(status) {
  const order = ["new", "assigned", "accepted", "in_progress", "delivered", "completed"];
  const index = order.indexOf(status);
  return index >= 0 && index < order.length - 1 ? order[index + 1] : null;
}

async function createServiceRequest() {
  if (!$("service-type").value) throw new Error("Select a configured service.");
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/service-requests`, {
    method: "POST",
    body: JSON.stringify({ data: {
      room: $("service-room").value.trim() || null,
      service_id: $("service-type").value,
      description: $("service-description").value.trim(),
      priority: $("service-priority").value,
      sla_target_seconds: Number($("service-sla").value || 15) * 60,
    } }),
  });
  $("service-description").value = "";
  await loadServiceRequests();
  showToast("Service request created.");
}

async function updateServiceStatus(requestId, status) {
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/service-requests/${requestId}/status`, {
    method: "PUT",
    body: JSON.stringify({ status }),
  });
  await loadServiceRequests();
  showToast("Service request updated.");
}

function formatDate(timestamp) {
  if (!timestamp) return "Never";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(timestamp * 1000));
}

function propertyName(propertyId) {
  if (!propertyId) return "All properties";
  return state.properties.find((item) => item.property_id === propertyId)?.hotel_name || propertyId;
}

async function loadPermissions() {
  if (!state.permissions.length) {
    const payload = await jsonFetch("/api/admin/permissions");
    state.permissions = payload.permissions;
  }
  const catalog = $("permission-catalog");
  catalog.innerHTML = state.permissions.map((permission) => `
    <article class="permission-item"><strong>${escapeHTML(permission.key)}</strong><span>${escapeHTML(permission.name)}</span></article>
  `).join("");
  renderRolePermissionSelector([]);
}

async function loadRoles() {
  const payload = await jsonFetch("/api/admin/roles");
  state.roles = payload.roles;
  const select = $("admin-role");
  const current = select.value;
  select.innerHTML = "";
  for (const role of state.roles) {
    if (!can("properties.all") && role.slug === "super-admin") continue;
    select.appendChild(new Option(role.name, role.role_id));
  }
  if (current) select.value = current;
  const list = $("role-list");
  list.innerHTML = "";
  for (const role of state.roles) {
    const row = document.createElement("article");
    row.className = "role-row";
    row.innerHTML = `
      <div><h3>${escapeHTML(role.name)}</h3><p>${escapeHTML(role.description || "Custom permission role")}</p></div>
      <p>${role.permissions.length} permission${role.permissions.length === 1 ? "" : "s"} · ${escapeHTML(role.property_id ? propertyName(role.property_id) : "Platform")}</p>
      <span>${role.user_count || 0} user${role.user_count === 1 ? "" : "s"}</span>
      ${!role.is_system && can("roles.manage") ? '<button type="button">Edit</button>' : '<span>System</span>'}
    `;
    const button = row.querySelector("button");
    if (button) button.addEventListener("click", () => openRoleDialog(role));
    list.appendChild(row);
  }
}

function renderRolePermissionSelector(selected) {
  const target = $("role-permissions");
  if (!target) return;
  target.innerHTML = "";
  for (const permission of state.permissions) {
    const label = document.createElement("label");
    label.innerHTML = `<input type="checkbox" value="${escapeHTML(permission.key)}" ${selected.includes(permission.key) ? "checked" : ""}> <span>${escapeHTML(permission.key)}</span>`;
    label.title = permission.name;
    target.appendChild(label);
  }
}

async function openRoleDialog(role = null) {
  if (!state.permissions.length) await loadPermissions();
  hydratePropertyOptions();
  $("role-id").value = role?.role_id || "";
  $("role-name").value = role?.name || "";
  $("role-description").value = role?.description || "";
  $("role-property").value = role?.property_id || state.auth?.property_id || "";
  $("role-dialog-title").textContent = role ? "Edit Role" : "Create Role";
  $("save-role-button").textContent = role ? "Save Changes" : "Create Role";
  $("role-dialog-message").textContent = "";
  renderRolePermissionSelector(role?.permissions || []);
  $("role-dialog").showModal();
}

async function saveRole(event) {
  event.preventDefault();
  const roleId = $("role-id").value;
  const payload = {
    name: $("role-name").value.trim(),
    description: $("role-description").value.trim(),
    property_id: $("role-property").value || null,
    permissions: [...document.querySelectorAll('#role-permissions input:checked')].map((item) => item.value),
  };
  try {
    await jsonFetch(roleId ? `/api/admin/roles/${encodeURIComponent(roleId)}` : "/api/admin/roles", {
      method: roleId ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    $("role-dialog").close();
    await loadRoles();
    showToast(roleId ? "Role updated." : "Role created.");
  } catch (error) {
    $("role-dialog-message").textContent = error.message;
  }
}

async function loadUsers() {
  if (!state.roles.length && can("roles.view")) await loadRoles();
  const payload = await jsonFetch("/api/admin/users");
  state.users = payload.users;
  renderUsers();
}

function renderUsers() {
  const query = $("user-search").value.trim().toLowerCase();
  const status = $("user-status-filter").value;
  const users = state.users.filter((user) => {
    const matchesQuery = !query || user.username.toLowerCase().includes(query) || user.display_name.toLowerCase().includes(query);
    return matchesQuery && (!status || user.status === status);
  });
  $("user-count").textContent = `${users.length} user${users.length === 1 ? "" : "s"}`;
  $("users-empty").hidden = users.length > 0;
  const body = $("users-table-body");
  body.innerHTML = "";
  for (const user of users) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><div class="user-cell"><strong>@${escapeHTML(user.username)}</strong><span>${escapeHTML(user.email || "No recovery email")}</span></div></td>
      <td>${escapeHTML(user.display_name)}</td>
      <td>${escapeHTML(propertyName(user.property_id))}</td>
      <td>${escapeHTML(user.role)}</td>
      <td><span class="status-label ${escapeHTML(user.status)}">${escapeHTML(user.status)}</span></td>
      <td>${escapeHTML(formatDate(user.last_login))}</td>
      <td>${escapeHTML(formatDate(user.created))}</td>
      <td><div class="row-actions"></div></td>
    `;
    const actions = row.querySelector(".row-actions");
    if (can("users.edit")) {
      const edit = document.createElement("button");
      edit.type = "button";
      edit.textContent = "Edit";
      edit.addEventListener("click", () => openUserDialog(user));
      actions.appendChild(edit);
      const more = document.createElement("button");
      more.type = "button";
      more.textContent = "Actions";
      more.addEventListener("click", (event) => openUserActions(user, event.currentTarget));
      actions.appendChild(more);
    }
    body.appendChild(row);
  }
}

async function openUserDialog(user = null) {
  if (!state.roles.length) await loadRoles();
  hydratePropertyOptions();
  const creating = !user;
  $("user-id").value = user?.id || "";
  $("admin-username").value = user?.username || "";
  $("admin-username").disabled = !creating;
  $("admin-display-name").value = user?.display_name || "";
  $("admin-property").value = user?.property_id || state.auth?.property_id || state.properties[0]?.property_id || "";
  $("admin-role").value = user?.role_id || state.roles.find((role) => role.slug === "viewer-auditor")?.role_id || state.roles[0]?.role_id || "";
  $("admin-email").value = user?.email || "";
  $("admin-status").value = user?.status || "active";
  $("admin-status").querySelector('option[value="locked"]').hidden = creating;
  $("admin-password").value = "";
  $("admin-password-confirm").value = "";
  $("admin-force-password").checked = true;
  for (const field of document.querySelectorAll(".create-password-field")) field.hidden = !creating;
  $("user-dialog-title").textContent = creating ? "Create User" : "Edit User";
  $("save-user-button").textContent = creating ? "Create User" : "Save Changes";
  $("user-dialog-message").textContent = "";
  $("user-dialog").showModal();
}

async function saveUser(event) {
  event.preventDefault();
  const userId = $("user-id").value;
  const creating = !userId;
  const payload = {
    display_name: $("admin-display-name").value.trim(),
    property_id: $("admin-property").value || null,
    role_id: $("admin-role").value,
    email: $("admin-email").value.trim() || null,
    status: $("admin-status").value,
  };
  if (creating) {
    if ($("admin-password").value !== $("admin-password-confirm").value) {
      $("user-dialog-message").textContent = "Passwords do not match.";
      return;
    }
    Object.assign(payload, {
      username: $("admin-username").value.trim(),
      password: $("admin-password").value,
      force_password_change: $("admin-force-password").checked,
    });
  }
  try {
    await jsonFetch(creating ? "/api/admin/users" : `/api/admin/users/${encodeURIComponent(userId)}`, {
      method: creating ? "POST" : "PUT",
      body: JSON.stringify(payload),
    });
    $("user-dialog").close();
    await loadUsers();
    showToast(creating ? "User created." : "User updated.");
  } catch (error) {
    $("user-dialog-message").textContent = error.message;
  }
}

function openUserActions(user, anchor) {
  const menu = $("user-action-menu");
  const actions = [
    ["Edit User", () => openUserDialog(user)],
    ["Change Role / Property", () => openUserDialog(user)],
    ["Reset Password", () => openPasswordReset(user)],
    [user.status === "locked" ? "Unlock Account" : user.status === "disabled" ? "Enable Account" : "Disable Account", () => toggleUserStatus(user, user.status !== "active")],
    ["Revoke Sessions", () => revokeUserSessions(user)],
    ["View Activity", () => viewUserActivity(user)],
  ];
  if (can("users.delete") && user.id !== state.auth.id) actions.push(["Delete User", () => deleteUser(user), "danger"]);
  menu.innerHTML = `<strong>@${escapeHTML(user.username)}</strong>`;
  for (const [label, handler, className] of actions) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    if (className) button.className = className;
    button.addEventListener("click", () => {
      menu.hidden = true;
      handler();
    });
    menu.appendChild(button);
  }
  const rect = anchor.getBoundingClientRect();
  menu.style.top = `${Math.min(window.innerHeight - 280, rect.bottom + 5)}px`;
  menu.style.left = `${Math.max(8, Math.min(window.innerWidth - 210, rect.right - 200))}px`;
  menu.hidden = false;
}

function openPasswordReset(user) {
  $("password-reset-user-id").value = user.id;
  $("password-reset-user").textContent = `Create a temporary password for @${user.username}. All active sessions will be revoked.`;
  $("password-reset-value").value = "";
  $("password-reset-confirm").value = "";
  $("password-reset-message").textContent = "";
  $("password-reset-dialog").showModal();
}

async function resetUserPassword(event) {
  event.preventDefault();
  const value = $("password-reset-value").value;
  if (value !== $("password-reset-confirm").value) {
    $("password-reset-message").textContent = "Passwords do not match.";
    return;
  }
  try {
    await jsonFetch(`/api/admin/users/${encodeURIComponent($("password-reset-user-id").value)}/reset-password`, {
      method: "POST",
      body: JSON.stringify({ password: value, force_password_change: $("password-reset-force").checked }),
    });
    $("password-reset-dialog").close();
    await loadUsers();
    showToast("Temporary password created and sessions revoked.");
  } catch (error) {
    $("password-reset-message").textContent = error.message;
  }
}

async function toggleUserStatus(user, enable) {
  await jsonFetch(`/api/admin/users/${encodeURIComponent(user.id)}`, {
    method: "PUT",
    body: JSON.stringify({ status: enable ? "active" : "disabled" }),
  });
  await loadUsers();
  showToast(enable ? "Account enabled." : "Account disabled and sessions revoked.");
}

async function revokeUserSessions(user) {
  await jsonFetch(`/api/admin/users/${encodeURIComponent(user.id)}/revoke-sessions`, { method: "POST" });
  await loadUsers();
  showToast("Active sessions revoked.");
}

function viewUserActivity(user) {
  $("audit-username").value = user.username;
  activatePanel("audit");
}

async function deleteUser(user) {
  if (!window.confirm(`Delete @${user.username}? This cannot be undone.`)) return;
  await jsonFetch(`/api/admin/users/${encodeURIComponent(user.id)}`, { method: "DELETE" });
  await loadUsers();
  showToast("User deleted.");
}

async function loadAudit() {
  hydratePropertyOptions();
  const params = new URLSearchParams();
  if ($("audit-username").value.trim()) params.set("username", $("audit-username").value.trim());
  if ($("audit-property").value) params.set("property_id", $("audit-property").value);
  if ($("audit-action").value.trim()) params.set("action", $("audit-action").value.trim());
  if ($("audit-resource").value.trim()) params.set("resource", $("audit-resource").value.trim());
  if ($("audit-date").value) {
    const start = new Date(`${$("audit-date").value}T00:00:00`);
    params.set("start_at", String(Math.floor(start.getTime() / 1000)));
    params.set("end_at", String(Math.floor((start.getTime() + 86400000 - 1) / 1000)));
  }
  const payload = await jsonFetch(`/api/admin/audit?${params.toString()}`);
  const body = $("audit-table-body");
  body.innerHTML = "";
  $("audit-empty").hidden = payload.events.length > 0;
  for (const event of payload.events) {
    const row = document.createElement("tr");
    row.innerHTML = `<td>${escapeHTML(formatDate(event.timestamp))}</td><td><div class="user-cell"><strong>${escapeHTML(event.display_name || "System")}</strong><span>${event.username ? `@${escapeHTML(event.username)}` : "Unauthenticated"}</span></div></td><td>${escapeHTML(event.role || "—")}</td><td>${escapeHTML(propertyName(event.property_id))}</td><td>${escapeHTML(event.action)}</td><td>${escapeHTML(event.resource)}${event.resource_id ? `<br><small>${escapeHTML(event.resource_id)}</small>` : ""}</td><td>${escapeHTML(event.ip_address || "—")}</td>`;
    body.appendChild(row);
  }
}

async function changePassword(event) {
  event.preventDefault();
  const form = event.currentTarget;
  if ($("new-password").value !== $("confirm-new-password").value) {
    showToast("New passwords do not match.", "error");
    return;
  }
  await jsonFetch("/api/admin/auth/change-password", {
    method: "POST",
    body: JSON.stringify({ current_password: $("current-password").value, new_password: $("new-password").value }),
  });
  form.reset();
  state.auth.force_password_change = false;
  showToast("Password changed. Other sessions were revoked.");
}

async function logout() {
  await jsonFetch("/api/admin/auth/logout", { method: "POST" });
  window.location.assign("/admin/login");
}

function normalizeColor(value) {
  return /^#[0-9a-f]{6}$/i.test(value) ? value : "#18181b";
}

function setup() {
  for (const icon of document.querySelectorAll(".nav-icon")) icon.setAttribute("aria-hidden", "true");
  for (const item of document.querySelectorAll(".nav-item")) {
    item.addEventListener("click", () => activatePanel(item.dataset.panel));
  }
  if (!window.matchMedia("(max-width: 620px)").matches && localStorage.getItem("concierge.admin.sidebar") === "collapsed") {
    document.querySelector(".platform-shell").classList.add("sidebar-collapsed");
  }
  $("sidebar-toggle").addEventListener("click", () => {
    if (window.matchMedia("(max-width: 620px)").matches) {
      const open = document.querySelector(".platform-shell").classList.toggle("mobile-nav-open");
      $("sidebar-toggle").setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
      return;
    }
    const collapsed = document.querySelector(".platform-shell").classList.toggle("sidebar-collapsed");
    localStorage.setItem("concierge.admin.sidebar", collapsed ? "collapsed" : "expanded");
    $("sidebar-toggle").setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
  });
  for (const target of document.querySelectorAll("[data-dashboard-panel]")) target.addEventListener("click", () => activatePanel(target.dataset.dashboardPanel));
  $("property-switcher").addEventListener("change", (event) => switchProperty(event.target.value).catch((error) => showToast(error.message, "error")));
  $("profile-button").addEventListener("click", () => {
    const menu = $("profile-menu");
    menu.hidden = !menu.hidden;
    $("profile-button").setAttribute("aria-expanded", String(!menu.hidden));
  });
  for (const button of document.querySelectorAll("[data-profile-panel]")) {
    button.addEventListener("click", () => {
      $("profile-menu").hidden = true;
      activatePanel(button.dataset.profilePanel);
    });
  }
  $("profile-switch-property").addEventListener("click", () => {
    $("profile-menu").hidden = true;
    $("property-switcher").focus();
  });
  $("logout-button").addEventListener("click", () => logout().catch((error) => showToast(error.message, "error")));
  $("create-user-button").addEventListener("click", () => openUserDialog().catch((error) => showToast(error.message, "error")));
  $("user-form").addEventListener("submit", saveUser);
  $("user-search").addEventListener("input", renderUsers);
  $("user-status-filter").addEventListener("change", renderUsers);
  $("create-role-button").addEventListener("click", () => openRoleDialog().catch((error) => showToast(error.message, "error")));
  $("role-form").addEventListener("submit", saveRole);
  $("password-reset-form").addEventListener("submit", resetUserPassword);
  $("change-password-form").addEventListener("submit", (event) => changePassword(event).catch((error) => showToast(error.message, "error")));
  $("refresh-audit").addEventListener("click", () => loadAudit().catch((error) => showToast(error.message, "error")));
  $("apply-audit-filters").addEventListener("click", () => loadAudit().catch((error) => showToast(error.message, "error")));
  for (const button of document.querySelectorAll("[data-close-dialog]")) {
    button.addEventListener("click", () => $(button.dataset.closeDialog).close());
  }
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".profile-shell")) {
      $("profile-menu").hidden = true;
      $("profile-button").setAttribute("aria-expanded", "false");
    }
    if (!event.target.closest("#user-action-menu") && !event.target.closest(".row-actions")) $("user-action-menu").hidden = true;
  });

  const liveInputs = [
    "design-hotel-name",
    "design-concierge-name",
    "logo-display-input",
    "greeting-input",
    "welcome-input",
    "composer-placeholder-input",
    "background-input",
    "surface-input",
    "text-color-input",
    "secondary-text-color-input",
    "accent-input",
    "user-message-input",
    "button-color-input",
    "composer-background-input",
    "background-overlay-input",
    "font-input",
    "base-font-size-input",
    "density-input",
    "content-width-input",
    "message-width-input",
    "composer-width-input",
    "message-spacing-input",
    "radius-input",
    "suggestion-layout-input",
    "user-style-input",
    "assistant-style-input",
    "header-enabled-input",
    "show-logo-input",
    "show-name-input",
    "show-concierge-input",
  ];
  for (const id of liveInputs) {
    $(id).addEventListener("input", updatePreview);
    $(id).addEventListener("change", updatePreview);
  }
  $("logo-upload-input").addEventListener("change", (event) => {
    handleImageUpload(event.target, "logo-url-input", {
      maxBytes: 500 * 1024,
      recommended: "Recommended logo: 512 x 512 px or 800 x 240 px, under 500 KB.",
    });
  });
  $("background-image-input").addEventListener("change", (event) => {
    handleImageUpload(event.target, "background-image-url-input", {
      maxBytes: 1536 * 1024,
      recommended: "Recommended background: 1600 x 2400 px portrait or 2400 x 1600 px landscape, under 1.5 MB.",
    });
  });

  $("hotel-name-input").addEventListener("input", (event) => {
    $("design-hotel-name").value = event.target.value;
    $("overview-title").textContent = event.target.value || "Property";
    updatePreview();
  });
  $("concierge-name-input").addEventListener("input", (event) => {
    $("design-concierge-name").value = event.target.value;
    updatePreview();
  });
  $("add-prompt").addEventListener("click", () => {
    addPromptRow();
    updatePreview();
  });
  $("save-draft").addEventListener("click", () => saveDraft().catch((error) => showToast(error.message, "error")));
  $("publish-design").addEventListener("click", () => publishDesign().catch((error) => showToast(error.message, "error")));
  $("discard-design").addEventListener("click", () => discardDesign().catch((error) => showToast(error.message, "error")));
  $("ai-default-provider").addEventListener("change", handleDefaultProviderChange);
  $("ai-local-only").addEventListener("change", handleLocalOnlyChange);
  $("save-ai-settings").addEventListener("click", () => saveAISettings().catch((error) => showToast(error.message, "error")));
  $("close-provider-drawer").addEventListener("click", closeProviderDrawer);
  $("provider-drawer-backdrop").addEventListener("click", closeProviderDrawer);
  for (const id of [
    "drawer-auth-method",
    "drawer-model",
    "drawer-endpoint",
    "drawer-temperature",
    "drawer-max-tokens",
    "drawer-timeout",
    "drawer-enabled",
  ]) {
    $(id).addEventListener("input", markProviderDirty);
    $(id).addEventListener("change", markProviderDirty);
  }
  $("save-provider").addEventListener("click", () => saveProvider().catch((error) => showToast(error.message, "error")));
  $("save-provider-secret").addEventListener("click", () => saveProviderSecret().catch((error) => showToast(error.message, "error")));
  $("remove-provider-secret").addEventListener("click", () => removeProviderSecret().catch((error) => showToast(error.message, "error")));
  $("refresh-provider-models").addEventListener("click", () => refreshProviderModels().catch((error) => showToast(error.message, "error")));
  $("test-provider").addEventListener("click", () => testProvider().catch((error) => showToast(error.message, "error")));
  $("loop-provider").addEventListener("change", () => loopModelOptions());
  $("loop-save").addEventListener("click", () => saveImprovementLoop().catch((error) => showToast(error.message, "error")));
  $("loop-run-once").addEventListener("click", () => runImprovementLoopOnce().catch((error) => showToast(error.message, "error")));
  $("loop-start").addEventListener("click", () => startImprovementLoop().catch((error) => showToast(error.message, "error")));
  $("loop-pause").addEventListener("click", () => improvementLoopAction("pause", "Improvement loop paused.").catch((error) => showToast(error.message, "error")));
  $("loop-resume").addEventListener("click", () => startImprovementLoop("resume").catch((error) => showToast(error.message, "error")));
  $("loop-stop").addEventListener("click", () => improvementLoopAction("stop", "Improvement loop stopped.").catch((error) => showToast(error.message, "error")));
  $("loop-satisfied").addEventListener("click", () => improvementLoopAction("satisfied", "Loop marked satisfied by operator.").catch((error) => showToast(error.message, "error")));
  $("loop-approve").addEventListener("click", () => decideImprovementLoop("approved").catch((error) => showToast(error.message, "error")));
  $("loop-revise").addEventListener("click", () => decideImprovementLoop("revision_requested").catch((error) => showToast(error.message, "error")));

  for (const button of document.querySelectorAll("[data-map-tool]")) {
    button.addEventListener("click", () => {
      state.mapTool = button.dataset.mapTool;
      for (const candidate of document.querySelectorAll("[data-map-tool]")) candidate.classList.toggle("active", candidate === button);
    });
  }
  $("floor-map-canvas").addEventListener("pointerdown", handleCanvasPointer);
  $("floor-map-canvas").addEventListener("pointermove", handleCanvasPointerMove);
  $("floor-map-canvas").addEventListener("pointerup", finishFreeform);
  $("floor-map-canvas").addEventListener("pointercancel", finishFreeform);
  $("save-map-object").addEventListener("click", () => saveMapObject().catch((error) => showToast(error.message, "error")));
  $("delete-map-object").addEventListener("click", () => {
    state.mapHistory.push(structuredClone(state.mapObjects));
    state.mapObjects.pop();
    renderMapCanvas();
  });
  $("duplicate-map-object").addEventListener("click", () => {
    const last = state.mapObjects.at(-1);
    if (last) state.mapObjects.push(structuredClone(last));
    renderMapCanvas();
  });
  $("undo-map").addEventListener("click", () => {
    const previous = state.mapHistory.pop();
    if (previous) {
      state.mapRedo.push(structuredClone(state.mapObjects));
      state.mapObjects = previous;
      renderMapCanvas();
    }
  });
  $("redo-map").addEventListener("click", () => {
    const next = state.mapRedo.pop();
    if (next) {
      state.mapHistory.push(structuredClone(state.mapObjects));
      state.mapObjects = next;
      renderMapCanvas();
    }
  });
  for (const input of document.querySelectorAll(".layer-toggle")) input.addEventListener("change", renderMapCanvas);
  $("zone-building-select").addEventListener("change", hydrateZoneSelectors);
  $("zone-floor-select").addEventListener("change", renderMapCanvas);
  $("floor-map-upload").addEventListener("change", (event) => uploadFloorMap(event.target.files?.[0]).catch((error) => showToast(error.message, "error")));
  $("create-stay-session").addEventListener("click", () => createStaySession().catch((error) => showToast(error.message, "error")));
  $("save-stay-memory").addEventListener("click", () => saveStayMemory().catch((error) => showToast(error.message, "error")));
  $("record-observation").addEventListener("click", () => recordObservation().catch((error) => showToast(error.message, "error")));
  $("load-location-report").addEventListener("click", () => loadLocationReport().catch((error) => showToast(error.message, "error")));
  $("create-service-request").addEventListener("click", () => createServiceRequest().catch((error) => showToast(error.message, "error")));
  $("service-type").addEventListener("change", syncRequestService);
  $("save-department").addEventListener("click", () => saveDepartment().catch((error) => showToast(error.message, "error")));
  $("save-catalog-service").addEventListener("click", () => saveCatalogService().catch((error) => showToast(error.message, "error")));
  $("save-recommendation").addEventListener("click", () => saveRecommendation().catch((error) => showToast(error.message, "error")));
  $("refresh-conversations").addEventListener("click", () => loadConversations().catch((error) => showToast(error.message, "error")));
  $("save-conversation-retention").addEventListener("click", () => saveConversationRetention().catch((error) => showToast(error.message, "error")));
  $("conversation-search").addEventListener("input", renderConversations);
  $("conversation-status-filter").addEventListener("change", renderConversations);
  $("toggle-takeover").addEventListener("click", () => setConversationState("open", !state.selectedConversation?.human_takeover).catch((error) => showToast(error.message, "error")));
  $("close-conversation").addEventListener("click", () => setConversationState("closed", false).catch((error) => showToast(error.message, "error")));
  $("send-staff-response").addEventListener("click", () => sendStaffResponse().catch((error) => showToast(error.message, "error")));
  for (const id of ["intro-mode", "intro-preset", "intro-duration", "intro-message", "intro-background", "intro-brand-color", "intro-first-visit", "intro-skip"]) {
    $(id).addEventListener("input", updateIntroPreview);
    $(id).addEventListener("change", updateIntroPreview);
  }
  $("save-intro").addEventListener("click", () => saveIntro().catch((error) => showToast(error.message, "error")));
  $("intro-upload").addEventListener("change", (event) => uploadIntroAsset(event.target.files?.[0]).catch((error) => showToast(error.message, "error")));
  $("save-hotel-information").addEventListener("click", () => saveHotelInformation().catch((error) => showToast(error.message, "error")));
  $("clear-hotel-information").addEventListener("click", () => { for (const id of ["hotel-info-description", "hotel-info-address", "hotel-info-phone", "hotel-info-email", "hotel-info-website", "hotel-info-checkin", "hotel-info-checkout", "hotel-info-breakfast", "hotel-info-wifi", "hotel-info-policies"]) $(id).value = ""; });
  $("save-room").addEventListener("click", () => saveRoom().catch((error) => showToast(error.message, "error")));
  $("save-guest-module").addEventListener("click", () => saveGuestModule().catch((error) => showToast(error.message, "error")));
  $("save-facility").addEventListener("click", () => saveFacility().catch((error) => showToast(error.message, "error")));
  $("save-restaurant").addEventListener("click", () => saveRestaurant().catch((error) => showToast(error.message, "error")));
  $("ai-usage-period").addEventListener("change", () => loadAIUsage().catch((error) => showToast(error.message, "error")));
  $("test-antlabs").addEventListener("click", () => testAntlabs().catch((error) => showToast(error.message, "error")));
  $("save-knowledge").addEventListener("click", () => saveKnowledgeEntry().catch((error) => showToast(error.message, "error")));
  $("save-faq").addEventListener("click", () => saveFAQ().catch((error) => showToast(error.message, "error")));
  $("knowledge-document-upload").addEventListener("change", (event) => uploadKnowledgeDocument(event.target.files?.[0]).catch((error) => showToast(error.message, "error")));
  $("save-personality").addEventListener("click", () => savePersonality().catch((error) => showToast(error.message, "error")));
  $("save-guardrails").addEventListener("click", () => saveGuardrails().catch((error) => showToast(error.message, "error")));
  $("save-webhook").addEventListener("click", () => saveWebhook().catch((error) => showToast(error.message, "error")));
  $("save-location").addEventListener("click", () => saveManagedLocation().catch((error) => showToast(error.message, "error")));
  $("save-deployment").addEventListener("click", () => saveDeploymentSettings().catch((error) => showToast(error.message, "error")));
  $("save-network").addEventListener("click", () => saveDeploymentSettings().catch((error) => showToast(error.message, "error")));
  $("verify-deployment").addEventListener("click", () => verifyDeployment().catch((error) => showToast(error.message, "error")));
  $("save-app-settings").addEventListener("click", () => saveApplicationSettings().catch((error) => showToast(error.message, "error")));
  $("save-smtp").addEventListener("click", () => saveSMTPSettings().catch((error) => showToast(error.message, "error")));
  $("test-smtp").addEventListener("click", () => testSMTP().catch((error) => showToast(error.message, "error")));

  for (const button of document.querySelectorAll(".preview-size")) {
    button.addEventListener("click", () => {
      for (const candidate of document.querySelectorAll(".preview-size")) {
        candidate.classList.toggle("active", candidate === button);
      }
      $("chat-preview").className = "phone-preview " + button.dataset.size;
    });
  }
}

document.body.dataset.adminReady = "false";
const platformShell = document.querySelector(".platform-shell");
if (platformShell) platformShell.inert = true;
setup();
async function initializeAdmin() {
  await loadCurrentAdmin();
  await loadProperty();
  document.body.dataset.adminReady = "true";
  if (platformShell) platformShell.inert = false;
}
initializeAdmin().catch((error) => {
  document.body.dataset.adminReady = "error";
  if (platformShell) platformShell.inert = false;
  showToast(error.message, "error");
});
window.setInterval(() => {
  if (!$("improvement-loop").classList.contains("active")) return;
  if (!["running", "awaiting_approval"].includes(state.improvementLoop?.loop?.status)) return;
  loadImprovementLoop(true).catch((error) => showToast(error.message, "error"));
}, 2500);
