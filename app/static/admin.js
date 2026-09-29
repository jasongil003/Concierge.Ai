const state = {
  auth: null,
  authSavedSnapshot: null,
  authSaving: false,
  properties: [],
  users: [],
  roles: [],
  permissions: [],
  property: null,
  designDraft: null,
  designPublished: null,
  versions: [],
  ai: null,
  personalizationPolicy: null,
  improvementLoop: null,
  activeProvider: null,
  providerDirty: false,
  zones: null,
  mapTool: "select",
  mapObjects: [],
  selectedMapObject: null,
  mapHistory: [],
  mapRedo: [],
  mapZoom: 1,
  mapPointer: null,
  mapPolygonPoints: [],
  mapConnectFrom: null,
  designDevice: "mobile",
  designZoom: 1,
  designAccentText: "#ffffff",
  introDirty: false,
  introPreviewTimer: null,
  mapStructureMode: "building",
  mapPropertyId: "",
  mapSelectedFloorId: "",
  mapSelectedBuildingId: "",
  mapDirty: false,
  intro: null,
  catalog: { departments: [], services: [] },
  serviceRequests: [],
  guestSessions: [],
  conversations: [],
  selectedConversation: null,
  guestSessionLinks: [],
  guestStays: [],
  guestDevices: [],
  recommendations: [],
  hospitality: null,
  restaurantMenus: [],
  restaurantPromotions: [],
  restaurantAnalytics: null,
  mapBackgrounds: new Map(),
  knowledge: { items: [], documents: [], faqs: [] },
  managedKnowledge: { items: [], sources: [], categories: [] },
  knowledgeHealth: null,
  hotelAIFiles: [],
  hotelAISubmitting: false,
  webhooks: { webhooks: [], deliveries: [] },
  deployment: null,
  operations: null,
  operationsPeriod: "24h",
  operationsStart: null,
  operationsEnd: null,
  assistantConversationId: null,
  assistantConversations: [],
  assistantMode: "auto",
};

const INTRO_TEMPLATES = {
  quiet_luxury: { mode: "generate_from_logo", preset: "luxury_reveal", duration_ms: 2400, background: "#f4f0e8", brand_color: "#27352e", welcome_message: "Welcome to a more considered stay." },
  city_boutique: { mode: "generate_from_logo", preset: "minimal_fade", duration_ms: 1300, background: "#f3f6fa", brand_color: "#20304a", welcome_message: "Your city stay, made simple." },
  warm_welcome: { mode: "generate_from_logo", preset: "fade_scale", duration_ms: 1800, background: "#fff6ed", brand_color: "#70452f", welcome_message: "We're glad you're here." },
  coastal_retreat: { mode: "generate_from_logo", preset: "logo_to_chat_header", duration_ms: 1900, background: "#eff8f7", brand_color: "#1e5d61", welcome_message: "Take a breath. You're right where you need to be." },
};
let restaurantAssignmentRequestId = 0;

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
  partial: { label: "Partial", className: "partial" },
  coming_soon: { label: "Coming Soon", className: "soon" },
  configuration_required: { label: "Configuration Required", className: "required" },
};

const NAV_SECTIONS = [
  {
    title: "Operations",
    open: true,
    items: [
      { id: "dashboard", label: "Dashboard", panel: "overview", permission: "dashboard.view", icon: "⌂" },
      { id: "guest-requests", label: "Guest Requests", panel: "requests", permission: "requests.view", icon: "☷" },
      { id: "guest-sessions", label: "Guest Sessions", panel: "sessions", permission: "guest_sessions.view", icon: "◎" },
      { id: "alerts", label: "Alerts", panel: "alerts", permission: "dashboard.view", icon: "!" },
    ],
  },
  {
    title: "Guest Experience",
    items: [
      { id: "conversations", label: "Conversations", panel: "conversations", permission: "conversations.view", icon: "◫" },
      { id: "personalization", label: "Personalization", panel: "personalization-settings", permission: "properties.view", icon: "✧" },
      { id: "guest-preview", label: "Conversation Modules", panel: "guest", permission: "concierge.view", icon: "◫" },
      { id: "recommendations", label: "Recommendations", panel: "recommendations", permission: "properties.view", icon: "✦" },
      { id: "location", label: "Location", panel: "location", permission: "analytics.view", icon: "⌖" },
    ],
  },
  {
    title: "Property",
    items: [
      { id: "hotel-information", label: "Hotel Information", panel: "hotel-information", permission: "properties.view", icon: "□" },
      { id: "rooms", label: "Rooms", panel: "rooms", permission: "properties.view", icon: "▤" },
      { id: "facilities", label: "Facilities", panel: "facilities", permission: "properties.view", icon: "◇" },
      { id: "restaurants", label: "Restaurants", panel: "restaurants", permission: "restaurant.view", icon: "○" },
      { id: "service-catalog", label: "Service Catalog", panel: "service-catalog", permission: "requests.view", icon: "＋" },
      { id: "zones-maps", label: "Zones & Maps", panel: "zones", permission: "properties.view", icon: "⌗" },
      { id: "appearance", label: "Design", panel: "appearance", permission: "concierge.view", icon: "◐" },
      { id: "branding-intro", label: "Branding / Intro", panel: "intro", permission: "concierge.view", icon: "A" },
    ],
  },
  {
    title: "Intelligence",
    items: [
      { id: "analytics", label: "Analytics", panel: "analytics", permission: "analytics.view", icon: "▥" },
      { id: "reports", label: "Reports", panel: "reports", permission: "reports.export", icon: "▧" },
      { id: "ai-assistant", label: "AI Assistant", panel: "ai-assistant", permission: "assistant.use", icon: "✦" },
      { id: "knowledge", label: "Knowledge", panel: "knowledge", permission: "knowledge.view", icon: "▣" },
      { id: "documents", label: "Documents", panel: "documents", permission: "knowledge.view", icon: "▧" },
      { id: "faqs", label: "FAQs", panel: "faqs", permission: "knowledge.view", icon: "?" },
      { id: "personality", label: "Personality", panel: "ai-personality", permission: "ai.view", icon: "A" },
      { id: "guardrails", label: "Guardrails", panel: "guardrails", permission: "security.view", icon: "⊡" },
      { id: "ai-usage", label: "Usage", panel: "ai-usage", permission: "analytics.view", icon: "◫" },
      { id: "questions", label: "Guest Questions", panel: "questions", permission: "analytics.view", icon: "?" },
      { id: "request-analytics", label: "Request Analytics", panel: "request-analytics", permission: "analytics.view", icon: "▥" },
    ],
  },
  {
    title: "Platform",
    items: [
      { id: "system-health", label: "System Health", panel: "system-health", permission: "infrastructure.view", icon: "◉" },
      { id: "models-providers", label: "Models & Providers", panel: "ai", permission: "ai.view", icon: "◈" },
      { id: "integrations", label: "Integrations", panel: "third-party", permission: "integrations.view", icon: "⌁" },
      { id: "antlabs-wifi", label: "ANTlabs / Wi-Fi", panel: "wifi", permission: "integrations.view", icon: "⌁" },
      { id: "auth-types", label: "Authentication Types", panel: "auth-types", permission: "integrations.view", icon: "✓" },
      { id: "webhooks", label: "Webhooks", panel: "webhooks", permission: "integrations.view", icon: "↗" },
      { id: "audit", label: "Audit Logs", panel: "audit", permission: "audit.view", icon: "☷" },
      { id: "users", label: "Users", panel: "users", permission: "users.view", icon: "◎" },
      { id: "roles", label: "Roles", panel: "roles", permission: "roles.view", icon: "◇" },
      { id: "permissions", label: "Permissions", panel: "permissions", permission: "roles.view", icon: "✓" },
      { id: "security", label: "Security", panel: "security", permission: "security.view", icon: "⊡" },
      { id: "settings", label: "Settings", panel: "system-settings", permission: "system.configure", icon: "⌘", superAdminOnly: true },
      { id: "api", label: "API", panel: "api", permission: "integrations.view", icon: "⌁" },
    ],
  },
  {
    title: "Deployment",
    items: [
      { id: "network-access", label: "Network Access", panel: "network-access", permission: "network.view", icon: "⌁" },
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
  if (!response.ok) {
    const detail = data.detail;
    const error = new Error(typeof detail === "string" ? detail : (detail?.warnings || ["Request failed"]).join(" "));
    if (detail && typeof detail === "object") {
      error.code = detail.code;
      error.confirmations = detail.confirmations || [];
      error.warnings = detail.warnings || [];
    }
    throw error;
  }
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
  applyAssistantPermissionVisibility();
}

function applyAssistantPermissionVisibility() {
  const reportAllowed = ["reports.export", "analytics.view", "restaurant.analytics.view"].some(can);
  const attachButton = $("assistant-attach");
  if (attachButton) attachButton.hidden = !((can("knowledge.edit") && can("knowledge.view")) || can("restaurant.menu.edit"));
  for (const element of document.querySelectorAll("[data-assistant-mode='knowledge'], [data-assistant-suggestion][data-assistant-mode='knowledge']")) {
    element.hidden = !can("knowledge.view");
  }
  for (const element of document.querySelectorAll("[data-assistant-mode='health'], [data-assistant-suggestion][data-assistant-mode='health']")) {
    element.hidden = !can("diagnostics.view");
  }
  for (const element of document.querySelectorAll("[data-assistant-mode='report'], [data-assistant-suggestion][data-assistant-mode='report']")) {
    element.hidden = !reportAllowed;
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
    if (section.title === "Overview") {
      for (const item of visibleItems) nav.appendChild(createNavButton(item));
      continue;
    }
    const group = document.createElement("details");
    group.className = "nav-group";
    group.open = Boolean(section.open);
    const summary = document.createElement("summary");
    summary.innerHTML = `<span class="nav-label">${escapeHTML(section.title)}</span>`;
    group.appendChild(summary);
    if (section.description) {
      const description = document.createElement("p");
      description.className = "nav-group-description";
      description.textContent = section.description;
      group.appendChild(description);
    }
    for (const item of visibleItems) group.appendChild(createNavButton(item));
    nav.appendChild(group);
  }
}

function createNavButton(item) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "nav-item";
  button.dataset.navId = item.id;
  button.dataset.panel = item.panel;
  button.dataset.permission = item.permission;
  button.title = item.label;
  button.innerHTML = `
    <span class="nav-icon" aria-hidden="true">${escapeHTML(item.icon || "•")}</span>
    <span class="nav-label">${escapeHTML(item.label)}</span>
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

const PAGE_COMMENTS = {
  "property-onboarding": [
    "Set up the first property workspace so its guest experience, services, dining, rooms, and knowledge can be configured.",
    ["Enter the official property name and a unique Property ID.", "Choose the property's time zone and enter its address.", "Create the property, then add verified information in the Property pages before guests use the concierge."],
    "The Property ID is used in URLs and records; choose it carefully. A property stays empty until its operational details are added."
  ],
  overview: [
    "Give managers and administrators a quick view of property activity, service demand, and system signals for the selected period.",
    ["Choose a timeframe at the top of the page.", "Review the health banner, metric cards, alert list, and department demand.", "Open System Health, Alerts, or Analytics from the related action when a card needs investigation."],
    "Counts and charts reflect recorded activity in the selected property and period; an empty chart means there is not enough recorded history."
  ],
  "system-health": [
    "Review application, database, provider, and host checks to see what is available and what needs attention.",
    ["Select a timeframe.", "Open each component to inspect its state, last check, and supporting evidence.", "Use the suggested next step or open Alerts to follow up on a warning."],
    "Unavailable means a check could not confirm healthy operation. It does not by itself identify a root cause."
  ],
  alerts: [
    "Collect threshold-based operational warnings that may need a manager or administrator to investigate.",
    ["Review each alert's component, severity, time, and supporting observation.", "Open the related health or operations page for more detail.", "Assign follow-up through the appropriate staff workflow if action is needed."],
    "An alert is a signal to review recorded evidence; it does not automatically confirm a service outage."
  ],
  "ai-assistant": [
    "Ask operational questions and request reports or system checks using data your account is permitted to view.",
    ["Ask one clear question and include the property and timeframe when relevant.", "Check the response's evidence, reported time window, and any unavailable data.", "Start a new conversation to change topics, or use Hotel Knowledge AI for source-library work."],
    "Assistant answers summarize available records. Verify important decisions against the linked operational pages."
  ],
  analytics: [
    "Explore guest engagement, service delivery, department performance, and AI outcomes over time.",
    ["Choose a preset period or Custom, enter both dates, then select Apply.", "Compare the metric cards and charts, then inspect top services and questions.", "Use the findings to decide which services or knowledge entries need attention."],
    "Very recent or sparse activity can make trends incomplete; always check the selected dates before sharing a result."
  ],
  reports: [
    "Create a management summary or a detailed workbook for the selected property and reporting period.",
    ["Confirm the active property and choose the report period above the download cards.", "Choose the XLSX workbook for detailed sheets or the PDF for a concise summary.", "Review the downloaded file's property, date range, and included data before forwarding it."],
    "Reports contain operational data. Share them only with people who are authorized to see that property."
  ],
  appearance: [
    "Customize the guest concierge's brand, greeting, colors, and chat preview for the active property.",
    ["Set the hotel and concierge names, logo, and the way the header is displayed.", "Write the greeting, welcome headline, and composer hint; these are the guest's first chat cues.", "Adjust background, surface, text, accent, and button colors, then inspect the preview for contrast.", "Save a draft and use Publish in the top bar when the design is ready."],
    "This page controls presentation. Keep factual guest guidance in Hotel Information, FAQs, or approved Knowledge."
  ],
  zones: [
    "Build the property's indoor map by connecting a building and floor-plan image to named places, amenity pins, and navigation features.",
    ["Choose the building and floor from the map toolbar, then upload the matching plan image.", "Choose a drawing tool such as Rectangle or Polygon and draw an area, or select a map object from the hierarchy.", "Set the object type and name in Selected Object; choose Guest visible for places guests should see, and Operations only for staff or infrastructure items.", "Save the object and use the layer controls to check that zones, facilities, access points, paths, and the floor plan are easy to distinguish."],
    "Keep the map aligned with the actual property. Network access-point identifiers belong in the location workflow, not guest-facing labels."
  ],
  location: [
    "Manage guest-visible property locations and review aggregate activity derived from configured WLAN observations.",
    ["Create or update a location with a clear guest-facing name and map placement.", "Choose the reporting period and review the available activity summaries.", "Confirm that network observations are configured before interpreting location counts."],
    "Location activity is an aggregate signal; it should not be treated as precise individual tracking."
  ],
  intro: [
    "Configure the branded welcome or introductory experience guests see before starting a concierge conversation.",
    ["Choose whether chat opens directly, uses the property logo, or plays a custom brand video.", "Set the welcome message, motion preset, duration, colors, and guest skip behavior.", "Preview the phone and desktop layouts. For custom video, upload a silent MP4 or WebM file up to 12 MB.", "Save and activate the intro; it is applied to the guest app as soon as it is saved."],
    "Use readable contrast and keep a reduced-motion-friendly experience for guests who prefer less animation."
  ],
  ai: [
    "Configure AI providers and routing used by the property, and review whether the selected provider is reachable.",
    ["Choose the intended provider and model or routing policy.", "Open that provider's configuration, add its credential in the protected secret field, and run the connection check.", "Review provider status and recent usage before relying on a route."],
    "Provider credentials are stored through the protected credential workflow and are not shown again after saving. Never paste them into notes or guest content."
  ],
  "improvement-loop": [
    "Run a bounded, reviewable improvement cycle for AI behavior using an explicit goal and measurable evaluation criteria.",
    ["Write the desired outcome, constraints, and evidence used to evaluate it.", "Choose the configured provider and a limited iteration budget, then start the run.", "Review every proposed change and its evaluation before approving, revising, pausing, or stopping."],
    "A generated proposal does not become live until an authorized person reviews and applies it."
  ],
  knowledge: [
    "Review extracted and authored property facts before allowing them to support guest answers.",
    ["Search or filter the queue by source and review status.", "Open an item, correct its wording and source details, then approve only verified information.", "Keep published entries enabled and revisit them when hotel policies or services change."],
    "Uploaded or extracted content is not automatically trustworthy or guest-visible; verify it before approval."
  ],
  wifi: [
    "Check the configured ANTlabs/WLAN gateway connection used for guest session and network context.",
    ["Confirm the intended gateway and runtime mode with the platform administrator.", "Select Test Connection and read the result and timestamp.", "Resolve missing credentials or network reachability in protected deployment configuration."],
    "Gateway secrets are environment-controlled and are not entered or displayed in this browser page."
  ],
  "auth-types": [
    "Choose which supported guest sign-in methods appear in the guest experience.",
    ["Review which login methods are available and configured for this deployment.", "Enable only methods the property can actually support.", "Save changes and verify the guest sign-in screen."],
    "An enabled method that lacks a working identity provider can prevent guests from signing in."
  ],
  guest: [
    "Create and order guest-facing shortcut buttons that send a prepared request to the concierge chat.",
    ["Give each module a short action name guests will understand.", "Write a complete prompt that asks for help without storing hotel facts or private staff instructions.", "Set its order and visibility, save the module, then check it in the guest app."],
    "A conversation module starts a chat request; it does not execute a service workflow. Use Guest Requests for tracked work and the Property pages for verified information."
  ],
  conversations: [
    "Review restaurant staff requests guests chose to send, assign them to an eligible team member, and reply while that person handles the request.",
    ["Use the status cards or search to find a staff request.", "Open the request to review the restaurant and the reason the guest submitted.", "Assign or accept the request, send a reply, then resolve it or return it to the concierge when appropriate."],
    "Only the guest's submitted staff request and staff replies appear here. Ordinary concierge chat stays private."
  ],
  "service-catalog": [
    "Connect guest request options to the hotel teams that fulfill them. Departments provide ownership and escalation; services describe what a guest can request and how quickly staff should respond.",
    ["Create a department for each team that owns work, such as Housekeeping, Front Desk, or Engineering. Set a realistic default SLA and escalation contact.", "Add a separate service for each guest request type, such as Extra towels or Air-conditioning help.", "Assign each service to a department, add common guest keywords and a clear description, then set its SLA and whether the guest must confirm before submission.", "Enable the service and check that it appears correctly in the Guest Requests workflow. Disable it when the team cannot fulfill it."],
    "A catalog entry routes and tracks a request; it does not perform the work or notify staff outside configured workflows. Keep response targets aligned with actual staffing."
  ],
  users: [
    "Create and maintain administrator or staff accounts and control which properties they can access.",
    ["Search the user list or create a new account.", "Assign the smallest role and property scope needed for the person's job.", "Review status and sessions, then deactivate access promptly when it is no longer needed."],
    "Share temporary credentials securely and ask new users to change them at first sign-in."
  ],
  roles: [
    "Define reusable role profiles that group the administrative capabilities a user may access.",
    ["Review built-in roles before creating a custom one.", "Name the custom role and grant only the permissions required for its duties.", "Save it, then assign it to a test account and confirm the allowed pages."],
    "Permission checks are enforced by the API as well as the interface. Avoid broad access without a clear need."
  ],
  permissions: [
    "Read the permission catalog to understand which actions can be granted through roles.",
    ["Find the capability by its name or description.", "Use the catalog while designing roles and access scopes.", "Manage grants from Roles or Users rather than changing this reference list."],
    "This catalog is descriptive; it does not grant access by itself."
  ],
  audit: [
    "Review a traceable record of administrator changes, security events, and configuration activity.",
    ["Choose relevant filters such as user, action, or date range.", "Apply the filters or refresh the records.", "Open event details to understand what changed and who performed it."],
    "Audit history is read-only. Use it for review and follow-up, not as a place to edit records."
  ],
  profile: [
    "Review your administrator identity, role, and property access scope.",
    ["Confirm that the displayed name, username, and email are correct.", "Check the assigned role and property scope with an administrator if they are wrong.", "Use Security to change your password or review session protections."],
    "Your role and property scope determine which information and actions appear elsewhere in the platform."
  ],
  security: [
    "Protect your administrator account by changing credentials and reviewing session safeguards.",
    ["Enter your current password and a new password that meets the displayed policy.", "Confirm the new password and save the change.", "Sign out sessions you no longer recognize, if the controls are available."],
    "Do not reuse guest-facing or shared staff credentials for an administrator account."
  ],
  "hotel-information": [
    "This is the property's main guest-facing fact sheet. Concierge answers and other guest pages can refer to its name, location, contact details, arrival guidance, and policies.",
    ["Enter the official hotel name, a clear short description, address, phone, email, and website.", "Choose check-in and checkout times using the time controls, then explain breakfast, Wi-Fi access, and important policies.", "Save and publish the facts, then check the guest app and correct anything guests could misunderstand.", "Use Rooms, Facilities, Restaurants, and Service Catalog to add the detailed directories that do not fit in this summary."],
    "Write verified guest-ready facts and include local time context where needed. Put staff-only procedures in internal notes, not here."
  ],
  rooms: [
    "Describe the room categories or room types guests may ask about. These records provide room information to the concierge and are separate from live room assignment or reservation systems.",
    ["Add one recognizable entry for each type, such as Deluxe King or Family Suite.", "Describe guest-relevant features and set the maximum number of guests.", "Optionally add the reference number of rooms and guest-facing floor range.", "Set the catalog status and save. Search or filter the list to edit an entry when details change."],
    "Room counts and catalog status are reference information, not live inventory. This page does not synchronize occupied rooms, prices, or reservations with a PMS. Never enter a guest's assigned room number."
  ],
  restaurants: [
    "Maintain the dining directory guests can browse and ask Concierge AI about. Each restaurant can include venue details, weekly hours, meal periods, menus, promotions, and reservation information.",
    ["Choose Add Restaurant and enter the venue name, cuisine, location, and the linked facility or map zone when available.", "Set the hours for each day, meal periods, current operating status, and reservation options. Add guest-facing descriptions and contact details.", "Save the venue, then open Menus, promotions, and reports to add menu items and submit time-limited offers for approval.", "Search the restaurant list and update hours, availability, or guest information whenever operations change."],
    "Keep internal notes separate from guest notes. Check prices, allergens, reservation links, promotions, and temporary closures before publishing changes."
  ],
  recommendations: [
    "Curate nearby attractions, shops, transport points, and other places that Concierge AI can recommend to guests as local cards.",
    ["Add the place name and a useful category, then enter its full address.", "Write a short description that explains why a guest might visit, and add a working map link.", "Record the recommendation source, choose guest visibility, and save.", "Check the guest preview to confirm the card and directions are useful."],
    "Only publish places the property is comfortable recommending. Verify safety, distance, hours, and links periodically."
  ],
  documents: [
    "Upload property source files and turn their contents into reviewable knowledge items.",
    ["Choose one or more supported files and upload them.", "Wait for processing, then review extracted items in Knowledge.", "Correct and approve only verified entries before making them guest-visible."],
    "An upload is a source for review, not an automatic update to guest answers. Image extraction requires OCR support."
  ],
  faqs: [
    "Maintain approved question-and-answer pairs for common guest questions.",
    ["Enter the guest's likely question and a complete, verified answer.", "Enable it for Concierge AI and save.", "Review managed FAQs and update or disable entries when the policy changes."],
    "Use precise answers and avoid including private staff procedures or information that should not be shared with guests."
  ],
  "ai-personality": [
    "Set the concierge's voice, formality, response length, and greeting behavior for this property.",
    ["Choose an identity and tone that fit the property.", "Set response length and greeting behavior, then write concise property-specific instructions.", "Save and try representative questions in the guest preview."],
    "Personality shapes wording; approved facts and system safety rules determine what the concierge may say or do."
  ],
  "system-prompt": [
    "Explain the protected prompt policy that guides Concierge AI and the approved hotel context it can use.",
    ["Use AI Personality for response style and Guardrails for allowed actions and safety settings.", "Use Knowledge and Hotel Information to manage verified property facts.", "Ask a platform administrator to change server-managed prompt policy."],
    "This page is intentionally read-only so protected instructions cannot be exposed or edited in the browser."
  ],
  guardrails: [
    "Set backend-enforced safety, privacy, network, escalation, and action limits for guest workflows.",
    ["Review network ranges and trusted proxy addresses with your infrastructure administrator.", "Enable only the internet tools, actions, and data handling that are configured and approved.", "Save changes and review diagnostics to confirm the intended policy is active."],
    "Incorrect CIDR ranges or proxy trust settings can block legitimate guests or trust the wrong network. Validate them before saving."
  ],
  api: [
    "Show the status and administration boundary for secure API access and integration policies.",
    ["Review the availability message on this page.", "Manage credentials through the approved server-side secret workflow.", "Contact the platform administrator for API access and integration documentation."],
    "API credentials are restricted to protected deployment configuration and are not created in this browser page."
  ],
  webhooks: [
    "Send signed, property-scoped event notifications to an approved external system.",
    ["Create an endpoint with an HTTPS URL and select only the events the receiver needs.", "Set a signing secret and enable the endpoint, then save it.", "Review recent delivery records and repair receiver errors before relying on delivery."],
    "Treat signing secrets as passwords. The receiver should verify signatures and safely handle duplicate event delivery."
  ],
  "third-party": [
    "Use the integration directory to find the correct setup area for guest Wi-Fi, guest sign-in, outbound events, and external service connections.",
    ["Open ANTlabs / Wi-Fi to inspect gateway status and run a connection check.", "Open Authentication methods to choose which configured sign-in options guests can use.", "Open Webhooks to configure signed event delivery and review recent delivery attempts.", "Treat the external-service empty state as authoritative: no PMS or other third-party data sync is active until a supported connector is configured."],
    "API credentials remain deployment-managed and cannot be viewed or created in this browser."
  ],
  questions: [
    "Show aggregated patterns in guest questions and highlight gaps in property knowledge.",
    ["Review the page's collection status and wait for enough guest activity to accumulate.", "Use Knowledge or FAQs to address verified information gaps.", "Revisit trends after the knowledge update to see whether unanswered topics decrease."],
    "This page may not have historical results yet. Guest question analytics are aggregated and should not expose credentials."
  ],
  "request-analytics": [
    "Provide historical views of request volume, SLA performance, completion, and department trends when available.",
    ["Use Guest Requests for the live queue and immediate staff follow-up.", "Review the historical analytics once enough request data has been collected.", "Compare results by period and department before adjusting staffing or service levels."],
    "This page currently directs live work to Guest Requests; historical reporting may be unavailable until data accumulates."
  ],
  "ai-usage": [
    "Review recorded provider and model request volume, errors, and latency over time.",
    ["Choose a reporting period.", "Compare the usage metrics and provider/model activity list.", "Open Models & Providers or System Health to investigate elevated errors or latency."],
    "Costs are not shown unless verified billing data is connected; request counts alone do not establish spend."
  ],
  "system-settings": [
    "Set application defaults and protected outbound email used for password-reset messages.",
    ["Set the default language, time zone, and any maintenance banner, then save.", "Configure SMTP host, port, security, sender, and credentials if email is required.", "Test the SMTP connection before saving the email configuration."],
    "A blank password keeps the saved credential. Use a verified sender address and protect the SMTP password."
  ],
  "network-access": [
    "Review private management access and the property-specific guest network policy.",
    ["Keep management networks separate from guest networks.", "Configure the hotel's guest domain and existing network guardrails.", "Verify DNS and SSL after the hotel's DNS and certificate are ready."],
    "The application detects the server address but does not change host networking."
  ]
};

function createRelatedPageNav(pageId) {
  const nav = document.createElement("nav");
  nav.className = "page-comment-related";
  nav.setAttribute("aria-label", "Related admin pages");
  nav.dataset.relatedPage = pageId;
  nav.innerHTML = `<h2>Related pages</h2><div class="page-comment-related-links"></div>`;
  return nav;
}

function addPageComment(panel) {
  if (!panel) return;
  const existingGuide = panel.querySelector(":scope > .contextual-help-disclosure > .module-guide, :scope > .contextual-help-disclosure > .personalization-guide, :scope > .contextual-help-disclosure > .session-guide, :scope > .contextual-help-disclosure > .request-guide, :scope > .contextual-help-disclosure > .facility-guide, :scope > .contextual-help-disclosure > .room-guide-card, :scope > .contextual-help-disclosure > .intro-guide, :scope > .module-guide, :scope > .personalization-guide, :scope > .session-guide, :scope > .request-guide, :scope > .facility-guide, :scope > .room-guide-card, :scope > .intro-guide");
  if (existingGuide) {
    if (!existingGuide.parentElement.matches(".contextual-help-disclosure")) {
      const disclosure = document.createElement("details");
      disclosure.className = "contextual-help-disclosure";
      disclosure.innerHTML = `<summary><span aria-hidden="true">?</span><strong>How this page works</strong><span class="contextual-help-toggle" aria-hidden="true"></span></summary>`;
      existingGuide.before(disclosure);
      disclosure.appendChild(existingGuide);
    }
    if (PAGE_LINKS[panel.id] && !existingGuide.querySelector(":scope > .page-comment-related")) {
      existingGuide.appendChild(createRelatedPageNav(panel.id));
    }
    if (state.auth) populatePageCommentLinks();
    return;
  }
  if (panel.querySelector(":scope > .page-comment")) return;

  const [purpose, steps, note] = PAGE_COMMENTS[panel.id] || [
    "Review the page description and availability status to understand this capability.",
    ["Check the displayed data or availability message.", "Use the linked operational page or contact a platform administrator when this workflow is unavailable."],
    "Only rely on controls and data that are shown as available for your account and this property."
  ];
  const title = panel.id === "overview"
    ? "Operations overview"
    : panel.querySelector(":scope > .page-title h1, .onboarding-card h1")?.textContent?.trim() || panel.id;
  const guide = document.createElement("details");
  guide.className = "page-comment";
  guide.dataset.page = panel.id;
  guide.innerHTML = `<summary><span class="page-comment-help-icon" aria-hidden="true">?</span><span class="page-comment-summary-title"></span><span class="page-comment-toggle" aria-hidden="true"></span></summary><div class="page-comment-content"><section><h2>What this page is for</h2><p class="page-comment-purpose"></p></section><section><h2>How to use it</h2><ol class="page-comment-steps"></ol></section><p class="page-comment-note"></p><nav class="page-comment-related" aria-label="Related admin pages" hidden><h2>Related pages</h2><div class="page-comment-related-links"></div></nav></div>`;
  guide.querySelector(".page-comment-summary-title").textContent = title;
  guide.querySelector("summary").setAttribute("aria-label", `Help for ${title}`);
  guide.querySelector(".page-comment-purpose").textContent = purpose;
  guide.querySelector(".page-comment-note").textContent = note;
  guide.querySelector(".page-comment-related").dataset.relatedPage = panel.id;
  const list = guide.querySelector(".page-comment-steps");
  for (const step of steps) {
    const item = document.createElement("li");
    item.textContent = step;
    list.appendChild(item);
  }

  const titleBlock = panel.querySelector(":scope > .page-title");
  if (titleBlock) titleBlock.after(guide);
  else if (panel.id === "property-onboarding") panel.querySelector(".onboarding-card > button")?.before(guide);
  else panel.prepend(guide);
  if (state.auth) populatePageCommentLinks();
}

const PAGE_LINKS = {
  overview: ["system-health", "alerts", "analytics"],
  "system-health": ["alerts", "ai", "ai-usage"],
  alerts: ["system-health", "requests"],
  "ai-assistant": ["requests", "reports"],
  conversations: ["restaurants", "requests"],
  analytics: ["reports", "ai-usage"],
  reports: ["analytics", "ai-usage"],
  appearance: ["intro", "guest"],
  guest: ["appearance", "intro", "hotel-information"],
  "personalization-settings": ["sessions", "guardrails", "knowledge"],
  zones: ["facilities", "location", "appearance"],
  sessions: ["location", "personalization-settings"],
  location: ["zones", "analytics", "sessions"],
  intro: ["appearance", "guest", "hotel-information"],
  ai: ["ai-usage", "system-health", "guardrails"],
  "improvement-loop": ["ai", "knowledge", "ai-assistant"],
  knowledge: ["documents", "faqs", "hotel-information"],
  documents: ["knowledge", "faqs"],
  faqs: ["knowledge", "guest"],
  wifi: ["auth-types", "sessions", "network-access"],
  "auth-types": ["wifi", "guardrails"],
  requests: ["service-catalog", "reports"],
  "service-catalog": ["requests", "recommendations"],
  users: ["roles", "audit", "security"],
  roles: ["permissions", "users"],
  permissions: ["roles", "users"],
  audit: ["users", "security", "system-settings"],
  profile: ["security", "users"],
  security: ["users", "audit"],
  "hotel-information": ["rooms", "facilities", "restaurants"],
  rooms: ["facilities", "restaurants"],
  facilities: ["restaurants", "zones", "recommendations"],
  restaurants: ["service-catalog", "recommendations"],
  recommendations: ["zones", "restaurants"],
  "ai-personality": ["guest", "guardrails", "appearance"],
  "system-prompt": ["ai-personality", "guardrails", "knowledge"],
  guardrails: ["network-access", "wifi", "security"],
  api: ["webhooks", "ai", "system-settings"],
  webhooks: ["api", "service-catalog", "requests"],
  "third-party": ["wifi", "webhooks", "ai"],
  questions: ["knowledge", "faqs", "analytics"],
  "request-analytics": ["requests", "service-catalog", "reports"],
  "ai-usage": ["ai", "system-health", "reports"],
  "system-settings": ["security", "webhooks", "system-health"],
  "network-access": ["guardrails", "wifi"]
};

function populatePageCommentLinks() {
  for (const related of document.querySelectorAll(".page-comment-related[data-related-page]")) {
    const links = related.querySelector(".page-comment-related-links");
    if (!links) continue;
    links.replaceChildren();
    const targets = PAGE_LINKS[related.dataset.relatedPage] || [];
    for (const target of targets) {
      const item = allNavItems().find((candidate) => {
        return candidate.panel === target && can(candidate.permission) && (!candidate.superAdminOnly || isSuperAdmin());
      });
      if (!item) continue;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary page-comment-related-link";
      button.dataset.panel = item.panel;
      button.textContent = `Open ${item.label}`;
      button.addEventListener("click", () => {
        activatePanel(item.panel, item.id);
        document.querySelector(".platform-main")?.scrollTo({ top: 0, behavior: "smooth" });
      });
      links.appendChild(button);
    }
    related.hidden = links.childElementCount === 0;
  }
}

function annotateAdminPages() {
  for (const panel of document.querySelectorAll(".panel")) addPageComment(panel);
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
  populatePageCommentLinks();
  applyPermissionVisibility();
  activatePanel(state.activeNavId ? allNavItems().find((item) => item.id === state.activeNavId)?.panel || "overview" : "overview", state.activeNavId || "dashboard");
  if (state.auth.force_password_change) {
    activatePanel("security");
    showToast("Change your temporary password to continue.");
  }
}

function activatePanel(panelId, navId = null) {
  const requestedItem = navId
    ? allNavItems().find((item) => item.id === navId)
    : allNavItems().find((item) => item.panel === panelId);
  if (requestedItem && state.auth && !["profile", "security"].includes(panelId) && (!can(requestedItem.permission) || (requestedItem.superAdminOnly && !isSuperAdmin()))) {
    showToast("This area is not available for your account.", "error");
    return;
  }
  const panel = ensurePanel(panelId);
  document.querySelector(".platform-shell")?.classList.toggle("is-design-panel", panelId === "appearance");
  if (panel) addPageComment(panel);
  for (const panel of document.querySelectorAll(".panel")) {
    panel.classList.toggle("active", panel.id === panelId);
  }
  if (navId) state.activeNavId = navId;
  if (!navId) state.activeNavId = allNavItems().find((item) => item.panel === panelId)?.id || null;
  for (const item of document.querySelectorAll(".nav-item")) {
    item.classList.toggle("active", item.dataset.navId === state.activeNavId);
  }
  const activeNavItem = [...document.querySelectorAll(".nav-item")].find((item) => item.dataset.navId === state.activeNavId);
  const activeNavGroup = activeNavItem?.closest(".nav-group");
  if (activeNavGroup) activeNavGroup.open = true;
  if (panelId === "appearance") requestAnimationFrame(fitPreview);
  if (panelId === "ai-assistant" && currentPropertyId()) {
    $("assistant-chat-scope").textContent = propertyName(currentPropertyId()) + " · Personal history";
    loadAssistantConversations().catch((error) => showToast(error.message, "error"));
  }
  if (panelId === "overview" && currentPropertyId()) loadDashboard().catch((error) => showToast(error.message, "error"));
  if (["system-health", "alerts", "analytics", "reports"].includes(panelId) && currentPropertyId()) {
    loadDashboard().catch((error) => showToast(error.message, "error"));
  }
  if (panelId === "ai" && currentPropertyId()) {
    loadAI().catch((error) => showToast(error.message, "error"));
  }
  if (panelId === "improvement-loop" && currentPropertyId()) {
    loadImprovementLoop().catch((error) => showToast(error.message, "error"));
  }
  if (panelId === "zones" && currentPropertyId()) loadZones().catch((error) => showToast(error.message, "error"));
  if (panelId === "sessions" && currentPropertyId()) loadSessions().catch((error) => showToast(error.message, "error"));
  if (panelId === "conversations" && currentPropertyId()) loadConversations().catch((error) => showToast(error.message, "error"));
  if (panelId === "personalization-settings" && currentPropertyId()) loadPersonalizationPolicy().catch((error) => showToast(error.message, "error"));
  if (panelId === "location" && currentPropertyId()) loadLocationLive().catch((error) => showToast(error.message, "error"));
  if (panelId === "intro" && currentPropertyId()) loadIntro().catch((error) => showToast(error.message, "error"));
  if (panelId === "requests" && currentPropertyId()) loadServiceRequests().catch((error) => showToast(error.message, "error"));
  if (panelId === "service-catalog" && currentPropertyId()) loadServiceCatalog().catch((error) => showToast(error.message, "error"));
  if (panelId === "recommendations" && currentPropertyId()) loadRecommendations().catch((error) => showToast(error.message, "error"));
  if (panelId === "hotel-information" && currentPropertyId()) loadHotelInformation();
  if (panelId === "rooms" && currentPropertyId()) renderRooms();
  if (panelId === "guest" && currentPropertyId()) renderGuestModules();
  if (["facilities", "restaurants"].includes(panelId) && currentPropertyId()) loadHospitalityManagement().catch((error) => showToast(error.message, "error"));
  if (panelId === "ai-usage" && currentPropertyId()) loadAIUsage().catch((error) => showToast(error.message, "error"));
  if (panelId === "wifi" && currentPropertyId()) loadAntlabsStatus().catch((error) => showToast(error.message, "error"));
  if (panelId === "auth-types" && currentPropertyId()) loadAntlabsStatus().catch((error) => showToast(error.message, "error"));
  if (["knowledge", "documents", "faqs"].includes(panelId) && currentPropertyId()) loadKnowledge().catch((error) => showToast(error.message, "error"));
  if (["ai-personality", "guardrails"].includes(panelId) && currentPropertyId()) loadAIPolicy();
  if (panelId === "guardrails" && currentPropertyId()) loadGuardrailDiagnostics().catch((error) => showToast(error.message, "error"));
  if (panelId === "webhooks" && currentPropertyId()) loadWebhooks().catch((error) => showToast(error.message, "error"));
  if (panelId === "network-access" && currentPropertyId()) {
    loadNetworkAccess().catch((error) => showToast(error.message, "error"));
    if (can("security.view")) loadGuardrailDiagnostics().catch((error) => showToast(error.message, "error"));
  }
  if (panelId === "system-settings") loadSystemSettings().catch((error) => showToast(error.message, "error"));
  if (panelId === "users") loadUsers().catch((error) => showToast(error.message, "error"));
  if (panelId === "roles") loadRoles().catch((error) => showToast(error.message, "error"));
  if (panelId === "permissions") loadPermissions().catch((error) => showToast(error.message, "error"));
  if (panelId === "audit") loadAudit().catch((error) => showToast(error.message, "error"));
}

function currentPropertyId() {
  return state.property?.property_id || $("property-id").value;
}

async function loadPersonalizationPolicy() {
  const config = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/personalization`);
  state.personalizationPolicy = config;
  $("personalization-enabled").checked = Boolean(config.enabled);
  $("personalization-default-level").value = config.default_level || "private";
  $("personalization-learning").checked = Boolean(config.allow_preference_learning);
  $("personalization-profile").checked = Boolean(config.allow_guest_profile);
  $("personalization-delete-checkout").checked = Boolean(config.delete_profile_at_checkout);
  $("personalization-retention").value = config.memory_retention || "stay_only";
  const retentionDays = Number(config.memory_retention_days) || 2;
  $("personalization-retention-days").dataset.configurableValue = String(retentionDays);
  $("personalization-retention-days").value = $("personalization-retention").value === "configurable" ? retentionDays : 2;
  $("personalization-pms").checked = Boolean(config.allow_pms_personalization);
  $("personalization-location").checked = Boolean(config.allow_location_aware_recommendations);
  $("personalization-internet").checked = Boolean(config.allow_internet_recommendations);
  $("personalization-retention-days").disabled = $("personalization-retention").value !== "configurable";
  const personalOption = $("personalization-default-level").querySelector('option[value="personal"]');
  personalOption.disabled = !config.allow_guest_profile;
}

async function savePersonalizationPolicy() {
  const retentionMode = $("personalization-retention").value;
  const retentionDays = retentionMode === "configurable" ? Number($("personalization-retention-days").value) : 2;
  if (retentionMode === "configurable" && (!Number.isInteger(retentionDays) || retentionDays < 1 || retentionDays > 365)) {
    throw new Error("Configurable memory expiry must be between 1 and 365 days.");
  }
  const payload = {
    enabled: $("personalization-enabled").checked,
    default_level: $("personalization-default-level").value,
    allow_preference_learning: $("personalization-learning").checked,
    allow_guest_profile: $("personalization-profile").checked,
    delete_profile_at_checkout: $("personalization-delete-checkout").checked,
    memory_retention: $("personalization-retention").value,
    memory_retention_days: retentionDays,
    allow_pms_personalization: $("personalization-pms").checked,
    allow_location_aware_recommendations: $("personalization-location").checked,
    allow_internet_recommendations: $("personalization-internet").checked,
  };
  state.personalizationPolicy = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/personalization`, {
    method: "PUT",
    body: JSON.stringify({ data: payload }),
  });
  showToast("Personalization settings saved.");
}

async function loadDashboard() {
  const period = state.operationsPeriod || "24h";
  const range = period === "custom" && state.operationsStart && state.operationsEnd
    ? `&start_at=${encodeURIComponent(state.operationsStart)}&end_at=${encodeURIComponent(state.operationsEnd)}` : "";
  state.operations = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/operations/dashboard?period=${encodeURIComponent(period)}${range}`);
  renderOperationsDashboard();
}

function metricCard(label, value, detail, stateName = "") {
  const display = value === null || value === undefined ? "Unavailable" : value;
  return `<article class="operations-metric ${escapeHTML(stateName)}"><span>${escapeHTML(label)}</span><strong>${escapeHTML(display)}</strong><small>${escapeHTML(detail)}</small></article>`;
}

function lineChart(title, series, formatter = (value) => value) {
  const available = (series || []).filter((item) => item.value !== null && Number.isFinite(Number(item.value)));
  if (available.length < 2) {
    return `<article class="chart-card"><header><div><span>Historical telemetry</span><h2>${escapeHTML(title)}</h2></div></header><div class="chart-empty"><strong>Not enough history</strong><p>Real samples will appear as this environment records them.</p></div></article>`;
  }
  const values = available.map((item) => Number(item.value));
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const span = Math.max(1, maximum - minimum);
  const plotted = available.map((item, index) => ({
    item,
    x: 12 + index * (276 / Math.max(1, available.length - 1)),
    y: 100 - ((Number(item.value) - minimum) / span) * 74,
  }));
  const points = plotted.map(({ x, y }) => `${x},${y}`).join(" ");
  const hoverPoints = plotted.map(({ item, x, y }) => `<circle class="chart-point" cx="${x}" cy="${y}" r="3"><title>${escapeHTML(formatDate(item.timestamp))}: ${escapeHTML(formatter(item.value))}</title></circle>`).join("");
  const latest = formatter(values.at(-1));
  return `<article class="chart-card"><header><div><span>Recorded history</span><h2>${escapeHTML(title)}</h2></div><strong>${escapeHTML(latest)}</strong></header><svg viewBox="0 0 300 112" role="img" aria-label="${escapeHTML(title)} trend"><path d="M12 100H288" class="chart-axis"/><polyline points="${points}" class="chart-line"/>${hoverPoints}</svg><footer><span>${escapeHTML(formatDate(available[0].timestamp))}</span><span>${escapeHTML(formatDate(available.at(-1).timestamp))}</span></footer></article>`;
}

function listRows(items, emptyText) {
  if (!items?.length) return `<div class="empty-inline">${escapeHTML(emptyText)}</div>`;
  return items.map((item) => `<div class="operations-row"><div><strong>${escapeHTML(item.name || item.title || item.question)}</strong>${item.evidence ? `<p>${escapeHTML(item.evidence)}</p>` : ""}</div><span>${escapeHTML(item.value ?? item.count ?? "")}</span></div>`).join("");
}

function renderOperationsDashboard() {
  const data = state.operations;
  if (!data) return;
  const summary = data.analytics.summary;
  const profileCopy = {
    platform: "Platform-wide technical health and operational signals for this property.",
    property_operations: "Property health, integrations, guest operations, and service demand.",
    management: "Management performance across guest engagement, service delivery, and AI outcomes.",
    department: "Department-scoped service demand, SLA performance, and trends.",
    service_operations: "Live guest and service-request operations for front-line teams.",
    content_operations: "Knowledge coverage and guest-question trends for content operations.",
    read_only: "Read-only operational reporting and audit visibility.",
  };
  $("operations-profile-label").textContent = `${data.role.name} workspace`;
  $("operations-role-copy").textContent = profileCopy[data.profile] || profileCopy.read_only;
  const banner = $("operations-health-banner");
  const attention = data.health.components.filter((item) => !["healthy", "simulation"].includes(item.state)).length;
  const infrastructureView = can("infrastructure.view");
  const requestAttention = Number(summary.overdue_requests || 0);
  const unresolved = Number(summary.open_requests || 0);
  const bannerState = infrastructureView ? data.health.state : requestAttention ? "warning" : "healthy";
  banner.className = `health-banner ${bannerState}`;
  banner.querySelector(".health-dot").className = `health-dot ${bannerState}`;
  if (infrastructureView) {
    banner.querySelector("strong").textContent = data.health.state === "healthy" ? "All monitored components healthy" : `${attention} component${attention === 1 ? "" : "s"} need review`;
    banner.querySelector("p").textContent = `Updated ${new Date(data.generated_at * 1000).toLocaleTimeString()} · ${data.period} view · no synthetic telemetry`;
  } else {
    banner.querySelector("strong").textContent = requestAttention ? `${requestAttention} request${requestAttention === 1 ? "" : "s"} need attention` : unresolved ? "Guest request queue is on track" : "No open guest requests";
    banner.querySelector("p").textContent = requestAttention ? "Review overdue service requests and confirm their next action." : `Updated ${new Date(data.generated_at * 1000).toLocaleTimeString()} · ${data.period} view · no synthetic telemetry`;
  }
  const healthLink = banner.querySelector("[data-dashboard-panel='system-health']");
  if (healthLink) healthLink.hidden = !infrastructureView;
  const insight = data.insight;
  $("overview-intelligence-message").textContent = insight?.message || "Not enough operational data to generate an insight.";
  $("overview-intelligence-source").textContent = insight?.source || "A recorded-data insight will appear when there is enough activity.";

  const slaMetric = summary.service_requests > 0 && summary.sla_performance_percent !== null ? `${summary.sla_performance_percent}%` : null;
  const aiResolution = summary.ai_conversations > 0 && summary.ai_resolution_rate_percent !== null ? `${summary.ai_resolution_rate_percent}%` : null;
  const cards = data.profile === "platform" ? [
    ["CPU utilization", data.system.cpu_utilization?.value === null ? null : `${data.system.cpu_utilization?.value}%`, "Current host sample"],
    ["Memory utilization", data.system.memory_utilization?.value === null ? null : `${data.system.memory_utilization?.value}%`, "Current host sample"],
    ["Database latency", data.database.latency_ms === null ? null : `${data.database.latency_ms} ms`, data.database.evidence],
    ["Open requests", summary.open_requests, `${summary.overdue_requests} overdue`, summary.overdue_requests ? "warning" : ""],
  ] : data.profile === "department" ? [
    ["Open requests", summary.open_requests, "In your department", summary.open_requests ? "attention" : ""],
    ["Overdue", summary.overdue_requests, "Past the service target", summary.overdue_requests ? "warning" : ""],
    ["SLA performance", slaMetric, slaMetric === null ? "No requests in this period" : "Within service targets", summary.overdue_requests ? "warning" : "success"],
    ["Average resolution", summary.average_resolution_seconds === null ? null : `${Math.round(summary.average_resolution_seconds / 60)} min`, summary.average_resolution_seconds === null ? "No completed requests" : "Completed requests"],
  ] : data.profile === "service_operations" ? [
    ["Open requests", summary.open_requests, "Awaiting completion", summary.open_requests ? "attention" : ""],
    ["Overdue", summary.overdue_requests, "Past the service target", summary.overdue_requests ? "warning" : ""],
    ["SLA performance", slaMetric, slaMetric === null ? "No requests in this period" : "Within service targets", summary.overdue_requests ? "warning" : "success"],
    ["Active guest sessions", can("guest_sessions.view") ? summary.active_sessions : null, can("guest_sessions.view") ? "Currently connected" : "Restricted for your role"],
  ] : data.profile === "content_operations" ? [
    ["Guest requests", summary.service_requests, `${summary.open_requests} still open`],
    ["Guest sessions", summary.guests_assisted, `During ${data.period}`],
    ["AI conversations", summary.ai_conversations, "During selected period"],
    ["AI resolution", aiResolution, aiResolution === null ? "Not enough conversation data" : `${summary.fallback_rate_percent ?? "Unavailable"}% used verified fallback`],
  ] : [
    ["Active guest sessions", can("guest_sessions.view") ? summary.active_sessions : null, can("guest_sessions.view") ? "Currently connected" : "Restricted for your role"],
    ["Open requests", summary.open_requests, `${summary.overdue_requests} overdue`, summary.overdue_requests ? "warning" : ""],
    ["SLA performance", slaMetric, slaMetric === null ? "No requests in this period" : "Within service targets", summary.overdue_requests ? "warning" : "success"],
    ["Guests assisted", can("guest_sessions.view") ? summary.guests_assisted : null, can("guest_sessions.view") ? `During ${data.period}` : "Restricted for your role"],
  ];
  $("operations-metrics").innerHTML = cards.map((item) => metricCard(...item)).join("");
  $("overview-charts").innerHTML = [
    lineChart("Service requests", data.analytics.request_volume),
    lineChart("AI requests", data.analytics.ai.request_volume),
    lineChart("AI latency", data.histories.ai_latency_ms, (value) => `${value} ms`),
    lineChart("API latency", data.histories.api_latency_ms, (value) => `${value} ms`),
    lineChart("HTTP / application errors", data.histories.http_errors),
    lineChart("Guest auth success", data.histories.guest_auth_success_rate, (value) => `${value}%`),
  ].join("");
  $("overview-alerts").innerHTML = data.alerts.length ? data.alerts.map((alert) => `<div class="alert-row ${escapeHTML(alert.severity)}"><div><span>${escapeHTML(alert.component.replaceAll("_", " "))}</span><strong>${escapeHTML(alert.title)}</strong><p>${escapeHTML(alert.evidence)}</p></div>${can("assistant.use") ? `<button class="secondary investigate-alert" type="button" data-question="Investigate ${escapeHTML(alert.title)}">Investigate</button>` : ""}</div>`).join("") : `<div class="empty-inline">No active threshold-based alerts.</div>`;
  $("overview-departments").innerHTML = listRows(data.analytics.requests_by_department, "No department request activity in this period.");
  renderHealthPanel();
  renderAlertsPanel();
  renderAnalyticsPanel();
  bindInvestigateButtons();
}

function renderHealthPanel() {
  const data = state.operations;
  if (!data || !$("health-components")) return;
  const summary = $("system-health-summary");
  if (summary) {
    const states = data.health.components.map((item) => item.state);
    const needsReview = states.filter((value) => ["warning", "critical"].includes(value)).length;
    const unavailable = states.filter((value) => value === "unavailable").length;
    const restricted = states.filter((value) => value === "restricted").length;
    const normal = states.filter((value) => ["healthy", "simulation"].includes(value)).length;
    const heading = needsReview ? `${needsReview} check${needsReview === 1 ? "" : "s"} need review` : unavailable ? `${unavailable} check${unavailable === 1 ? " is" : "s are"} unavailable` : "No active health warnings";
    const counts = [`${normal} healthy or simulated`, ...(needsReview ? [`${needsReview} need review`] : []), ...(unavailable ? [`${unavailable} unavailable`] : []), ...(restricted ? [`${restricted} restricted`] : [])];
    summary.className = `health-banner ${data.health.state}`;
    summary.querySelector(".health-dot").className = `health-dot ${data.health.state}`;
    summary.querySelector("strong").textContent = heading;
    summary.querySelector("p").textContent = `Updated ${new Date(data.generated_at * 1000).toLocaleTimeString()} · ${data.period} timeframe · ${counts.join(" · ")}.`;
  }
  $("health-components").innerHTML = data.health.components.map((item) => `<article class="component-card"><div><span class="health-dot ${escapeHTML(item.state)}"></span><strong>${escapeHTML(item.name)}</strong></div><span class="state-label ${escapeHTML(item.state)}">${escapeHTML(item.state.replaceAll("_", " "))}</span><p>${escapeHTML(item.evidence)}</p>${!["healthy", "simulation"].includes(item.state) ? `<footer><button class="secondary" type="button" data-dashboard-panel="alerts">View alerts</button>${can("audit.view") ? `<button class="secondary" type="button" data-dashboard-panel="audit">Logs</button>` : ""}${can("assistant.use") ? `<button class="secondary investigate-alert" type="button" data-question="Investigate ${escapeHTML(item.name)}">Ask AI</button>` : ""}</footer>` : ""}</article>`).join("");
  $("system-charts").innerHTML = [
    lineChart("CPU utilization", data.histories.cpu_utilization, (value) => `${value}%`),
    lineChart("Memory utilization", data.histories.memory_utilization, (value) => `${value}%`),
    lineChart("Disk utilization", data.histories.disk_utilization, (value) => `${value}%`),
    lineChart("Request queue depth", data.histories.request_queue_depth),
    lineChart("Network receive", data.histories.network_rx_bytes, (value) => `${Math.round(value / 1024 / 1024)} MB`),
    lineChart("Network transmit", data.histories.network_tx_bytes, (value) => `${Math.round(value / 1024 / 1024)} MB`),
    lineChart("Active guest sessions", data.histories.active_sessions),
    lineChart("Application errors", data.histories.http_errors),
  ].join("");
  bindInvestigateButtons();
}

function renderAlertsPanel() {
  if (!state.operations || !$("alerts-list")) return;
  const summary = $("alerts-summary");
  if (summary) {
    const alerts = state.operations.alerts;
    const critical = alerts.filter((alert) => alert.severity === "critical").length;
    const warnings = alerts.filter((alert) => alert.severity === "warning").length;
    const stateName = critical ? "critical" : warnings ? "warning" : "healthy";
    summary.className = `health-banner ${stateName}`;
    summary.querySelector(".health-dot").className = `health-dot ${stateName}`;
    summary.querySelector("strong").textContent = alerts.length ? `${alerts.length} active alert${alerts.length === 1 ? "" : "s"}` : "No active alerts";
    const counts = [critical ? `${critical} critical` : "", warnings ? `${warnings} warning${warnings === 1 ? "" : "s"}` : ""].filter(Boolean);
    summary.querySelector("p").textContent = `Evaluated ${new Date(state.operations.generated_at * 1000).toLocaleTimeString()} · ${state.operations.period} timeframe${counts.length ? ` · ${counts.join(" · ")}` : " · no threshold breaches detected"}.`;
  }
  $("alerts-list").innerHTML = state.operations.alerts.length ? state.operations.alerts.map((alert) => {
    const target = alert.component === "request_queue" ? "requests" : alert.component === "ai_providers" ? "ai" : "system-health";
    const targetItem = allNavItems().find((item) => item.panel === target && can(item.permission));
    return `<article class="alert-card ${escapeHTML(alert.severity)}"><div><span>${escapeHTML(alert.severity)} · ${escapeHTML(alert.component.replaceAll("_", " "))}</span><h2>${escapeHTML(alert.title)}</h2><p>${escapeHTML(alert.evidence)}</p><small>Last observed ${escapeHTML(formatDate(alert.last_seen_at))}</small></div><div>${targetItem ? `<button class="secondary" type="button" data-dashboard-panel="${escapeHTML(target)}">${target === "requests" ? "Open queue" : target === "ai" ? "View providers" : "View metrics"}</button>` : ""}${can("assistant.use") ? `<button type="button" class="investigate-alert" data-question="Investigate ${escapeHTML(alert.title)}">Investigate with AI</button>` : ""}</div></article>`;
  }).join("") : `<div class="empty-state"><strong>No active alerts</strong><p>No configured threshold is currently breached for this property.</p></div>`;
  bindInvestigateButtons();
}

function renderAnalyticsPanel() {
  if (!state.operations || !$("analytics-metrics")) return;
  const data = state.operations.analytics;
  const summary = data.summary;
  $("analytics-metrics").innerHTML = [
    metricCard("Guests assisted", summary.guests_assisted, summary.ai_conversations === null ? "Guest conversation analytics are restricted" : `${summary.ai_conversations} AI conversations`),
    metricCard("Avg. resolution", summary.average_resolution_seconds === null ? null : `${Math.round(summary.average_resolution_seconds / 60)} min`, "Completed requests"),
    metricCard("Fallback rate", summary.fallback_rate_percent === null ? null : `${summary.fallback_rate_percent}%`, summary.fallback_rate_percent === null ? "Not enough conversation data" : "Verified fallback responses"),
  ].join("");
  $("analytics-charts").innerHTML = [lineChart("Request volume", data.request_volume), lineChart("AI errors", state.operations.histories.ai_errors)].join("");
  $("analytics-services").innerHTML = listRows(data.top_services, "No service requests in this period.");
  $("analytics-questions").innerHTML = listRows(data.top_questions, "No guest questions in this period.");
}

function normalizeHotelTime(value) {
  const raw = String(value || "").trim();
  const twentyFourHour = raw.match(/^(\d{1,2}):(\d{2})(?::\d{2})?$/);
  if (twentyFourHour) {
    const hours = Number(twentyFourHour[1]);
    const minutes = Number(twentyFourHour[2]);
    if (hours <= 23 && minutes <= 59) return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
  }
  const twelveHour = raw.match(/^(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m?\.?$/i);
  if (!twelveHour) return "";
  const clockHour = Number(twelveHour[1]);
  const minutes = Number(twelveHour[2] || 0);
  if (clockHour < 1 || clockHour > 12 || minutes > 59) return "";
  const hours = (clockHour % 12) + (twelveHour[3].toLowerCase() === "p" ? 12 : 0);
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function loadHotelTimeInput(inputId, noteId, value) {
  const input = $(inputId);
  const original = String(value || "").trim();
  input.value = normalizeHotelTime(original);
  input.dataset.legacyValue = original && !input.value ? original : "";
  const note = $(noteId);
  note.hidden = !input.dataset.legacyValue;
  note.textContent = input.dataset.legacyValue
    ? `Saved value “${input.dataset.legacyValue}” is preserved. Choose a time to replace it, or use Clear Optional Fields to remove it.`
    : "";
}

function savedHotelTime(inputId) {
  const input = $(inputId);
  return input.value || input.dataset.legacyValue || "";
}

function loadHotelInformation() {
  const property = state.property;
  $("hotel-info-name").value = property.hotel_name || "";
  $("hotel-info-description").value = property.description || "";
  $("hotel-info-address").value = property.address || "";
  $("hotel-info-phone").value = property.contact_details?.phone || "";
  $("hotel-info-email").value = property.contact_details?.email || "";
  $("hotel-info-website").value = property.contact_details?.website || "";
  loadHotelTimeInput("hotel-info-checkin", "hotel-info-checkin-note", property.contact_details?.check_in);
  loadHotelTimeInput("hotel-info-checkout", "hotel-info-checkout-note", property.contact_details?.checkout);
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
      check_in: savedHotelTime("hotel-info-checkin"), checkout: savedHotelTime("hotel-info-checkout"),
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
  const rooms = [...(state.property.rooms || [])].sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
  const query = ($("room-search")?.value || "").trim().toLocaleLowerCase();
  const statusFilter = $("room-status-filter")?.value || "all";
  const availableCount = rooms.filter((room) => (room.status || "available") === "available").length;
  $("room-count").textContent = `${rooms.length} ${rooms.length === 1 ? "room type" : "room types"} · ${availableCount} marked available`;
  const filtered = rooms.filter((room) => {
    const matchesQuery = !query || `${room.name || ""} ${room.description || ""} ${room.floors || ""} ${room.count ?? ""}`.toLocaleLowerCase().includes(query);
    return matchesQuery && (statusFilter === "all" || (room.status || "available") === statusFilter);
  });
  for (const room of filtered) {
    const row = document.createElement("article"); row.className = "compact-row room-entry";
    const status = ["available", "unavailable", "maintenance"].includes(room.status) ? room.status : "available";
    const statusLabel = { available: "Available to describe", unavailable: "Not currently offered", maintenance: "Under maintenance" }[status];
    const details = [`<span><b>Max guests</b>${Number(room.capacity || 1)}</span>`];
    if (room.count !== undefined && room.count !== null && String(room.count).trim() !== "") details.push(`<span><b>Rooms of type</b>${escapeHTML(room.count)}</span>`);
    if (room.floors) details.push(`<span><b>Floor or range</b>${escapeHTML(room.floors)}</span>`);
    row.innerHTML = `<div class="room-entry-heading"><strong>${escapeHTML(room.name)}</strong><span class="room-status-pill is-${status}">${statusLabel}</span></div><div class="room-entry-details">${details.join("")}</div><p class="room-entry-description">${escapeHTML(room.description || "Add a guest-facing description so staff and the concierge can explain this room clearly.")}</p>`;
    const edit = makeActionButton("Edit", () => {
      $("room-id").value = room.id;
      $("room-name").value = room.name;
      $("room-description").value = room.description || "";
      $("room-capacity").value = room.capacity || 1;
      $("room-count").value = room.count ?? "";
      $("room-floors").value = room.floors || "";
      $("room-status").value = room.status || "available";
      $("room-form-title").textContent = "Edit room type";
      $("room-form-help").textContent = `Update the guest-facing details for ${room.name}.`;
      $("cancel-room-edit").hidden = false;
      $("room-name").focus({ preventScroll: true });
      $("room-editor-card").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    const remove = makeActionButton("Delete", () => deleteRoom(room.id));
    edit.className = "btn btn-ghost btn-sm";
    const actions = document.createElement("div"); actions.className = "room-entry-actions"; actions.append(edit, remove);
    row.append(actions); list.appendChild(row);
  }
  if (!filtered.length) {
    const empty = document.createElement("div"); empty.className = "room-empty-state";
    if (!rooms.length) {
      empty.innerHTML = "<span aria-hidden='true'>⌂</span><strong>Your room catalog is ready to build</strong><p>Add one entry per room type, such as a Deluxe King or Family Suite. Include only details you have verified.</p>";
      const add = document.createElement("button"); add.type = "button"; add.className = "btn btn-primary btn-sm"; add.id = "room-empty-add"; add.textContent = "Add first room type";
      add.addEventListener("click", () => clearRoomForm({ focus: true, scroll: true }));
      empty.append(add);
    } else {
      empty.innerHTML = "<strong>No room types match these filters</strong><p>Try another search or status, or clear the filters to see the full catalog.</p>";
      const clear = document.createElement("button"); clear.type = "button"; clear.className = "btn btn-secondary btn-sm"; clear.textContent = "Clear filters";
      clear.addEventListener("click", clearRoomFilters);
      empty.append(clear);
    }
    list.append(empty);
  }
}

function clearRoomFilters() {
  $("room-search").value = "";
  $("room-status-filter").value = "all";
  renderRooms();
}

function clearRoomForm({ focus = false, scroll = false } = {}) {
  $("room-id").value = "";
  $("room-name").value = "";
  $("room-description").value = "";
  $("room-capacity").value = "1";
  $("room-count").value = "";
  $("room-floors").value = "";
  $("room-status").value = "available";
  $("room-form-title").textContent = "Create a room type";
  $("room-form-help").textContent = "Add the details guests and the concierge should use when describing this room.";
  $("cancel-room-edit").hidden = true;
  if (focus) {
    if (scroll) $("room-editor-card").scrollIntoView({ behavior: "smooth", block: "start" });
    $("room-name").focus({ preventScroll: true });
  }
}

async function saveRoom() {
  const name = $("room-name").value.trim();
  if (!name) throw new Error("Room name or type is required.");
  const capacity = Number($("room-capacity").value);
  if (!Number.isInteger(capacity) || capacity < 1 || capacity > 30) throw new Error("Maximum guests must be a whole number from 1 to 30.");
  const countValue = $("room-count").value.trim();
  const count = countValue ? Number(countValue) : null;
  if (countValue && (!Number.isInteger(count) || count < 1 || count > 9999)) throw new Error("Rooms of this type must be a whole number from 1 to 9,999.");
  const id = $("room-id").value || `room_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
  const rooms = [...(state.property.rooms || [])];
  const floorRange = $("room-floors").value.trim();
  const record = { id, name, description: $("room-description").value.trim(), capacity, ...(count === null ? {} : { count }), ...(floorRange ? { floors: floorRange } : {}), status: $("room-status").value };
  const index = rooms.findIndex((item) => item.id === id);
  if (index >= 0) rooms[index] = record; else rooms.push(record);
  state.property.rooms = rooms;
  await savePropertyBasics();
  clearRoomForm();
  renderRooms(); showToast("Room type saved.");
}

async function deleteRoom(id) {
  const room = (state.property.rooms || []).find((item) => item.id === id);
  if (!room || !window.confirm(`Delete “${room.name}”? This removes the room type from the guest property information.`)) return;
  state.property.rooms = (state.property.rooms || []).filter((item) => item.id !== id);
  if ($("room-id").value === id) clearRoomForm();
  await savePropertyBasics(); renderRooms(); showToast("Room deleted.");
}

function renderGuestModules() {
  const list = $("guest-module-list"); list.innerHTML = "";
  const modules = [...(state.property.guest_modules || [])].sort((a, b) => Number(a.order || 0) - Number(b.order || 0));
  const enabledCount = modules.filter((module) => module.enabled !== false).length;
  $("guest-module-count").textContent = modules.length + (modules.length === 1 ? " module" : " modules") + " · " + enabledCount + " shown to guests";
  for (const module of modules) {
    const row = document.createElement("div"); row.className = "compact-row module-saved-row"; row.innerHTML = `<strong>${escapeHTML(module.name)}</strong><span>${module.enabled !== false ? "Shown to guests" : "Hidden"} · menu position ${Number(module.order || 0)}</span><span>${escapeHTML(module.prompt || "")}</span>`;
    const edit = makeActionButton("Edit", () => {
      $("guest-module-id").value = module.id;
      $("guest-module-name").value = module.name;
      $("guest-module-prompt").value = module.prompt || "";
      $("guest-module-order").value = module.order || 0;
      $("guest-module-enabled").checked = module.enabled !== false;
      $("guest-module-form-title").textContent = "Edit module";
      $("save-guest-module").textContent = "Update Module";
      $("guest-module-name").scrollIntoView({ behavior: "smooth", block: "center" });
    });
    const toggle = makeActionButton(module.enabled !== false ? "Hide" : "Show", () => toggleGuestModule(module.id), true);
    const remove = makeActionButton("Delete", () => deleteGuestModule(module.id), true);
    row.append(edit, toggle, remove); list.appendChild(row);
  }
  if (!list.children.length) list.textContent = "No guest menu actions yet. Create one with a guest-facing name and a complete prompt.";
}

function clearGuestModuleForm() {
  $("guest-module-id").value = "";
  $("guest-module-name").value = "";
  $("guest-module-prompt").value = "";
  $("guest-module-order").value = "0";
  $("guest-module-enabled").checked = true;
  $("guest-module-form-title").textContent = "Create a module";
  $("save-guest-module").textContent = "Save Module";
}

async function saveGuestModule() {
  const name = $("guest-module-name").value.trim(); const prompt = $("guest-module-prompt").value.trim();
  if (!name || !prompt) throw new Error("Module name and guest prompt are required.");
  const order = Number($("guest-module-order").value || 0);
  if (!Number.isInteger(order) || order < 0 || order > 99) throw new Error("Menu order must be a whole number from 0 to 99.");
  const id = $("guest-module-id").value || `module_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
  const modules = [...(state.property.guest_modules || [])]; const record = { id, name, prompt, order, enabled: $("guest-module-enabled").checked };
  const index = modules.findIndex((item) => item.id === id); if (index >= 0) modules[index] = record; else modules.push(record);
  state.property.guest_modules = modules; await savePropertyBasics(); clearGuestModuleForm(); renderGuestModules(); showToast("Guest menu action saved.");
}

async function toggleGuestModule(id) { state.property.guest_modules = (state.property.guest_modules || []).map((item) => item.id === id ? { ...item, enabled: item.enabled === false } : item); await savePropertyBasics(); renderGuestModules(); showToast("Guest menu action updated."); }
async function deleteGuestModule(id) { state.property.guest_modules = (state.property.guest_modules || []).filter((item) => item.id !== id); await savePropertyBasics(); if ($("guest-module-id").value === id) clearGuestModuleForm(); renderGuestModules(); showToast("Guest menu action deleted."); }

async function loadHospitalityManagement() {
  state.hospitality = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/hospitality`);
  renderFacilities(); renderRestaurants();
}

function renderFacilities() {
  const list = $("facility-list"); if (!list) return; list.replaceChildren();
  const query = $("facility-search").value.trim().toLocaleLowerCase();
  const facilities = (state.hospitality?.facilities || []).filter((item) =>
    [item.name, item.facility_type, item.status_note, item.description]
      .some((value) => String(value || "").toLocaleLowerCase().includes(query))
  );
  const empty = !(state.hospitality?.facilities || []).length;
  $("facility-empty").hidden = !empty;
  $("facility-table-shell").hidden = empty;
  $("facility-search").hidden = empty;
  $("facility-empty-copy").textContent = can("properties.edit")
    ? "Add a facility when you are ready to share its details with guests."
    : "No facilities have been configured for this property.";
  $("facility-table-shell").querySelector("thead th:last-child").hidden = !can("properties.edit");
  $("facility-count").textContent = empty ? "" : `${facilities.length} ${facilities.length === 1 ? "facility" : "facilities"}`;
  if (!empty && !facilities.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6; cell.className = "table-empty"; cell.textContent = "No facilities match your search.";
    row.appendChild(cell); list.appendChild(row); return;
  }
  for (const item of facilities) {
    const row = document.createElement("tr");
    const values = [item.name, item.facility_type, item.status_note, item.opening_hours?.display || "Not set"];
    for (const value of values) {
      const cell = document.createElement("td"); cell.textContent = value || "—"; row.appendChild(cell);
    }
    const status = document.createElement("td"); status.textContent = String(item.live_status || "unknown").replaceAll("_", " "); row.appendChild(status);
    const actions = document.createElement("td"); actions.className = "facility-actions"; actions.hidden = !can("properties.edit");
    if (can("properties.edit")) {
      const edit = document.createElement("button"); edit.type = "button"; edit.className = "btn btn-secondary btn-sm"; edit.textContent = "Edit"; edit.addEventListener("click", () => editFacility(item));
      const remove = document.createElement("button"); remove.type = "button"; remove.className = "btn btn-danger btn-sm"; remove.textContent = "Delete";
      remove.addEventListener("click", () => deleteFacility(item.facility_id, item.name).catch((error) => showToast(error.message, "error")));
      actions.append(edit, remove);
    }
    row.appendChild(actions); list.appendChild(row);
  }
}

function editFacility(item) {
  $("facility-form").reset();
  $("facility-dialog-title").textContent = "Edit Facility";
  $("facility-id").value = item.facility_id; $("facility-name").value = item.name; $("facility-type").value = item.facility_type; $("facility-location").value = item.status_note || ""; $("facility-hours").value = item.opening_hours?.display || ""; $("facility-status").value = item.live_status; $("facility-description").value = item.description || "";
  $("facility-dialog-message").textContent = "";
  $("facility-dialog").showModal();
  $("facility-name").focus();
}

function openNewFacility() {
  $("facility-form").reset();
  $("facility-dialog-title").textContent = "Add Facility";
  $("facility-id").value = "";
  $("facility-dialog-message").textContent = "";
  $("facility-dialog").showModal();
  $("facility-name").focus();
}

async function saveFacility(event) {
  event.preventDefault();
  const name = $("facility-name").value.trim(); if (!name) throw new Error("Facility name is required.");
  const submit = $("save-facility"); submit.disabled = true;
  try {
    await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/hospitality/facilities`, { method: "PUT", body: JSON.stringify({ data: { facility_id: $("facility-id").value || undefined, name, facility_type: $("facility-type").value.trim() || "amenity", opening_hours: { display: $("facility-hours").value.trim() }, description: $("facility-description").value.trim(), live_status: $("facility-status").value, status_note: $("facility-location").value.trim() } }) });
    $("facility-dialog").close(); await loadHospitalityManagement(); showToast("Facility saved.");
  } catch (error) {
    $("facility-dialog-message").textContent = error.message;
  } finally { submit.disabled = false; }
}

async function deleteFacility(id, name) {
  if (!window.confirm(`Delete ${name}? This cannot be undone.`)) return;
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/hospitality/facilities/${encodeURIComponent(id)}`, { method: "DELETE" });
  await loadHospitalityManagement(); showToast("Facility deleted.");
}

function renderRestaurants() {
  const list = $("restaurant-list"); if (!list) return; list.replaceChildren();
  const activeRestaurants = (state.hospitality?.restaurants || []).filter((item) => !item.archived && item.status !== "archived");
  const query = $("restaurant-search")?.value.trim().toLocaleLowerCase() || "";
  const restaurants = activeRestaurants.filter((item) => [item.name, item.location, item.cuisine, item.status, ...(item.meal_periods || [])]
    .some((value) => String(value || "").toLocaleLowerCase().includes(query)));
  const isEmpty = activeRestaurants.length === 0;
  $("restaurant-empty").hidden = !isEmpty;
  $("restaurant-search").hidden = isEmpty;
  $("restaurant-count").textContent = isEmpty ? "" : `${restaurants.length} of ${activeRestaurants.length} ${activeRestaurants.length === 1 ? "restaurant" : "restaurants"}`;
  list.hidden = isEmpty;
  const workflowSelect = $("restaurant-workflow-select");
  const previousRestaurantId = workflowSelect?.value;
  const facilitySelect = $("restaurant-facility");
  if (facilitySelect) {
    const previousFacilityId = facilitySelect.value;
    facilitySelect.replaceChildren(new Option("No linked facility", ""));
    for (const facility of state.hospitality?.facilities || []) facilitySelect.appendChild(new Option(facility.name, facility.facility_id));
    facilitySelect.value = previousFacilityId;
  }
  if (workflowSelect) {
    workflowSelect.replaceChildren();
    for (const restaurant of activeRestaurants) workflowSelect.appendChild(new Option(restaurant.name, restaurant.restaurant_id));
    if (activeRestaurants.some((item) => item.restaurant_id === previousRestaurantId)) workflowSelect.value = previousRestaurantId;
  }
  if (!isEmpty && !restaurants.length) {
    const noResults = document.createElement("div"); noResults.className = "compact-row restaurant-directory-row"; noResults.textContent = "No restaurants match your search."; list.appendChild(noResults);
  }
  for (const item of restaurants) {
    const row = document.createElement("article"); row.className = "compact-row restaurant-directory-row";
    const details = document.createElement("div"); details.className = "restaurant-directory-details";
    const title = document.createElement("div"); title.className = "restaurant-directory-title";
    const name = document.createElement("strong"); name.textContent = item.name;
    const status = document.createElement("small"); status.textContent = String(item.status || "unknown").replaceAll("_", " ");
    title.append(name, status);
    const summary = document.createElement("span");
    summary.textContent = [item.location || "Location not set", item.cuisine, (item.meal_periods || []).join(", ")].filter(Boolean).join(" · ");
    const hours = document.createElement("span"); hours.textContent = `Hours: ${item.opening_hours?.display || "Not set"}`;
    details.append(title, summary, hours);
    const actions = document.createElement("div"); actions.className = "restaurant-directory-actions";
    if (can("restaurant.manage")) {
      actions.append(makeActionButton("Edit", () => editRestaurant(item)));
      if (can("properties.edit")) {
        actions.append(makeActionButton("Delete", () => deleteRestaurant(item.restaurant_id, item.name), true));
      }
    }
    row.append(details, actions); list.appendChild(row);
  }
  if ($("restaurant-workflow-disclosure").open) {
    if (workflowSelect?.value) loadRestaurantWorkflows().catch((error) => showToast(error.message, "error"));
    else { state.restaurantMenus = []; state.restaurantPromotions = []; state.restaurantAnalytics = null; renderRestaurantWorkflows(); }
  }
}

function editRestaurant(item) {
  $("restaurant-dialog-title").textContent = "Edit Restaurant";
  $("restaurant-form").reset();
  $("restaurant-id").value = item.restaurant_id; $("restaurant-name").value = item.name; $("restaurant-location").value = item.location || ""; $("restaurant-hours").value = item.opening_hours?.display || ""; $("restaurant-meals").value = (item.meal_periods || []).join(", "); $("restaurant-status").value = item.status; $("restaurant-description").value = item.description || ""; $("restaurant-reservations").checked = item.reservation_available;
  for (const day of ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]) $("restaurant-hours-" + day).value = item.opening_hours?.[day] || "";
  $("restaurant-facility").value = item.facility_id || ""; $("restaurant-cuisine").value = item.cuisine || ""; $("restaurant-dress-code").value = item.dress_code || ""; $("restaurant-capacity").value = item.capacity || ""; $("restaurant-phone-extension").value = item.phone_extension || ""; $("restaurant-reservation-url").value = item.external_reservation_url || ""; $("restaurant-contact-email").value = item.contact_details?.email || ""; $("restaurant-contact-phone").value = item.contact_details?.phone || ""; $("restaurant-contact-website").value = item.contact_details?.website || ""; $("restaurant-images").value = (item.images || []).join(", "); $("restaurant-guest-notes").value = item.guest_notes || ""; $("restaurant-internal-notes").value = item.internal_notes || "";
  $("save-restaurant").textContent = "Save Changes";
  $("restaurant-dialog").showModal();
  $("restaurant-name").focus();
}

function openNewRestaurant() {
  $("restaurant-form").reset();
  $("restaurant-id").value = "";
  $("restaurant-dialog-title").textContent = "Add Restaurant";
  $("save-restaurant").textContent = "Add Restaurant";
  $("restaurant-dialog").showModal();
  $("restaurant-name").focus();
}

async function saveRestaurant() {
  const name = $("restaurant-name").value.trim(); if (!name) throw new Error("Restaurant name is required.");
  const id = $("restaurant-id").value;
  if (!id && !can("properties.edit")) throw new Error("Only a property administrator can add a restaurant.");
  const submit = $("save-restaurant"); submit.disabled = true;
  const openingHours = { display: $("restaurant-hours").value.trim() };
  for (const day of ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]) {
    const hours = $("restaurant-hours-" + day).value.trim();
    if (hours) openingHours[day] = hours;
  }
  const data = { facility_id: $("restaurant-facility").value || null, name, location: $("restaurant-location").value.trim(), opening_hours: openingHours, meal_periods: $("restaurant-meals").value.split(",").map((item) => item.trim()).filter(Boolean), status: $("restaurant-status").value, description: $("restaurant-description").value.trim(), reservation_available: $("restaurant-reservations").checked, cuisine: $("restaurant-cuisine").value.trim(), dress_code: $("restaurant-dress-code").value.trim(), capacity: $("restaurant-capacity").value ? Number($("restaurant-capacity").value) : null, phone_extension: $("restaurant-phone-extension").value.trim(), external_reservation_url: $("restaurant-reservation-url").value.trim(), contact_details: { email: $("restaurant-contact-email").value.trim(), phone: $("restaurant-contact-phone").value.trim(), website: $("restaurant-contact-website").value.trim() }, images: $("restaurant-images").value.split(",").map((item) => item.trim()).filter(Boolean), guest_notes: $("restaurant-guest-notes").value.trim(), internal_notes: $("restaurant-internal-notes").value.trim() };
  try {
    await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/restaurants${id ? `/${encodeURIComponent(id)}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify({ data }) });
    $("restaurant-dialog").close(); await loadHospitalityManagement(); showToast("Restaurant saved.");
  } finally { submit.disabled = false; }
}

async function deleteRestaurant(id, name) {
  if (!window.confirm(`Delete ${name} from the active restaurant list? Historical audit records will be retained.`)) return;
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/restaurants/${encodeURIComponent(id)}`, { method: "DELETE" });
  await loadHospitalityManagement(); showToast("Restaurant removed from the active list.");
}

async function loadRestaurantWorkflows() {
  const restaurantId = $("restaurant-workflow-select")?.value;
  if (!restaurantId) { state.restaurantMenus = []; state.restaurantPromotions = []; state.restaurantAnalytics = null; renderRestaurantWorkflows(); return; }
  const base = `/api/admin/properties/${encodeURIComponent(currentPropertyId())}/restaurants/${encodeURIComponent(restaurantId)}`;
  const requests = [jsonFetch(`${base}/menus`), jsonFetch(`${base}/promotions`)];
  if (can("restaurant.analytics.view")) requests.push(jsonFetch(`${base}/analytics`));
  const [menus, promotions, analytics] = await Promise.all(requests);
  state.restaurantMenus = menus.menus || [];
  state.restaurantPromotions = promotions.promotions || [];
  state.restaurantAnalytics = analytics || null;
  renderRestaurantWorkflows();
}

function renderRestaurantWorkflows() {
  const menuList = $("restaurant-menu-list");
  const menuSelect = $("restaurant-menu-select");
  const promotionList = $("restaurant-promotion-list");
  const analytics = $("restaurant-analytics");
  if (!menuList || !menuSelect || !promotionList) return;
  const previousMenuId = menuSelect.value;
  menuList.replaceChildren(); menuSelect.replaceChildren(); promotionList.replaceChildren();
  for (const menu of state.restaurantMenus) menuSelect.appendChild(new Option(`${menu.name} · ${menu.workflow_status}`, menu.menu_id));
  if (state.restaurantMenus.some((menu) => menu.menu_id === previousMenuId)) menuSelect.value = previousMenuId;
  for (const menu of state.restaurantMenus) {
    const row = document.createElement("div"); row.className = "compact-row";
    row.innerHTML = `<strong>${escapeHTML(menu.name)}</strong><span>${escapeHTML(menu.meal_period)} · ${escapeHTML(menu.workflow_status)}</span><span>${menu.items?.length || 0} item(s) · ${menu.active ? "active" : "inactive"}</span>`;
    if (can("restaurant.menu.edit")) row.append(makeActionButton("Edit", () => editRestaurantMenu(menu), true));
    if (menu.workflow_status === "pending_approval" && can("restaurant.menu.approve")) row.append(makeActionButton("Approve", () => approveRestaurantWorkflow("menus", menu.menu_id, "approve"), true));
    if (menu.workflow_status === "approved" && can("restaurant.menu.approve")) row.append(makeActionButton("Publish", () => approveRestaurantWorkflow("menus", menu.menu_id, "publish")));
    menuList.appendChild(row);
    for (const item of menu.items || []) {
      const itemRow = document.createElement("div"); itemRow.className = "compact-row menu-item-row";
      itemRow.innerHTML = `<strong>${escapeHTML(item.name)}</strong><span>${escapeHTML(item.price || "No price")} · ${item.available ? "available" : "unavailable"}</span><span>${escapeHTML(item.description || "")}${item.allergens?.length ? ` · Allergens: ${escapeHTML(item.allergens.join(", "))}` : ""}</span>`;
      if (can("restaurant.menu.edit")) itemRow.append(makeActionButton("Edit item", () => editRestaurantMenuItem(menu, item), true));
      menuList.appendChild(itemRow);
    }
  }
  for (const promotion of state.restaurantPromotions) {
    const row = document.createElement("div"); row.className = "compact-row";
    row.innerHTML = `<strong>${escapeHTML(promotion.title)}</strong><span>${escapeHTML(promotion.status)}</span><span>${escapeHTML(promotion.description || "")}</span>`;
    if (can("restaurant.promotions.edit")) row.append(makeActionButton("Edit", () => editRestaurantPromotion(promotion), true));
    if (promotion.status === "pending_approval" && can("restaurant.promotions.approve")) row.append(makeActionButton("Approve", () => approveRestaurantWorkflow("promotions", promotion.promotion_id, "approve"), true));
    if (promotion.status === "approved" && can("restaurant.promotions.approve")) row.append(makeActionButton("Publish", () => approveRestaurantWorkflow("promotions", promotion.promotion_id, "publish")));
    promotionList.appendChild(row);
  }
  if (!menuList.children.length) menuList.textContent = "No menus configured.";
  if (!promotionList.children.length) promotionList.textContent = "No promotions configured.";
  if (analytics) {
    analytics.replaceChildren();
    for (const [label, value] of Object.entries({ conversations: "conversations", waiting_for_staff: "waiting", human_active: "staff handling", completed: "completed", menus: "menus", promotions: "promotions" })) {
      const item = document.createElement("div"); item.className = "metric-card"; item.innerHTML = `<strong>${Number(state.restaurantAnalytics?.[label] || 0)}</strong><span>${escapeHTML(value)}</span>`; analytics.appendChild(item);
    }
  }
}

async function saveRestaurantMenu() {
  const restaurantId = $("restaurant-workflow-select").value;
  const name = $("restaurant-menu-name").value.trim();
  if (!restaurantId || !name) throw new Error("Select a restaurant and enter a menu name.");
  const menuId = $("restaurant-menu-edit-id").value;
  const endpoint = menuId ? `/api/admin/properties/${encodeURIComponent(currentPropertyId())}/menus/${encodeURIComponent(menuId)}` : `/api/admin/properties/${encodeURIComponent(currentPropertyId())}/restaurants/${encodeURIComponent(restaurantId)}/menus`;
  await jsonFetch(endpoint, { method: menuId ? "PUT" : "POST", body: JSON.stringify({ data: { name, meal_period: $("restaurant-menu-period").value.trim() || "all_day" } }) });
  $("restaurant-menu-edit-id").value = ""; $("restaurant-menu-name").value = ""; $("restaurant-menu-period").value = ""; $("save-restaurant-menu").textContent = "Add Menu"; await loadRestaurantWorkflows(); showToast("Menu submitted for approval.");
}

function editRestaurantMenu(menu) {
  $("restaurant-menu-edit-id").value = menu.menu_id;
  $("restaurant-menu-name").value = menu.name;
  $("restaurant-menu-period").value = menu.meal_period;
  $("save-restaurant-menu").textContent = "Save Menu";
}

function editRestaurantMenuItem(menu, item) {
  $("restaurant-menu-select").value = menu.menu_id;
  $("restaurant-item-edit-id").value = item.item_id;
  $("restaurant-item-name").value = item.name;
  $("restaurant-item-description").value = item.description || "";
  $("restaurant-item-price").value = item.price || "";
  $("restaurant-item-allergens").value = (item.allergens || []).join(", ");
  $("restaurant-item-available").checked = item.available !== false;
  $("save-restaurant-menu-item").textContent = "Save Menu Item";
}

function editRestaurantPromotion(promotion) {
  const localDateTime = (timestamp) => {
    if (!timestamp) return "";
    const date = new Date(Number(timestamp) * 1000);
    date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
    return date.toISOString().slice(0, 16);
  };
  $("restaurant-promotion-edit-id").value = promotion.promotion_id;
  $("restaurant-promotion-title").value = promotion.title;
  $("restaurant-promotion-description").value = promotion.description || "";
  $("restaurant-promotion-start").value = localDateTime(promotion.starts_at);
  $("restaurant-promotion-end").value = localDateTime(promotion.ends_at);
  $("save-restaurant-promotion").textContent = "Save and Resubmit";
}

async function saveRestaurantMenuItem() {
  const menuId = $("restaurant-menu-select").value;
  const name = $("restaurant-item-name").value.trim();
  if (!menuId || !name) throw new Error("Select a menu and enter a menu item name.");
  const itemId = $("restaurant-item-edit-id").value;
  const data = { name, description: $("restaurant-item-description").value.trim(), price: $("restaurant-item-price").value.trim(), allergens: $("restaurant-item-allergens").value.split(",").map((item) => item.trim()).filter(Boolean), available: $("restaurant-item-available").checked };
  const endpoint = itemId ? `/api/admin/properties/${encodeURIComponent(currentPropertyId())}/menu-items/${encodeURIComponent(itemId)}` : `/api/admin/properties/${encodeURIComponent(currentPropertyId())}/menus/${encodeURIComponent(menuId)}/items`;
  await jsonFetch(endpoint, { method: itemId ? "PUT" : "POST", body: JSON.stringify({ data }) });
  $("restaurant-item-edit-id").value = ""; $("restaurant-item-name").value = ""; $("restaurant-item-description").value = ""; $("restaurant-item-price").value = ""; $("restaurant-item-allergens").value = ""; $("restaurant-item-available").checked = true; $("save-restaurant-menu-item").textContent = "Add Menu Item"; await loadRestaurantWorkflows(); showToast("Menu item submitted for approval.");
}

async function saveRestaurantPromotion() {
  const restaurantId = $("restaurant-workflow-select").value;
  const title = $("restaurant-promotion-title").value.trim();
  if (!restaurantId || !title) throw new Error("Select a restaurant and enter a promotion title.");
  const toUnixSeconds = (value) => value ? Math.floor(new Date(value).getTime() / 1000) : null;
  const promotionId = $("restaurant-promotion-edit-id").value;
  const endpoint = promotionId ? `/api/admin/properties/${encodeURIComponent(currentPropertyId())}/promotions/${encodeURIComponent(promotionId)}` : `/api/admin/properties/${encodeURIComponent(currentPropertyId())}/restaurants/${encodeURIComponent(restaurantId)}/promotions`;
  await jsonFetch(endpoint, { method: promotionId ? "PUT" : "POST", body: JSON.stringify({ data: { title, description: $("restaurant-promotion-description").value.trim(), starts_at: toUnixSeconds($("restaurant-promotion-start").value), ends_at: toUnixSeconds($("restaurant-promotion-end").value) } }) });
  $("restaurant-promotion-edit-id").value = ""; $("restaurant-promotion-title").value = ""; $("restaurant-promotion-description").value = ""; $("restaurant-promotion-start").value = ""; $("restaurant-promotion-end").value = ""; $("save-restaurant-promotion").textContent = "Submit for Approval"; await loadRestaurantWorkflows(); showToast("Promotion submitted for approval.");
}

async function approveRestaurantWorkflow(resource, id, action) {
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/${resource}/${encodeURIComponent(id)}/${action}`, { method: "POST" });
  await loadRestaurantWorkflows(); showToast(`${resource === "menus" ? "Menu" : "Promotion"} ${action}d.`);
}

async function loadKnowledge() {
  const base = `/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge`;
  const [legacy, managed, health] = await Promise.all([jsonFetch(base), jsonFetch(`${base}/managed`), jsonFetch(`${base}/health`)]);
  state.knowledge = legacy;
  state.managedKnowledge = managed;
  state.knowledgeHealth = health;
  renderKnowledge();
}

function makeActionButton(label, handler, secondary = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  const destructive = /delete|remove|archive/i.test(label);
  button.className = `btn ${destructive ? "btn-danger" : secondary ? "btn-ghost" : "btn-secondary"} btn-sm`;
  button.addEventListener("click", () => Promise.resolve(handler()).catch((error) => showToast(error.message, "error")));
  return button;
}

function renderKnowledge() {
  const health = state.knowledgeHealth;
  if (health && $("knowledge-health")) $("knowledge-health").textContent = `${health.coverage_percent}% coverage · ${health.pending_review} pending review · ${health.open_conflicts} open conflicts · ${health.expired_items} expired items. Missing categories: ${health.missing_categories.join(", ") || "none"}. Missing facts: ${health.missing_fields.join(", ") || "none"}.`;
  renderManagedKnowledge();
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
  if (!entryList.children.length) entryList.textContent = "No hotel knowledge has been added.";

  const documentList = $("document-list"); documentList.innerHTML = "";
  for (const item of state.knowledge.documents || []) {
    const row = document.createElement("div"); row.className = "compact-row";
    row.innerHTML = `<strong>${escapeHTML(item.source_name || item.title)}</strong><span>${escapeHTML(item.status)} · ${escapeHTML(item.content_type || "unknown type")}</span><span>${escapeHTML(item.error || "Ready for verified retrieval")}</span>`;
    row.append(makeActionButton("Delete", () => deleteKnowledgeItem(item.item_id), true)); documentList.appendChild(row);
  }
  for (const source of state.managedKnowledge.sources || []) {
    const row = document.createElement("div"); row.className = "compact-row";
    row.innerHTML = `<strong>${escapeHTML(source.filename)}</strong><span>${escapeHTML(source.status.replaceAll("_", " "))} · version ${source.version}${source.previous_source_id ? ` · replaces ${escapeHTML(source.previous_source_id.slice(0, 8))}` : ""} · ${escapeHTML(source.extension)} · ${escapeHTML(formatDate(source.created_at))}</span><span>${escapeHTML(source.error || "Review extracted knowledge before publishing.")}</span>`;
    row.append(makeActionButton("Review", () => { activatePanel("knowledge"); document.querySelector(`[data-source-id="${source.source_id}"]`)?.scrollIntoView({ block: "center" }); }));
    row.append(makeActionButton("Versions", async () => {
      const history = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge/sources/${source.source_id}/versions`);
      showToast(history.versions.map((version) => `v${version.version} ${version.filename} (${version.status})`).join(" → "));
    }, true));
    if (can("knowledge.edit")) {
      row.append(makeActionButton("Download original", () => window.location.assign(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge/sources/${source.source_id}/download`), true));
      if (source.status === "processing_failed") row.append(makeActionButton("Retry", async () => { await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge/sources/${source.source_id}/retry`, { method: "POST" }); await loadKnowledge(); }, true));
      row.append(makeActionButton("Replace", async () => {
        if (!window.confirm(`Upload a new version of ${source.filename}? The previous version remains active until you supersede it.`)) return;
        const picker = document.createElement("input"); picker.type = "file"; picker.accept = ".pdf,.docx,.xlsx,.csv,.txt,.md,.json,.pptx,.png,.jpg,.jpeg,.webp";
        picker.addEventListener("change", async () => { if (picker.files?.[0]) try { await uploadKnowledgeDocument(picker.files[0], () => {}, `/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge/sources/${source.source_id}/replace`); } catch (error) { showToast(error.message, "error"); } });
        picker.click();
      }, true));
    }
    if (source.previous_source_id && can("knowledge.publish") && source.status === "ready_review") row.append(makeActionButton("Supersede previous", async () => {
      if (!window.confirm("Archive the previous document version and remove its published knowledge from Guest AI?")) return;
      await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge/sources/${source.source_id}/supersede`, { method: "POST" }); await loadKnowledge();
    }, true));
    if (can("knowledge.delete")) row.append(makeActionButton("Delete source", async () => { if (!window.confirm(`Permanently delete ${source.filename} and all derived knowledge?`)) return; await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge/sources/${source.source_id}`, { method: "DELETE" }); await loadKnowledge(); }, true));
    documentList.appendChild(row);
  }
  if (!documentList.children.length) documentList.textContent = "No knowledge documents uploaded yet.";

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
  if (!faqList.children.length) faqList.textContent = "No FAQs configured yet.";
}

function renderManagedKnowledge() {
  const target = $("managed-knowledge-list");
  if (!target) return;
  target.replaceChildren();
  const query = $("managed-knowledge-search")?.value.trim().toLowerCase() || "";
  const items = (state.managedKnowledge.items || []).filter((item) => !query || `${item.title} ${item.content}`.toLowerCase().includes(query));
  for (const item of items) {
    const row = document.createElement("article"); row.className = "compact-row knowledge-review"; row.dataset.sourceId = item.source_id || "";
    const source = state.managedKnowledge.sources.find((candidate) => candidate.source_id === item.source_id);
    row.innerHTML = `<strong>${escapeHTML(item.title)}</strong><span>${escapeHTML(item.category)} · ${escapeHTML(item.status.replaceAll("_", " "))} · ${escapeHTML(item.visibility)}${item.conflict ? " · Conflict" : ""}${item.risk_flags?.length ? ` · Review: ${escapeHTML(item.risk_flags.join(", "))}` : ""}</span><span>${escapeHTML(source?.filename || "Admin Knowledge Entry")} · ${escapeHTML(JSON.stringify(item.location))}</span><p>${escapeHTML(item.content)}</p>`;
    const details = document.createElement("div"); details.className = "knowledge-review-details"; details.hidden = true;
    const title = document.createElement("input"); title.value = item.title; title.setAttribute("aria-label", "Knowledge title");
    const content = document.createElement("textarea"); content.value = item.content; content.rows = 4; content.setAttribute("aria-label", "Knowledge content");
    const category = document.createElement("select"); category.setAttribute("aria-label", "Knowledge category");
    for (const value of state.managedKnowledge.categories || []) { const option = document.createElement("option"); option.value = value; option.textContent = value; category.append(option); } category.value = item.category;
    const visibility = document.createElement("select"); visibility.setAttribute("aria-label", "Knowledge visibility");
    for (const [value, label] of [["admin", "Admin Only"], ["guest", "Guest + Admin"], ["manager", "Manager Only"], ["engineering", "Engineering Only"], ["staff", "Staff Only"]]) { const option = document.createElement("option"); option.value = value; option.textContent = label; visibility.append(option); } visibility.value = item.visibility;
    const effective = document.createElement("input"); effective.type = "date"; effective.setAttribute("aria-label", "Effective date"); if (item.effective_at) effective.value = new Date(item.effective_at * 1000).toISOString().slice(0, 10);
    const expires = document.createElement("input"); expires.type = "date"; expires.setAttribute("aria-label", "Expiration date"); if (item.expires_at) expires.value = new Date(item.expires_at * 1000).toISOString().slice(0, 10);
    details.append(title, content, category, visibility, effective, expires);
    const base = `/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge/items/${item.item_id}`;
    if (can("knowledge.edit") && item.status !== "published") details.append(makeActionButton("Save changes", async () => {
      await jsonFetch(base, { method: "PATCH", body: JSON.stringify({ title: title.value, content: content.value, category: category.value, visibility: visibility.value, effective_at: effective.value ? Math.floor(Date.parse(`${effective.value}T00:00:00Z`) / 1000) : null, expires_at: expires.value ? Math.floor(Date.parse(`${expires.value}T00:00:00Z`) / 1000) : null }) }); await loadKnowledge();
    }));
    row.append(makeActionButton("Review", () => { details.hidden = !details.hidden; }));
    if (can("knowledge.publish")) {
      if (item.status === "ready_review") row.append(makeActionButton("Approve", () => transitionKnowledge(item.item_id, "approve")));
      if (item.status === "approved") row.append(makeActionButton("Publish", () => transitionKnowledge(item.item_id, "publish")));
      if (item.status === "published") row.append(makeActionButton("Unpublish", () => transitionKnowledge(item.item_id, "unpublish"), true));
      if (item.status !== "archived") row.append(makeActionButton("Archive", () => transitionKnowledge(item.item_id, "archive"), true));
    }
    row.append(details); target.append(row);
  }
  if (!items.length) target.textContent = "No matching extracted knowledge.";
}

async function transitionKnowledge(itemId, action) {
  if (["publish", "archive", "unpublish"].includes(action) && !window.confirm(`${action[0].toUpperCase() + action.slice(1)} this knowledge item?`)) return;
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge/items/${itemId}/${action}`, { method: "POST" });
  await loadKnowledge();
}

async function saveKnowledgeEntry() {
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge`, { method: "PUT", body: JSON.stringify({ item_id: $("knowledge-id").value || null, kind: "entry", title: $("knowledge-title").value.trim(), body: $("knowledge-body").value.trim(), enabled: $("knowledge-enabled").checked }) });
  $("knowledge-id").value = ""; $("knowledge-title").value = ""; $("knowledge-body").value = ""; await loadKnowledge(); showToast("Knowledge entry saved.");
}

async function saveFAQ() {
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge`, { method: "PUT", body: JSON.stringify({ item_id: $("faq-id").value || null, kind: "faq", question: $("faq-question").value.trim(), answer: $("faq-answer").value.trim(), enabled: $("faq-enabled").checked }) });
  $("faq-id").value = ""; $("faq-question").value = ""; $("faq-answer").value = ""; await loadKnowledge(); showToast("FAQ saved.");
}

async function uploadKnowledgeDocument(file, onProgress = () => {}, endpoint = null) {
  if (!file) return;
  const content = new Uint8Array(await file.arrayBuffer()); let binary = "";
  for (let offset = 0; offset < content.length; offset += 8192) binary += String.fromCharCode(...content.subarray(offset, offset + 8192));
  const body = JSON.stringify({ filename: file.name, content_type: file.type || "application/octet-stream", content_base64: btoa(binary) });
  const item = await new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", endpoint || `/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge/sources`);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.setRequestHeader("X-CSRF-Token", state.auth?.csrf_token || "");
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) onProgress(Math.round(100 * event.loaded / event.total)); };
    xhr.onload = () => { const payload = JSON.parse(xhr.responseText || "{}"); if (xhr.status >= 200 && xhr.status < 300) resolve(payload); else reject(new Error(payload.detail || "Upload failed.")); };
    xhr.onerror = () => reject(new Error("Upload failed. Check your connection and retry."));
    xhr.send(body);
  });
  await loadKnowledge(); showToast(`${item.filename} queued for review.`);
  return item;
}

function addHotelAIFiles(files) {
  if (!can("knowledge.edit") && !can("restaurant.menu.edit")) { showToast("Permission required: knowledge.edit or restaurant.menu.edit", "error"); return; }
  const limit = state.managedKnowledge.limits?.max_files_per_upload || 5;
  for (const file of files) {
    if (state.hotelAIFiles.length >= limit) { showToast(`Choose up to ${limit} files per message.`, "error"); break; }
    if (!state.hotelAIFiles.some((candidate) => candidate.name === file.name && candidate.size === file.size)) state.hotelAIFiles.push(file);
  }
  renderHotelAIFiles();
}

function renderHotelAIFiles() {
  const target = $("assistant-attachments"); target.replaceChildren();
  for (const [index, file] of state.hotelAIFiles.entries()) {
    const chip = document.createElement("span"); chip.className = "knowledge-file-chip";
    chip.textContent = `${file.name} (${Math.ceil(file.size / 1024)} KB)`;
    chip.append(makeActionButton("Remove", () => { state.hotelAIFiles.splice(index, 1); renderHotelAIFiles(); }, true));
    target.append(chip);
  }
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
  $("guardrail-allowed").value = (guardrails.allowed_topics || []).join("\n");
  $("guardrail-restricted").value = (guardrails.restricted_topics || []).join("\n");
  $("guardrail-sensitive").value = guardrails.sensitive_information || "Never expose credentials, payment data, private guest records, or infrastructure identifiers.";
  $("guardrail-network-only").checked = guardrails.guest_network_only !== false;
  $("guardrail-cidrs").value = (guardrails.allowed_cidrs || ["127.0.0.0/8", "::1/128"]).join("\n");
  $("guardrail-proxies").value = (guardrails.trusted_proxy_ranges || []).join("\n");
  $("guardrail-revalidation").value = guardrails.session_network_revalidation || "suspend";
  $("guardrail-timeout").value = guardrails.guest_session_timeout || 30;
  $("guardrail-antlabs").checked = Boolean(guardrails.antlabs_gateway_enabled);
  $("guardrail-antlabs-ranges").value = (guardrails.antlabs_gateway_ranges || []).join("\n");
  $("guardrail-antlabs-secret").value = "";
  $("guardrail-antlabs-secret").placeholder = guardrails.antlabs_signature_configured ? "Saved securely; leave blank to keep" : "Not configured";
  $("guardrail-internet").checked = guardrails.internet_search_enabled !== false;
  $("guardrail-directions").checked = guardrails.directions_enabled !== false;
  $("guardrail-restaurants").checked = guardrails.restaurant_search_enabled !== false;
  $("guardrail-attractions").checked = guardrails.attractions_enabled !== false;
  $("guardrail-weather").checked = guardrails.weather_enabled !== false;
  $("guardrail-services").checked = guardrails.service_requests_enabled !== false;
  $("guardrail-reservations").checked = Boolean(guardrails.reservations_enabled);
  $("guardrail-financial").checked = Boolean(guardrails.financial_actions_enabled);
  $("guardrail-location").checked = Boolean(guardrails.location_access_enabled);
  $("guardrail-audit").checked = guardrails.audit_logging_enabled !== false;
}

const readLines = (id) => $(id).value.split("\n").map((value) => value.trim()).filter(Boolean);

async function savePersonality() {
  state.property.personality = { name: $("personality-name").value.trim(), tone: $("personality-tone").value, formality: $("personality-formality").value, response_length: $("personality-length").value, greeting_behavior: $("personality-greeting").value, property_instructions: $("personality-instructions").value.trim() };
  state.property.concierge_name = state.property.personality.name || state.property.concierge_name; $("concierge-name-input").value = state.property.concierge_name;
  await savePropertyBasics(); showToast("AI personality saved.");
}

async function saveGuardrails() {
  const config = { ...state.property.guardrails, allowed_topics: readLines("guardrail-allowed"), restricted_topics: readLines("guardrail-restricted"), sensitive_information: $("guardrail-sensitive").value.trim(), guest_network_only: $("guardrail-network-only").checked, allowed_cidrs: readLines("guardrail-cidrs"), trusted_proxy_ranges: readLines("guardrail-proxies"), session_network_revalidation: $("guardrail-revalidation").value, guest_session_timeout: Number($("guardrail-timeout").value || 30), antlabs_gateway_enabled: $("guardrail-antlabs").checked, antlabs_gateway_ranges: readLines("guardrail-antlabs-ranges"), internet_search_enabled: $("guardrail-internet").checked, directions_enabled: $("guardrail-directions").checked, restaurant_search_enabled: $("guardrail-restaurants").checked, attractions_enabled: $("guardrail-attractions").checked, weather_enabled: $("guardrail-weather").checked, service_requests_enabled: $("guardrail-services").checked, reservations_enabled: $("guardrail-reservations").checked, financial_actions_enabled: $("guardrail-financial").checked, location_access_enabled: $("guardrail-location").checked, audit_logging_enabled: $("guardrail-audit").checked };
  const signingSecret = $("guardrail-antlabs-secret").value;
  if (signingSecret) config.antlabs_signature_secret = signingSecret;
  delete config.antlabs_signature_configured;
  const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/guardrails`, { method: "PUT", body: JSON.stringify({ config }) });
  state.property.guardrails = result.config; loadAIPolicy(); await loadGuardrailDiagnostics(); showToast("Guardrails saved and enforced.");
}

async function loadGuardrailDiagnostics() {
  const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/guardrails/diagnostics`);
  $("guardrail-diagnostic-ip").textContent = result.detected_client_ip || "Unavailable";
  $("guardrail-diagnostic-network").textContent = result.matched_network || "No match";
  $("guardrail-diagnostic-property").textContent = result.property_id;
  $("guardrail-diagnostic-proxy").textContent = result.trusted_proxy ? "Trusted forwarded address" : "Direct source address";
  $("guardrail-diagnostic-result").textContent = result.network_policy_result;
  $("guardrail-diagnostic-sessions").textContent = result.active_guest_sessions;
  renderNetworkSetupGuidance(result);
}

function renderNetworkSetupGuidance(result) {
  const status = $("network-setup-status");
  const addButton = $("trust-detected-ip");
  const hotelWifiCheck = $("confirm-hotel-wifi-test");
  if (!status || !addButton) return;
  const ip = result.detected_client_ip || "";
  status.className = "network-setup-status";
  addButton.hidden = true;
  addButton.dataset.ip = "";
  if (hotelWifiCheck) hotelWifiCheck.checked = false;
  if (!ip) {
    status.textContent = "Could not determine the client address. Check the server connection and refresh.";
    status.classList.add("warning");
    return;
  }
  const isPrivateVmAddress = /^(172\.(1[6-9]|2\d|3[01])|10\.|192\.168\.)/.test(ip);
  if (result.matched_network) {
    status.textContent = `This connection is allowed: ${ip} matches ${result.matched_network}. Test the guest page from a phone on hotel Wi-Fi to verify guest access.`;
    status.classList.add("success");
  } else if (isPrivateVmAddress) {
    status.textContent = `Concierge sees ${ip}, but it is a private network address and does not match your approved guest network. A VM, WSL, NAT, or proxy may be hiding the guest device address. Fix client-IP forwarding before allowing guests.`;
    status.classList.add("warning");
  } else {
    status.textContent = `Concierge sees ${ip}, which is not in an approved network. If this check was made from a test device on the hotel guest Wi-Fi, you can add this exact address as a /32 rule.`;
    status.classList.add("warning");
    addButton.dataset.ip = ip;
    status.textContent += isPrivateVmAddress ? " This is a private VM or proxy address, so it cannot be added here." : " Confirm the test device was on hotel guest Wi-Fi to enable the rule.";
  }
  if (!can("network.manage")) addButton.hidden = true;
  if ($("guardrail-antlabs")?.checked && !$("guardrail-antlabs-secret").value && $("guardrail-antlabs-secret").placeholder === "Not configured") {
    status.textContent += " Signed ANTlabs validation is enabled but no signing secret is configured; turn it off unless your gateway is set up to sign requests.";
    status.classList.add("warning");
  }
}

function addDetectedAddressRule() {
  const ip = $("trust-detected-ip")?.dataset.ip;
  if (!ip || !$("confirm-hotel-wifi-test")?.checked || !/^\d{1,3}(?:\.\d{1,3}){3}$/.test(ip)) return;
  const textarea = $("guardrail-cidrs");
  const rules = textarea.value.split("\n").map((line) => line.trim()).filter(Boolean);
  const rule = `${ip}/32`;
  if (!rules.includes(rule)) rules.push(rule);
  textarea.value = rules.join("\n");
  showToast(`Added ${rule}. Click Save Guardrails to apply it.`);
}

async function loadWebhooks() { state.webhooks = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/webhooks`); renderWebhooks(); }

function renderWebhooks() {
  const list = $("webhook-list"); list.innerHTML = "";
  for (const item of state.webhooks.webhooks || []) {
    const row = document.createElement("div"); row.className = "compact-row";
    row.innerHTML = `<strong>${escapeHTML(item.name)}</strong><span>${item.enabled ? "Enabled" : "Disabled"} · ${escapeHTML((item.last_status || "not tested").replaceAll("_", " "))}</span><span>${escapeHTML(item.endpoint_url)}${item.last_error ? ` · ${escapeHTML(item.last_error)}` : ""}</span>`;
    row.append(
      makeActionButton("Edit", () => editWebhook(item)),
      makeActionButton("Test", () => testWebhook(item.webhook_id)),
      makeActionButton("Delete", () => deleteWebhook(item.webhook_id), true),
    ); list.appendChild(row);
  }
  if (!list.children.length) list.textContent = "No webhook endpoints configured.";
  $("webhook-deliveries").innerHTML = (state.webhooks.deliveries || []).slice(0, 20).map((item) => `<div class="compact-row"><strong>${escapeHTML(item.event_name)}</strong><span>${escapeHTML(item.status)} · ${escapeHTML(formatDate(item.attempted_at))}</span><span>${escapeHTML(item.error || (item.response_status ? `HTTP ${item.response_status}` : ""))}</span></div>`).join("") || "No delivery attempts recorded.";
}

async function saveWebhook() {
  const events = [...$("webhook-events").selectedOptions].map((option) => option.value);
  const name = $("webhook-name").value.trim();
  const endpointUrl = $("webhook-url").value.trim();
  if (!name) throw new Error("Enter a name for this webhook.");
  if (!events.length) throw new Error("Select at least one event to send.");
  try {
    const parsed = new URL(endpointUrl);
    if (!["http:", "https:"].includes(parsed.protocol)) throw new Error();
  } catch {
    throw new Error("Enter a valid HTTP or HTTPS endpoint URL.");
  }
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/webhooks`, { method: "PUT", body: JSON.stringify({ webhook_id: $("webhook-id").value || null, name, endpoint_url: endpointUrl, events, enabled: $("webhook-enabled").checked, secret: $("webhook-secret").value }) });
  resetWebhookForm(); await loadWebhooks(); showToast("Webhook saved.");
}
async function testWebhook(id) { const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/webhooks/${encodeURIComponent(id)}/test`, { method: "POST" }); await loadWebhooks(); showToast(result.status === "delivered" ? "Webhook delivered." : result.error, result.status === "delivered" ? "default" : "error"); }
function editWebhook(item) {
  $("webhook-id").value = item.webhook_id;
  $("webhook-name").value = item.name;
  $("webhook-url").value = item.endpoint_url;
  $("webhook-enabled").checked = item.enabled;
  for (const option of $("webhook-events").options) option.selected = item.events.includes(option.value);
  $("webhook-secret").value = "";
  $("webhook-secret").placeholder = item.secret_configured ? "Saved securely; leave blank to keep" : "Optional signing secret";
  $("save-webhook").textContent = "Update Webhook";
  $("reset-webhook-form").hidden = false;
}
function resetWebhookForm() {
  $("webhook-id").value = "";
  $("webhook-name").value = "";
  $("webhook-url").value = "";
  $("webhook-secret").value = "";
  $("webhook-secret").placeholder = "Optional; leave blank to keep a saved secret";
  $("webhook-enabled").checked = true;
  for (const option of $("webhook-events").options) option.selected = false;
  $("save-webhook").textContent = "Save Webhook";
  $("reset-webhook-form").hidden = true;
}
async function deleteWebhook(id) {
  const item = (state.webhooks.webhooks || []).find((webhook) => webhook.webhook_id === id);
  if (!window.confirm(`Delete the webhook${item ? ` “${item.name}”` : ""}? This stops future event delivery.`)) return;
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/webhooks/${encodeURIComponent(id)}`, { method: "DELETE" });
  if ($("webhook-id").value === id) resetWebhookForm();
  await loadWebhooks(); showToast("Webhook deleted.");
}

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

function prettifyAccessStatus(value) {
  return String(value || "not_configured").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

async function loadNetworkAccess() {
  const data = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/network-access/status`);
  state.networkAccess = data;
  const management = data.management || {};
  const guest = data.guest || {};
  const managementStatus = prettifyAccessStatus(management.status);
  const guestStatus = prettifyAccessStatus(guest.status);
  const serverIp = management.server_ip || "Unavailable";
  const adminUrl = management.admin_url || "Unavailable";
  const guestDomain = guest.domain || "Not configured";
  const guestUrl = guest.url || "Not configured";
  const sslStatus = prettifyAccessStatus(guest.ssl_status);

  $("management-status").textContent = managementStatus;
  $("management-enabled-status").textContent = management.enabled ? "Enabled" : "Disabled";
  $("management-server-ip").textContent = serverIp;
  $("management-admin-url").textContent = adminUrl;
  $("management-interface").textContent = management.network_interface || "Unavailable";
  $("management-https-status").textContent = prettifyAccessStatus(management.https_status);
  $("management-port").textContent = management.port || "443";
  $("management-protection").textContent = prettifyAccessStatus(management.access_protection);
  $("management-allowed-network-view").textContent = (management.allowed_cidrs || []).join(", ") || "None configured";
  $("management-trusted-proxy-view").textContent = (management.trusted_proxy_ranges || []).join(", ") || "None configured";
  $("management-access-enabled").checked = Boolean(management.enabled);
  $("management-networks").value = (management.allowed_cidrs || []).join("\n");
  $("management-proxies").value = (management.trusted_proxy_ranges || []).join("\n");
  $("management-manage-controls").hidden = !can("network.manage") || !management.can_manage;
  $("management-readonly-note").hidden = !can("network.manage") || management.can_manage;
  $("management-rollback-note").hidden = !management.rollback_pending;
  $("management-access-warning").textContent = (management.unsafe_networks || []).length
    ? "Warning: a /0 or public network can expose Admin outside the hotel's private networks. Saving requires explicit confirmation."
    : ((management.overlaps_guest_networks || []).length ? "Warning: one or more management networks overlap the guest networks. Saving requires explicit confirmation." : "");
  $("finalize-management-access").hidden = !management.rollback_pending || !management.can_manage;

  $("guest-access-enabled").checked = guest.enabled !== false;
  $("deployment-domain").value = guest.domain || "";
  $("deployment-public-url").value = guest.url || "";
  $("network-reverse-proxy").checked = Boolean(guest.reverse_proxy);
  $("network-https-required").checked = guest.https_required !== false;
  $("guardrail-network-only").checked = guest.guest_network_only !== false;
  $("guardrail-cidrs").value = (guest.allowed_cidrs || []).join("\n");
  $("guardrail-proxies").value = (guest.trusted_proxy_ranges || []).join("\n");
  $("guardrail-revalidation").value = guest.session_network_revalidation || "suspend";
  $("guardrail-timeout").value = guest.guest_session_timeout || 30;
  $("guardrail-antlabs").checked = Boolean(guest.antlabs_gateway_enabled);
  $("guardrail-antlabs-ranges").value = (guest.antlabs_gateway_ranges || []).join("\n");
  $("guest-access-fields").disabled = !can("network.manage");
  $("domain-status").textContent = prettifyAccessStatus(guest.domain_status);
  $("domain-addresses").textContent = (guest.resolved_addresses || []).join(", ") || "—";
  $("deployment-last-checked").textContent = guest.last_checked_at ? formatDate(guest.last_checked_at) : "Never";
  $("ssl-status").textContent = sslStatus;
  $("ssl-issuer").textContent = guest.ssl_issuer || "—";
  $("ssl-expiration").textContent = guest.ssl_expires_at ? formatDate(guest.ssl_expires_at) : "—";
  $("ssl-days").textContent = guest.ssl_days_remaining ?? "—";
  $("ssl-error").textContent = guest.ssl_error || "—";

  $("network-overview-management-status").textContent = managementStatus;
  $("network-overview-server-ip").textContent = serverIp;
  $("network-overview-admin-url").textContent = adminUrl;
  $("network-overview-management-count").textContent = String((management.allowed_cidrs || []).length);
  $("network-overview-guest-status").textContent = guestStatus;
  $("network-overview-guest-domain").textContent = guestDomain;
  $("network-overview-guest-url").textContent = guestUrl;
  $("network-overview-guest-network-only").textContent = guest.guest_network_only === false ? "Disabled" : "Enabled";
  $("network-overview-ssl").textContent = sslStatus;
}

async function saveManagementAccess() {
  const body = {
    management_access_enabled: $("management-access-enabled").checked,
    management_allowed_cidrs: readLines("management-networks"),
    management_trusted_proxy_ranges: readLines("management-proxies"),
  };
  let result;
  try {
    result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/network-access/management`, { method: "PUT", body: JSON.stringify(body) });
  } catch (error) {
    if (error.code !== "network_access_confirmation_required") throw error;
    const warning = [...(error.warnings || []), "Continue only after confirming that an administrator has another approved way to reach Concierge.AI."].join("\n\n");
    if (!window.confirm(warning)) throw new Error("No management network changes were saved.");
    for (const confirmation of error.confirmations || []) body[confirmation] = true;
    result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/network-access/management`, { method: "PUT", body: JSON.stringify(body) });
  }
  if (result.rollback_pending) {
    $("management-rollback-note").hidden = false;
    showToast("Saved with a 10-minute rollback. Confirm from an allowed management network to keep this change.", "error");
    return;
  }
  await loadNetworkAccess();
  showToast("Management Access saved.");
}

function addManagementNetwork() {
  const input = $("management-network-input");
  const value = input.value.trim();
  if (!value) return;
  const lines = readLines("management-networks");
  if (lines.some((item) => item.toLowerCase() === value.toLowerCase())) {
    showToast("That management network is already listed.", "error");
    return;
  }
  lines.push(value);
  $("management-networks").value = lines.join("\n");
  input.value = "";
}

async function finalizeManagementAccess() {
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/network-access/management/finalize`, { method: "POST" });
  await loadNetworkAccess();
  showToast("Management network change confirmed.");
}

async function saveGuestAccess() {
  const body = {
    guest_access_enabled: $("guest-access-enabled").checked,
    guest_domain: $("deployment-domain").value.trim().toLowerCase(),
    guest_url: $("deployment-public-url").value.trim(),
    guest_https_required: $("network-https-required").checked,
    reverse_proxy: $("network-reverse-proxy").checked,
    guest_network_only: $("guardrail-network-only").checked,
    allowed_cidrs: readLines("guardrail-cidrs"),
    trusted_proxy_ranges: readLines("guardrail-proxies"),
    session_network_revalidation: $("guardrail-revalidation").value,
    guest_session_timeout: Number($("guardrail-timeout").value || 30),
    antlabs_gateway_enabled: $("guardrail-antlabs").checked,
    antlabs_gateway_ranges: readLines("guardrail-antlabs-ranges"),
  };
  let result;
  try {
    result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/network-access/guest`, { method: "PUT", body: JSON.stringify(body) });
  } catch (error) {
    if (error.code !== "network_access_confirmation_required") throw error;
    if (!window.confirm((error.warnings || []).join("\n\n"))) throw new Error("No Guest Access changes were saved.");
    body.confirm_overlap = true;
    result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/network-access/guest`, { method: "PUT", body: JSON.stringify(body) });
  }
  const guest = result.guest || {};
  state.property.domain = guest.domain || "";
  $("domain-input").value = state.property.domain;
  state.property.guardrails = {
    ...(state.property.guardrails || {}),
    guest_network_only: guest.guest_network_only,
    allowed_cidrs: guest.allowed_cidrs,
    trusted_proxy_ranges: guest.trusted_proxy_ranges,
    session_network_revalidation: guest.session_network_revalidation,
    guest_session_timeout: guest.guest_session_timeout,
    antlabs_gateway_enabled: guest.antlabs_gateway_enabled,
    antlabs_gateway_ranges: guest.antlabs_gateway_ranges,
  };
  state.property.app_settings = {
    ...(state.property.app_settings || {}),
    deployment: {
      ...(state.property.app_settings?.deployment || {}),
      guest_access_enabled: guest.enabled,
      public_base_url: guest.url,
      https_required: guest.https_required,
      reverse_proxy: guest.reverse_proxy,
    },
  };
  await loadNetworkAccess();
  showToast("Guest Access saved.");
}

async function verifyDeployment() {
  const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/deployment/verify`, { method: "POST" });
  await loadNetworkAccess();
  showToast(result.domain_status === "verified" ? "DNS and SSL verification completed." : result.detail || "Verification remains pending.", result.domain_status === "verified" ? "default" : "error");
}

async function loadSystemSettings() {
  const application = state.property.app_settings?.application || {};
  const timezone = application.timezone || state.property.timezone || "UTC";
  const language = application.default_language || state.property.languages?.[0] || "en";
  if (![...$("setting-timezone").options].some((option) => option.value === timezone)) $("setting-timezone").add(new Option(`${timezone} (saved value)`, timezone));
  if (![...$("setting-language").options].some((option) => option.value === language)) $("setting-language").add(new Option(`${language} (saved value)`, language));
  $("setting-language").value = language; $("setting-timezone").value = timezone; $("setting-maintenance").checked = Boolean(application.maintenance_enabled); $("setting-maintenance-message").value = application.maintenance_message || "";
  const smtp = await jsonFetch("/api/admin/system/email"); $("smtp-enabled").checked = smtp.enabled; $("smtp-host").value = smtp.host; $("smtp-port").value = smtp.port; $("smtp-security").value = smtp.security; $("smtp-username").value = smtp.username; $("smtp-from").value = smtp.from_address; $("smtp-password").value = ""; $("smtp-password").placeholder = smtp.password_configured ? `Saved securely (${smtp.password_masked})` : "Not configured"; $("smtp-status").textContent = smtp.enabled ? "SMTP enabled. Use Test Connection to verify reachability." : "SMTP is disabled; password-reset requests remain generic and do not send email.";
}
async function saveApplicationSettings() { const application = { default_language: $("setting-language").value.trim() || "en", timezone: $("setting-timezone").value.trim() || "UTC", maintenance_enabled: $("setting-maintenance").checked, maintenance_message: $("setting-maintenance-message").value.trim() }; state.property.languages = [...new Set([...(state.property.languages || []), application.default_language])]; state.property.timezone = application.timezone; state.property.app_settings = { ...(state.property.app_settings || {}), application }; await savePropertyBasics(); showToast("Application settings saved."); }
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
  const authNote = $("auth-runtime-note");
  if (authNote) {
    if (data.mode === "mock") {
      authNote.textContent = "Mock mode only simulates successful submissions; it does not contact ANTlabs. Live SG5 handoff supports Complimentary, Local, PMS / Room Login, Credit Card, and Access Code.";
    } else if (!data.configured) {
      authNote.textContent = "Live authentication is not ready: configure the SG5 built-in processor URL. No login method will be presented to guests until a supported live flow is configured.";
    } else {
      const labels = new Map(authTypeDefinitions.map((item) => [item.id, item.label]));
      const methods = (data.supported_authentication_types || []).map((id) => labels.get(id) || id).join(", ");
      authNote.textContent = `Live SG5 built-in processor methods: ${methods}. A connection check confirms endpoint reachability only; verify a guest login and Internet access on the target gateway.`;
    }
  }
}

async function testAntlabs() {
  const data = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/antlabs/test`, { method: "POST" }); renderAntlabsStatus(data); $("antlabs-last-check").textContent = new Date().toLocaleString(); showToast(data.detail, data.ok ? "default" : "error");
}

function setPublishState(text) {
  $("publish-state").textContent = text;
}

function hydrateProperty(property) {
  state.property = property;
  renderAdminBrandLogo(property);
  $("property-id").value = property.property_id;
  $("hotel-name-input").value = property.hotel_name;
  $("overview-title").textContent = property.hotel_name || "Property not configured";
  $("concierge-name-input").value = property.concierge_name;
  $("domain-input").value = property.domain || "";
  $("deployment-mode").value = property.deployment_mode || "on-prem";
  renderAuthTypes(property.antlabs_config || {});
  loadAIPolicy();
  renderManagedLocations();
}

function renderAdminBrandLogo(property) {
  const image = $("brand-logo-image");
  const fallback = $("brand-mark-fallback");
  const rawLogoUrl = String(property?.logo_url || "").trim();
  let logoUrl = "";
  if (/^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(rawLogoUrl)) {
    logoUrl = rawLogoUrl;
  } else if (rawLogoUrl) {
    try {
      const candidate = new URL(rawLogoUrl, window.location.href);
      if (["http:", "https:"].includes(candidate.protocol)) logoUrl = candidate.href;
    } catch { /* Ignore malformed saved image URLs and keep the mark fallback. */ }
  }
  image.onerror = () => {
    image.hidden = true;
    fallback.hidden = false;
  };
  image.hidden = !logoUrl;
  fallback.hidden = Boolean(logoUrl);
  if (logoUrl && image.src !== logoUrl) image.src = logoUrl;
  if (!logoUrl) image.removeAttribute("src");
  $("brand-logo-remove").hidden = !rawLogoUrl || !can("properties.edit");
}

async function saveAdminPropertyLogo(logoUrl) {
  const propertyId = currentPropertyId();
  if (!propertyId) throw new Error("Select a property before adding its logo.");
  const trigger = $("brand-logo-trigger");
  const remove = $("brand-logo-remove");
  trigger.disabled = true;
  remove.disabled = true;
  try {
    const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(propertyId)}/logo`, {
      method: "PUT",
      body: JSON.stringify({ logo_url: logoUrl }),
    });
    if (state.property?.property_id === propertyId) {
      state.property = { ...state.property, logo_url: result.logo_url };
      renderAdminBrandLogo(state.property);
    }
    state.properties = state.properties.map((property) => property.property_id === propertyId
      ? { ...property, logo_url: result.logo_url }
      : property);
    showToast(logoUrl ? "Property logo updated." : "Property logo removed.");
  } finally {
    trigger.disabled = false;
    remove.disabled = false;
  }
}

async function uploadAdminPropertyLogo(input) {
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  const acceptedTypes = ["image/png", "image/jpeg", "image/webp"];
  if (!acceptedTypes.includes(file.type)) {
    showToast("Choose a PNG, JPEG, or WebP logo.", "error");
    return;
  }
  if (!file.size || file.size > 500 * 1024) {
    showToast("Logo images must be smaller than 500 KB.", "error");
    return;
  }
  try {
    const logoUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.addEventListener("load", () => resolve(String(reader.result || "")), { once: true });
      reader.addEventListener("error", () => reject(new Error("The logo file could not be read.")), { once: true });
      reader.readAsDataURL(file);
    });
    await saveAdminPropertyLogo(logoUrl);
  } catch (error) {
    showToast(error.message || "The property logo could not be saved.", "error");
  }
}

function renderAuthTypes(config = {}) {
  const list = $("auth-type-list");
  if (!list) return;
  const authenticationTypes = config.authentication_types || {};
  const masterSwitch = $("authentication-enabled");
  masterSwitch.checked = Object.hasOwn(config, "authentication_enabled")
    ? config.authentication_enabled === true
    : Object.values(authenticationTypes).some((item) => item?.enabled === true);
  masterSwitch.onchange = () => {
    const status = $("auth-runtime-note");
    if (status) status.textContent = masterSwitch.checked
      ? "Guest sign-in will be offered after you save. ANTlabs gateway policy is not changed by this setting."
      : "Guest sign-in will be hidden after you save. ANTlabs gateway policy is not changed by this setting.";
    updateAuthSaveState();
  };
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
        <input type="checkbox" role="switch" aria-label="Enable ${escapeHTML(type.label)} authentication" data-auth-type="${type.id}" ${authenticationTypes[type.id]?.enabled ? "checked" : ""}>
      </label>
    `;
    row.querySelector("input").addEventListener("change", updateAuthSaveState);
    list.appendChild(row);
  }
  state.authSavedSnapshot = authSettingsSnapshot();
  updateAuthSaveState();
}

function readAuthTypes() {
  return authTypeDefinitions.map((type) => ({
    id: type.id,
    label: type.label,
    enabled: Boolean(document.querySelector(`[data-auth-type="${type.id}"]`)?.checked),
  }));
}

function authSettingsSnapshot() {
  return JSON.stringify({
    enabled: Boolean($("authentication-enabled")?.checked),
    methods: readAuthTypes().map(({ id, enabled }) => ({ id, enabled })),
  });
}

function updateAuthSaveState() {
  const button = $("save-auth-types");
  const status = $("auth-save-state");
  const statusText = $("auth-save-state-text");
  if (!button || !status || !statusText) return;
  const dirty = state.authSavedSnapshot !== authSettingsSnapshot();
  const phase = state.authSaving ? "saving" : dirty ? "unsaved" : "saved";
  status.dataset.state = phase;
  statusText.textContent = phase === "saving" ? "Saving changes…" : phase === "unsaved" ? "Unsaved changes" : "All changes saved";
  button.disabled = state.authSaving || !dirty;
  button.setAttribute("aria-busy", String(state.authSaving));
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

async function saveAuthenticationTypes() {
  const authenticationEnabled = $("authentication-enabled").checked;
  state.authSaving = true;
  updateAuthSaveState();
  try {
    await savePropertyBasics();
    const status = $("auth-runtime-note");
    if (status) status.textContent = authenticationEnabled
      ? "Guest Wi-Fi sign-in is on for this property. Only enabled methods supported by the configured ANTlabs mode are offered."
      : "Guest Wi-Fi sign-in is off for this property. Saved method choices are preserved; ANTlabs gateway policy is unchanged.";
    showToast(authenticationEnabled
      ? "Authentication methods saved. Guest Wi-Fi sign-in is on; the guest app reflects the enabled methods."
      : "Authentication methods saved. Guest Wi-Fi sign-in is off; ANTlabs gateway policy is unchanged.");
  } finally {
    state.authSaving = false;
    updateAuthSaveState();
  }
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
          <h3>${escapeHTML(provider.name)}</h3>
          <p>${escapeHTML(provider.auth_method.replaceAll("_", " "))}</p>
        </div>
      </div>
      <div class="provider-status ${statusType}">
        <span class="status-dot ${statusType}"></span>
        <span class="status-text">${escapeHTML(statusLabel(provider.status))}</span>
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
  const scoreValue = Number.isFinite(Number(latest.score)) ? Math.max(0, Math.min(100, Number(latest.score))) : 0;
  $("loop-latest").innerHTML = `
    <div class="loop-score-row"><strong>${escapeHTML(score)}</strong><progress class="loop-score-track" max="100" value="${scoreValue}" aria-label="Quality score ${escapeHTML(score)}"></progress></div>
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
  state.designAccentText = config.theme?.accentText || "#ffffff";
  $("design-hotel-name").value = config.branding?.hotelName || "";
  $("design-concierge-name").value = config.branding?.conciergeName || "";
  $("logo-display-input").value = config.branding?.logoDisplay || "mark_name";
  $("logo-url-input").value = config.branding?.logoUrl || "";
  const logoStatus = $("logo-upload-status");
  if (logoStatus) {
    logoStatus.textContent = config.branding?.logoUrl ? "Logo saved in this draft." : "No logo selected.";
    logoStatus.dataset.state = config.branding?.logoUrl ? "ready" : "neutral";
  }
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
    hotelName: $("design-hotel-name").value.trim(),
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
    accentText: state.designAccentText || base.theme?.accentText || "#ffffff",
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
    authentication_enabled: $("authentication-enabled")?.checked ?? Boolean(property.antlabs_config?.authentication_enabled),
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
  const preview = $("chat-preview");
  const logo = $("preview-logo");
  $("preview-hotel").textContent = config.branding.hotelName || "Property not configured";
  $("preview-concierge").textContent = config.branding.conciergeName;
  logo.textContent = config.branding.hotelName.slice(0, 1).toUpperCase();
  logo.style.backgroundImage = config.branding.logoUrl ? `url("${config.branding.logoUrl}")` : "";
  logo.classList.toggle("has-image", Boolean(config.branding.logoUrl));
  preview.dataset.logoDisplay = config.branding.logoDisplay || "mark_name";
  preview.dataset.headerVisible = String(config.header.enabled !== false);
  preview.dataset.logoVisible = String(config.header.showLogo !== false);
  preview.dataset.nameVisible = String(config.header.showHotelName !== false);
  preview.dataset.conciergeVisible = String(config.header.showConciergeName !== false);
  preview.dataset.userStyle = config.messages.userStyle || "bubble";
  preview.dataset.assistantStyle = config.messages.assistantStyle || "minimal";
  preview.dataset.promptLayout = config.layout.suggestionLayout || "stack";
  $("preview-greeting").textContent = config.welcome.greeting;
  $("preview-welcome").textContent = config.welcome.headline;
  $("preview-placeholder").textContent = config.composer.placeholder;
  preview.style.setProperty("--preview-bg", config.theme.background);
  preview.style.setProperty("--preview-surface", config.theme.surface);
  preview.style.setProperty("--preview-text", config.theme.textPrimary);
  preview.style.setProperty("--preview-subtle", config.theme.textSecondary);
  preview.style.setProperty("--preview-border", config.theme.border || "#e4e4e7");
  preview.style.setProperty("--preview-user-bubble", config.theme.userMessageBackground || "#eeeeee");
  preview.style.setProperty("--preview-bg-image", config.theme.backgroundImageUrl ? `url("${config.theme.backgroundImageUrl}")` : "none");
  preview.style.setProperty("--preview-overlay", (config.theme.backgroundOverlay || 0) / 100);
  preview.style.setProperty("--preview-font", previewFontStack(config.typography.fontFamily || config.theme.font || "Geist"));
  preview.style.setProperty("--preview-accent", accent);
  preview.style.setProperty("--preview-button", config.theme.buttonColor || accent);
  preview.style.setProperty("--preview-button-text", config.theme.accentText || "#ffffff");
  preview.style.setProperty("--preview-composer", config.composer.background || config.theme.composerBackground || config.theme.surface);
  preview.style.setProperty("--preview-radius", `${config.theme.radius ?? 14}px`);
  preview.style.setProperty("--preview-font-size", `${config.typography.baseFontSize || 15}px`);
  preview.style.setProperty("--preview-message-spacing", `${config.layout.messageSpacing || 24}px`);
  preview.style.setProperty("--preview-content-width", `${config.layout.contentWidth || 840}px`);
  preview.style.setProperty("--preview-message-width", `${config.layout.messageWidth || 680}px`);
  preview.style.setProperty("--preview-composer-width", `${config.layout.composerWidth || 840}px`);
  preview.style.setProperty("--preview-density", config.theme.density === "compact" ? "0.78" : "1");
  $("background-overlay-value").textContent = `${config.theme.backgroundOverlay || 0}%`;
  renderPreviewPrompts();
}

const designPresets = {
  elegant: { background: "#f5f5f5", surface: "#ffffff", text: "#202020", subtle: "#666666", accent: "#444444", user: "#ededed", button: "#202020", buttonText: "#ffffff", composer: "#ffffff", font: "Playfair Display", density: "comfortable", baseSize: 15, contentWidth: 840, messageWidth: 660, composerWidth: 820, spacing: 27, radius: 8 },
  minimal: { background: "#f7f7f7", surface: "#ffffff", text: "#171717", subtle: "#686868", accent: "#111111", user: "#eeeeee", button: "#111111", buttonText: "#ffffff", composer: "#ffffff", font: "Inter", density: "comfortable", baseSize: 15, contentWidth: 840, messageWidth: 680, composerWidth: 840, spacing: 24, radius: 8 },
  "soft-gray": { background: "#f1f1f1", surface: "#ffffff", text: "#222222", subtle: "#6b6b6b", accent: "#444444", user: "#e8e8e8", button: "#222222", buttonText: "#ffffff", composer: "#ffffff", font: "Geist", density: "comfortable", baseSize: 15, contentWidth: 840, messageWidth: 680, composerWidth: 840, spacing: 26, radius: 12 },
  "high-contrast": { background: "#ececec", surface: "#ffffff", text: "#111111", subtle: "#4d4d4d", accent: "#111111", user: "#e1e1e1", button: "#111111", buttonText: "#ffffff", composer: "#ffffff", font: "Inter", density: "compact", baseSize: 15, contentWidth: 840, messageWidth: 620, composerWidth: 800, spacing: 20, radius: 5 },
  graphite: { background: "#202020", surface: "#292929", text: "#f4f4f4", subtle: "#b5b5b5", accent: "#f1f1f1", user: "#3b3b3b", button: "#f1f1f1", buttonText: "#171717", composer: "#303030", font: "Inter", density: "comfortable", baseSize: 15, contentWidth: 840, messageWidth: 680, composerWidth: 840, spacing: 24, radius: 8 },
  ocean: { background: "#edf5f6", surface: "#ffffff", text: "#183039", subtle: "#566b70", accent: "#287987", user: "#dcecef", button: "#236a78", buttonText: "#ffffff", composer: "#ffffff", font: "Geist", density: "comfortable", baseSize: 15, contentWidth: 840, messageWidth: 680, composerWidth: 840, spacing: 24, radius: 8 },
  botanical: { background: "#f1f5f1", surface: "#ffffff", text: "#20302a", subtle: "#5e6f64", accent: "#4b7659", user: "#e0eae2", button: "#3a6248", buttonText: "#ffffff", composer: "#ffffff", font: "Geist", density: "comfortable", baseSize: 15, contentWidth: 840, messageWidth: 680, composerWidth: 840, spacing: 24, radius: 8 },
  rose: { background: "#f7f1f4", surface: "#ffffff", text: "#322730", subtle: "#74636d", accent: "#98677f", user: "#efe1e9", button: "#83556c", buttonText: "#ffffff", composer: "#ffffff", font: "Inter", density: "comfortable", baseSize: 15, contentWidth: 840, messageWidth: 680, composerWidth: 840, spacing: 24, radius: 8 },
  coral: { background: "#f8f1ef", surface: "#ffffff", text: "#332723", subtle: "#76625c", accent: "#ad5d4d", user: "#f2dfda", button: "#994d3e", buttonText: "#ffffff", composer: "#ffffff", font: "Inter", density: "comfortable", baseSize: 15, contentWidth: 840, messageWidth: 680, composerWidth: 840, spacing: 24, radius: 8 },
  "modern-elegance": { background: "#f5f4f0", surface: "#ffffff", text: "#262a27", subtle: "#686c68", accent: "#78633c", user: "#ece9e1", button: "#304239", buttonText: "#ffffff", composer: "#ffffff", font: "Playfair Display", density: "comfortable", baseSize: 15, contentWidth: 840, messageWidth: 660, composerWidth: 820, spacing: 28, radius: 8 },
};

function applyDesignPreset(presetName) {
  const preset = designPresets[presetName];
  if (!preset) return;
  const values = {
    "background-input": preset.background,
    "surface-input": preset.surface,
    "text-color-input": preset.text,
    "secondary-text-color-input": preset.subtle,
    "accent-input": preset.accent,
    "user-message-input": preset.user,
    "button-color-input": preset.button,
    "composer-background-input": preset.composer,
    "font-input": preset.font,
    "density-input": preset.density,
    "base-font-size-input": preset.baseSize,
    "content-width-input": preset.contentWidth,
    "message-width-input": preset.messageWidth,
    "composer-width-input": preset.composerWidth,
    "message-spacing-input": preset.spacing,
    "radius-input": preset.radius,
  };
  for (const [id, value] of Object.entries(values)) $(id).value = String(value);
  state.designAccentText = preset.buttonText;
  document.querySelectorAll("[data-design-preset]").forEach((button) => {
    const selected = button.dataset.designPreset === presetName;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  updatePreview();
  showToast(`${document.querySelector(`[data-design-preset="${presetName}"] .template-copy strong`).textContent} applied to the preview. Save draft to keep it.`);
}

function setDesignInspector(panelName) {
  const labels = { templates: "Templates", brand: "Brand identity", content: "Welcome content", theme: "Colors & background", layout: "Typography & layout", prompts: "Suggested prompts", versions: "Published versions" };
  state.designInspector = panelName;
  document.querySelectorAll(".design-tool").forEach((button) => {
    const selected = button.dataset.designInspector === panelName;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  for (const detail of document.querySelectorAll("[data-inspector-panel]")) {
    detail.open = detail.dataset.inspectorPanel === panelName;
  }
  $("inspector-active-tool").textContent = labels[panelName] || "Design";
  if (panelName !== "templates") {
    document.querySelector(`[data-inspector-panel="${panelName}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function setPreviewDevice(device) {
  const widths = { mobile: "390 px", tablet: "768 px", desktop: "Fluid" };
  state.designDevice = device;
  $("chat-preview").className = `phone-preview ${device}`;
  $("preview-viewport-label").textContent = `${device[0].toUpperCase()}${device.slice(1)} · ${widths[device]}`;
  document.querySelectorAll(".preview-size").forEach((button) => {
    const selected = button.dataset.size === device;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  if ($("preview-zoom-level")) {
    updatePreviewZoom(state.designZoom);
    requestAnimationFrame(fitPreview);
  }
}

function updatePreviewZoom(zoom) {
  state.designZoom = Math.min(1.25, Math.max(0.55, zoom));
  const stageWidth = Math.max(280, $("preview-stage").clientWidth - 40);
  const naturalWidth = state.designDevice === "mobile" ? 390 : state.designDevice === "tablet" ? 768 : Math.min(stageWidth, 1080);
  $("preview-device-wrap").style.setProperty("--preview-zoom", state.designZoom);
  $("preview-device-wrap").style.setProperty("--preview-natural-width", `${naturalWidth}px`);
  $("preview-device-wrap").style.setProperty("--preview-natural-height", "680px");
  $("preview-device-wrap").style.width = `${naturalWidth * state.designZoom}px`;
  $("preview-device-wrap").style.height = `${680 * state.designZoom}px`;
  $("preview-zoom-level").textContent = `${Math.round(state.designZoom * 100)}%`;
}

function fitPreview() {
  const stage = $("preview-stage");
  const maxWidth = Math.max(260, stage.clientWidth - 72);
  const maxHeight = Math.max(400, stage.clientHeight - 156);
  const previewWidth = state.designDevice === "mobile" ? 390 : state.designDevice === "tablet" ? 768 : Math.min(maxWidth, 1080);
  const previewHeight = 680;
  updatePreviewZoom(Math.min(1, maxWidth / previewWidth, maxHeight / previewHeight));
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

function handleImageUpload(input, targetId, { maxBytes, recommended, onStatus }) {
  const file = input.files?.[0];
  if (!file) return;
  if (file.size > maxBytes) {
    showToast(`${recommended} Try a smaller file.`, "error");
    onStatus?.("This file exceeds the upload size limit.", "error");
    input.value = "";
    return;
  }
  onStatus?.(`Reading ${file.name}...`, "loading");
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    $(targetId).value = reader.result;
    onStatus?.(`${file.name} is ready in this draft.`, "ready");
    updatePreview();
  });
  reader.addEventListener("error", () => {
    onStatus?.("The file could not be read. Choose another.", "error");
    input.value = "";
    showToast("The selected image could not be read.", "error");
  }, { once: true });
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
  state.properties = data.properties || [];
  const switcher = $("property-switcher");
  switcher.innerHTML = "";
  if (!state.properties.length) {
    state.property = null;
    $("property-id").value = "";
    switcher.appendChild(new Option("Property not configured", ""));
    switcher.disabled = true;
    $("publish-state").textContent = "Property not configured";
    $("platform-shell").classList.add("no-property");
    document.querySelectorAll(".platform-main > .panel").forEach((panel) => panel.classList.remove("active"));
    $("property-onboarding").classList.add("active");
    const canCreate = can("properties.edit") || can("properties.all");
    $("onboarding-create-property").hidden = !canCreate;
    $("onboarding-permission-note").hidden = canCreate;
    return;
  }
  $("platform-shell").classList.remove("no-property");
  $("property-onboarding").classList.remove("active");
  switcher.disabled = false;
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
  if (document.querySelector(".platform-main > .panel.active")?.id === "ai-assistant" && can("assistant.use")) {
    state.assistantConversationId = null;
    await loadAssistantConversations();
  }
}

function propertyIdFromName(name) {
  return name.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-").replace(/^[^a-z0-9]+/g, "").replace(/-+$/g, "").slice(0, 80);
}

function populatePropertyTimezones() {
  const fallbackTimezones = [
    "Africa/Abidjan", "Africa/Cairo", "Africa/Johannesburg", "Africa/Lagos", "Africa/Nairobi",
    "America/Anchorage", "America/Argentina/Buenos_Aires", "America/Chicago", "America/Denver",
    "America/Halifax", "America/Los_Angeles", "America/Mexico_City", "America/New_York",
    "America/Phoenix", "America/Sao_Paulo", "America/Toronto", "America/Vancouver",
    "Asia/Bangkok", "Asia/Dubai", "Asia/Hong_Kong", "Asia/Jakarta", "Asia/Jerusalem",
    "Asia/Karachi", "Asia/Kolkata", "Asia/Manila", "Asia/Riyadh", "Asia/Seoul",
    "Asia/Shanghai", "Asia/Singapore", "Asia/Taipei", "Asia/Tokyo",
    "Atlantic/Azores", "Australia/Adelaide", "Australia/Brisbane", "Australia/Perth",
    "Australia/Sydney", "Europe/Amsterdam", "Europe/Athens", "Europe/Berlin", "Europe/Dublin",
    "Europe/Helsinki", "Europe/Istanbul", "Europe/London", "Europe/Madrid", "Europe/Moscow",
    "Europe/Paris", "Europe/Rome", "Europe/Zurich", "Pacific/Auckland", "Pacific/Fiji",
    "Pacific/Honolulu", "UTC",
  ];
  const timezones = typeof Intl.supportedValuesOf === "function"
    ? Intl.supportedValuesOf("timeZone")
    : fallbackTimezones;
  const grouped = new Map();
  for (const timezone of [...new Set(["UTC", ...timezones])].sort((a, b) => a.localeCompare(b))) {
    const region = timezone.includes("/") ? timezone.split("/")[0] : "Other";
    if (!grouped.has(region)) grouped.set(region, []);
    grouped.get(region).push(timezone);
  }

  for (const selectId of ["property-create-timezone", "setting-timezone"]) {
    const select = $(selectId);
    for (const region of [...grouped.keys()].sort((a, b) => a.localeCompare(b))) {
      const group = document.createElement("optgroup");
      group.label = region;
      for (const timezone of grouped.get(region)) group.appendChild(new Option(timezone, timezone));
      select.appendChild(group);
    }
  }
}

function openPropertyCreation() {
  $("property-create-form").reset();
  $("property-create-message").textContent = "";
  $("property-create-id").dataset.edited = "false";
  $("property-create-dialog").showModal();
  $("property-create-name").focus();
}

async function createProperty(event) {
  event.preventDefault();
  const hotelName = $("property-create-name").value.trim();
  const propertyId = $("property-create-id").value.trim();
  const timezone = $("property-create-timezone").value.trim();
  if (!hotelName || !propertyId || !timezone) return;
  const submit = $("property-create-submit"); submit.disabled = true;
  $("property-create-message").textContent = "";
  try {
    await jsonFetch(`/api/admin/properties/${encodeURIComponent(propertyId)}`, {
      method: "PUT",
      body: JSON.stringify({ property_id: propertyId, hotel_name: hotelName, timezone, address: $("property-create-address").value.trim() }),
    });
    $("property-create-dialog").close();
    window.location.reload();
  } catch (error) {
    $("property-create-message").textContent = error.message;
  } finally { submit.disabled = false; }
}

async function switchProperty(propertyId) {
  const property = state.properties.find((item) => item.property_id === propertyId);
  if (!property || property.property_id === currentPropertyId()) return;
  const shell = $("platform-shell");
  const activePanel = document.querySelector(".platform-main > .panel.active")?.id || "overview";
  shell.classList.add("switching-property");
  hydrateProperty(property);
  if (activePanel === "ai-assistant") {
    state.assistantConversationId = null;
    state.assistantConversations = [];
    $("assistant-chat-scope").textContent = `${property.hotel_name} · Personal history`;
    resetAssistantConversationView();
  }
  state.ai = null;
  state.improvementLoop = null;
  state.personalizationPolicy = null;
  state.zones = null;
  state.hospitality = null;
  state.intro = null;
  state.catalog = { departments: [], services: [] };
  state.recommendations = [];
  state.knowledge = { items: [], documents: [], faqs: [] };
  state.managedKnowledge = { items: [], sources: [], categories: [] };
  state.knowledgeHealth = null;
  state.restaurantMenus = [];
  state.restaurantPromotions = [];
  state.webhooks = { webhooks: [], deliveries: [] };
  state.deployment = null;
  const tasks = [];
  if (can("concierge.view")) tasks.push(loadDesign());
  if (can("ai.view")) tasks.push(loadAI());
  if (can("dashboard.view")) tasks.push(loadDashboard());
  if (currentPropertyId()) {
    const activeRefresh = {
      "ai-assistant": () => loadAssistantConversations(),
      zones: () => loadZones(),
      sessions: () => loadSessions(),
      conversations: () => loadConversations(),
      "personalization-settings": () => loadPersonalizationPolicy(),
      location: () => loadLocationLive(),
      intro: () => loadIntro(),
      requests: () => loadServiceRequests(),
      "service-catalog": () => loadServiceCatalog(),
      recommendations: () => loadRecommendations(),
      "hotel-information": () => loadHotelInformation(),
      rooms: () => renderRooms(),
      guest: () => renderGuestModules(),
      facilities: () => loadHospitalityManagement(),
      restaurants: () => loadHospitalityManagement(),
      "ai-usage": () => loadAIUsage(),
      wifi: () => loadAntlabsStatus(),
      knowledge: () => loadKnowledge(), documents: () => loadKnowledge(), faqs: () => loadKnowledge(),
      "ai-personality": () => loadAIPolicy(),
      guardrails: () => loadAIPolicy(),
      webhooks: () => loadWebhooks(),
      "network-access": () => loadNetworkAccess(),
    }[activePanel];
    if (activeRefresh) tasks.push(Promise.resolve().then(activeRefresh));
    if (activePanel === "guardrails") tasks.push(loadGuardrailDiagnostics());
  }
  try {
    await Promise.all(tasks);
    showToast(`Switched to ${property.hotel_name}.`);
  } finally { shell.classList.remove("switching-property"); }
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
  const propertyId = currentPropertyId();
  if (state.mapPropertyId && state.mapPropertyId !== propertyId) {
    state.mapObjects = []; state.selectedMapObject = null; state.mapHistory = []; state.mapRedo = []; state.mapPolygonPoints = []; state.mapConnectFrom = null; state.mapDirty = false;
  }
  state.mapPropertyId = propertyId;
  state.zones = await jsonFetch(`/api/admin/properties/${encodeURIComponent(propertyId)}/zones`);
  hydrateZoneSelectors();
  state.mapSelectedFloorId = currentMapFloorId();
  state.mapSelectedBuildingId = currentMapBuildingId();
  renderZoneTree();
  renderMapCanvas();
  renderMapInspector();
}

function currentMapFloorId() { return $("zone-floor-select")?.value || ""; }
function currentMapBuildingId() { return $("zone-building-select")?.value || ""; }
function mapFloor(floorId = currentMapFloorId()) { return state.zones?.floors.find((floor) => floor.floor_id === floorId) || null; }
function mapBuilding(buildingId = currentMapBuildingId()) { return state.zones?.buildings.find((building) => building.building_id === buildingId) || null; }
function mapFloorZones(floorId = currentMapFloorId()) { return (state.zones?.zones || []).filter((zone) => zone.floor_id === floorId); }
function mapFloorNodes(floorId = currentMapFloorId()) { return (state.zones?.navigation_nodes || []).filter((node) => node.floor_id === floorId); }

function hydrateZoneSelectors() {
  const buildingSelect = $("zone-building-select");
  const floorSelect = $("zone-floor-select");
  if (!buildingSelect || !floorSelect || !state.zones) return;
  const previousBuilding = currentMapBuildingId();
  const previousFloor = currentMapFloorId();
  buildingSelect.replaceChildren();
  for (const building of state.zones.buildings) buildingSelect.appendChild(new Option(building.name, building.building_id));
  if (!state.zones.buildings.length) buildingSelect.appendChild(new Option("No building yet", ""));
  if (state.zones.buildings.some((item) => item.building_id === previousBuilding)) buildingSelect.value = previousBuilding;
  const floors = state.zones.floors.filter((floor) => !buildingSelect.value || floor.building_id === buildingSelect.value);
  floorSelect.replaceChildren();
  for (const floor of floors) floorSelect.appendChild(new Option(`${floor.name} · Level ${floor.level}`, floor.floor_id));
  if (!floors.length) floorSelect.appendChild(new Option(buildingSelect.value ? "No floors yet" : "Add a building first", ""));
  if (floors.some((item) => item.floor_id === previousFloor)) floorSelect.value = previousFloor;
  buildingSelect.disabled = !state.zones.buildings.length;
  floorSelect.disabled = !floors.length;
  $("add-map-floor").disabled = !buildingSelect.value;
  $("upload-floor-plan-trigger").disabled = !floorSelect.value;
  $("map-empty-upload").disabled = !floorSelect.value;
  renderMapContext();
}

function renderMapContext() {
  const floorId = currentMapFloorId();
  const floor = mapFloor(floorId);
  const floorMap = state.zones?.maps?.find((item) => item.floor_id === floorId);
  const name = $("map-plan-name");
  const detail = $("map-plan-detail");
  if (!floor) {
    name.textContent = "Choose or create a floor";
    detail.textContent = "A floor plan keeps zones, routes, and access points organized by level.";
  } else if (!floorMap) {
    name.textContent = "Blank floor map";
    detail.textContent = `No plan uploaded for ${floor.name}. You can draw directly on the canvas or add a background plan.`;
  } else {
    name.textContent = floorMap.original_filename || "Floor plan uploaded";
    detail.textContent = `${floor.name} · ${floorMap.content_type === "application/pdf" ? "PDF reference file" : "Floor plan background"} · Replace by uploading a newer plan`;
  }
  $("map-canvas-dimensions").textContent = floor ? `Map coordinates · ${floor.name} · 1200 × 720` : "Create a floor to start mapping";
  const hasMapObjects = mapFloorZones(floorId).length > 0 || mapFloorNodes(floorId).length > 0 || state.mapObjects.length > 0;
  const needsStructure = !floor;
  const isBlankFloor = Boolean(floor && !floorMap && !hasMapObjects && state.mapTool === "select");
  $("map-canvas-empty").hidden = !needsStructure && !isBlankFloor;
  $("map-empty-add-building").hidden = !needsStructure;
  $("map-empty-start-drawing").hidden = !isBlankFloor;
  $("map-empty-upload").hidden = !floor;
  $("map-empty-upload").disabled = !floor;
  if (isBlankFloor) {
    $("map-empty-title").textContent = "Your map is ready to build";
    $("map-empty-copy").textContent = "Draw a guest area to get started, or upload a floor plan to use as your background.";
  } else {
    $("map-empty-title").textContent = state.zones?.buildings.length ? "Add a floor to this property" : "Start with a building";
    $("map-empty-copy").textContent = state.zones?.buildings.length
      ? "Each floor has its own plan, guest areas, facilities, and navigation routes."
      : "Buildings group your property's floors. Add one, then create the floors guests and staff need.";
  }
  $("map-empty-add-building").textContent = state.zones?.buildings.length ? "Add floor" : "Add building";
}

function renderZoneTree() {
  const list = $("zone-tree");
  if (!list) return;
  list.replaceChildren();
  const floorId = currentMapFloorId();
  const objects = [
    ...mapFloorZones(floorId).map((item) => ({ kind: "zone", id: item.zone_id, label: item.name, detail: item.category || "Guest area", item })),
    ...(state.zones?.facilities || []).filter((item) => mapFloorZones(floorId).some((zone) => zone.zone_id === item.zone_id)).map((item) => ({ kind: "facility", id: item.facility_id, label: item.name, detail: item.facility_type || "Facility", item })),
    ...(state.zones?.access_points || []).filter((item) => mapFloorZones(floorId).some((zone) => zone.zone_id === item.zone_id)).map((item) => ({ kind: "access_point", id: item.access_point_id, label: item.name, detail: "Wi-Fi access point", item })),
    ...mapFloorNodes(floorId).map((item) => ({ kind: "navigation_node", id: item.node_id, label: item.label, detail: item.node_type || "Waypoint", item })),
    ...(state.zones?.navigation_edges || []).filter((edge) => mapFloorNodes(floorId).some((node) => node.node_id === edge.from_node_id) && mapFloorNodes(floorId).some((node) => node.node_id === edge.to_node_id)).map((item) => {
      const nodes = new Map(mapFloorNodes(floorId).map((node) => [node.node_id, node]));
      return { kind: "navigation_edge", id: item.edge_id, label: `${nodes.get(item.from_node_id)?.label || "Start"} → ${nodes.get(item.to_node_id)?.label || "End"}`, detail: `${item.distance} map units`, item };
    }),
  ];
  $("map-object-count").textContent = String(objects.length);
  if (!floorId) {
    const empty = document.createElement("div");
    empty.className = "map-list-empty";
    empty.textContent = "Select a floor to see its map objects.";
    list.appendChild(empty);
    return;
  }
  if (!objects.length) {
    const empty = document.createElement("div");
    empty.className = "map-list-empty";
    empty.innerHTML = "<strong>This floor is clear</strong><span>Draw a guest area, add a waypoint, or place a Wi-Fi access point to get started.</span>";
    list.appendChild(empty);
    return;
  }
  const query = $("map-object-search").value.trim().toLowerCase();
  const visibleObjects = query ? objects.filter((entry) => `${entry.label} ${entry.detail}`.toLowerCase().includes(query)) : objects;
  if (!visibleObjects.length) {
    const empty = document.createElement("div"); empty.className = "map-list-empty"; empty.textContent = "No map objects match this search."; list.appendChild(empty); return;
  }
  for (const entry of visibleObjects) {
    const selected = state.selectedMapObject?.zone_id === entry.id || state.selectedMapObject?.facility_id === entry.id || state.selectedMapObject?.access_point_id === entry.id || state.selectedMapObject?.node_id === entry.id || state.selectedMapObject?.edge_id === entry.id;
    const button = document.createElement("button");
    button.type = "button";
    button.className = `map-object-row${selected ? " selected" : ""}`;
    const icon = entry.kind === "zone" ? "▱" : entry.kind === "facility" ? "◇" : entry.kind === "access_point" ? "⌁" : entry.kind === "navigation_edge" ? "↔" : "●";
    button.innerHTML = `<span class="map-object-row-icon" aria-hidden="true">${icon}</span><span><strong>${escapeHTML(entry.label)}</strong><small>${escapeHTML(entry.detail)}</small></span>`;
    button.addEventListener("click", () => selectMapObject(entry.item, entry.kind));
    list.appendChild(button);
  }
}

function selectMapObject(item, kind) {
  if (kind === "zone") state.selectedMapObject = { ...item, objectType: "zone", isDraft: false };
  else if (kind === "facility") state.selectedMapObject = { ...item, objectType: "facility", isDraft: false };
  else if (kind === "access_point") state.selectedMapObject = { ...item, objectType: "access_point", isDraft: false };
  else if (kind === "navigation_node") state.selectedMapObject = { ...item, objectType: "navigation_node", isDraft: false };
  else if (kind === "navigation_edge") state.selectedMapObject = { ...item, objectType: "navigation_edge", isDraft: false };
  state.mapDirty = false;
  renderZoneTree(); renderMapCanvas(); renderMapInspector();
}

function mapLayers() { return Object.fromEntries([...document.querySelectorAll(".layer-toggle")].map((input) => [input.dataset.layer, input.checked])); }
function selectedGeometryFor(zone) { return state.selectedMapObject?.zone_id === zone.zone_id ? state.selectedMapObject.geometry : zone.geometry; }
function pointForGeometry(geometry = {}) {
  if (geometry.type === "ellipse") return [geometry.cx, geometry.cy];
  if (geometry.type === "polygon" && geometry.points?.length) return [geometry.points.reduce((sum, p) => sum + p[0], 0) / geometry.points.length, geometry.points.reduce((sum, p) => sum + p[1], 0) / geometry.points.length];
  if (geometry.type === "point") return [geometry.x, geometry.y];
  return [Number(geometry.x || 0) + Number(geometry.width || 0) / 2, Number(geometry.y || 0) + Number(geometry.height || 0) / 2];
}

function renderMapCanvas() {
  const canvas = $("floor-map-canvas");
  if (!canvas || !state.zones) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width, height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, width, height);
  const layers = mapLayers();
  const floorId = currentMapFloorId();
  const floorMap = state.zones.maps.find((item) => item.floor_id === floorId);
  if (layers.floor_plan && floorMap && floorMap.content_type !== "application/pdf") {
    let image = state.mapBackgrounds.get(floorMap.map_id);
    if (!image) {
      image = new Image(); image.addEventListener("load", renderMapCanvas, { once: true }); image.src = floorMap.url; state.mapBackgrounds.set(floorMap.map_id, image);
    }
    if (image.complete && image.naturalWidth) {
      const scale = Math.min(width / image.naturalWidth, height / image.naturalHeight);
      const drawWidth = image.naturalWidth * scale, drawHeight = image.naturalHeight * scale;
      ctx.drawImage(image, (width - drawWidth) / 2, (height - drawHeight) / 2, drawWidth, drawHeight);
    }
  } else if (layers.floor_plan && floorMap?.content_type === "application/pdf") {
    ctx.fillStyle = "#f3f4f6"; ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = "#475569"; ctx.textAlign = "center"; ctx.font = "600 20px system-ui"; ctx.fillText("PDF saved as a reference", width / 2, height / 2 - 8);
    ctx.font = "14px system-ui"; ctx.fillText("Upload an image plan to use it as a map background.", width / 2, height / 2 + 20); ctx.textAlign = "start";
  }
  if (layers.grid) {
    ctx.save(); ctx.strokeStyle = floorMap ? "rgba(148,163,184,.2)" : "#e9edf2"; ctx.lineWidth = 1;
    for (let x = 0; x <= width; x += 40) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke(); }
    for (let y = 0; y <= height; y += 40) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); }
    ctx.restore();
  }
  const zones = mapFloorZones(floorId);
  const nodes = mapFloorNodes(floorId);
  const displayNodes = nodes.map((node) => state.selectedMapObject?.node_id === node.node_id ? state.selectedMapObject : node);
  const nodeById = new Map(displayNodes.map((node) => [node.node_id, node]));
  if (layers.navigation) {
    for (const edge of state.zones.navigation_edges || []) {
      const from = nodeById.get(edge.from_node_id), to = nodeById.get(edge.to_node_id);
      if (!from || !to) continue;
      const selected = state.selectedMapObject?.edge_id === edge.edge_id;
      ctx.save(); ctx.strokeStyle = selected ? "#155e75" : "#0f766e"; ctx.lineWidth = selected ? 6 : 4; ctx.setLineDash([10, 8]);
      ctx.beginPath(); ctx.moveTo(from.x, from.y); ctx.lineTo(to.x, to.y); ctx.stroke(); ctx.restore();
    }
  }
  if (layers.zones) for (const zone of zones) drawGeometry(ctx, selectedGeometryFor(zone), state.selectedMapObject?.zone_id === zone.zone_id ? "#0f766e" : "#2563eb", state.selectedMapObject?.zone_id === zone.zone_id ? state.selectedMapObject.name : zone.name, state.selectedMapObject?.zone_id === zone.zone_id);
  if (layers.facilities) for (const facility of state.zones.facilities || []) {
    const zone = zones.find((item) => item.zone_id === facility.zone_id); if (!zone) continue;
    const shownFacility = state.selectedMapObject?.facility_id === facility.facility_id ? state.selectedMapObject : facility;
    const [x, y] = pointForGeometry(selectedGeometryFor(zone)); drawMarker(ctx, x, y, "◇", "#b45309", shownFacility.name, state.selectedMapObject?.facility_id === facility.facility_id);
  }
  if (layers.access_points) for (const savedAp of state.zones.access_points || []) {
    const ap = state.selectedMapObject?.access_point_id === savedAp.access_point_id ? state.selectedMapObject : savedAp;
    if (!zones.some((item) => item.zone_id === ap.zone_id)) continue;
    drawMarker(ctx, Number(ap.x || 0), Number(ap.y || 0), "⌁", "#dc2626", ap.name, state.selectedMapObject?.access_point_id === ap.access_point_id);
  }
  if (layers.navigation) for (const node of displayNodes) {
    drawMarker(ctx, Number(node.x), Number(node.y), "●", "#0f766e", node.label, state.selectedMapObject?.node_id === node.node_id);
  }
  for (const draft of state.mapObjects) {
    if (draft.objectType === "zone") drawGeometry(ctx, draft.geometry, "#059669", draft.name || "New area", true);
    if (draft.objectType === "navigation_node") drawMarker(ctx, draft.x, draft.y, "●", "#0f766e", draft.label || "New waypoint", true);
    if (draft.objectType === "access_point") drawMarker(ctx, draft.x, draft.y, "⌁", "#dc2626", draft.name || "New access point", true);
    if (draft.objectType === "navigation_edge") {
      const from = nodeById.get(draft.from_node_id), to = nodeById.get(draft.to_node_id);
      if (from && to) { ctx.save(); ctx.strokeStyle = "#0f766e"; ctx.lineWidth = 5; ctx.setLineDash([8, 6]); ctx.beginPath(); ctx.moveTo(from.x, from.y); ctx.lineTo(to.x, to.y); ctx.stroke(); ctx.restore(); }
    }
  }
  if (state.mapPolygonPoints.length) {
    ctx.save(); ctx.strokeStyle = "#059669"; ctx.fillStyle = "rgba(5,150,105,.14)"; ctx.lineWidth = 3; ctx.setLineDash([8, 5]);
    ctx.beginPath(); ctx.moveTo(...state.mapPolygonPoints[0]); for (const point of state.mapPolygonPoints.slice(1)) ctx.lineTo(...point); ctx.stroke();
    for (const point of state.mapPolygonPoints) { ctx.fillStyle = "#059669"; ctx.beginPath(); ctx.arc(point[0], point[1], 6, 0, Math.PI * 2); ctx.fill(); }
    ctx.restore();
  }
  renderMapContext();
}

function drawGeometry(ctx, geometry, color, label, selected = false) {
  if (!geometry) return;
  ctx.save(); ctx.strokeStyle = color; ctx.fillStyle = color + "22"; ctx.lineWidth = selected ? 4 : 2;
  if (geometry.type === "rectangle") { ctx.fillRect(geometry.x, geometry.y, geometry.width, geometry.height); ctx.strokeRect(geometry.x, geometry.y, geometry.width, geometry.height); }
  else if (geometry.type === "ellipse") { ctx.beginPath(); ctx.ellipse(geometry.cx, geometry.cy, Math.max(1, geometry.rx), Math.max(1, geometry.ry), 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); }
  else if (geometry.type === "polygon" && geometry.points?.length) {
    ctx.beginPath(); ctx.moveTo(...geometry.points[0]); for (const point of geometry.points.slice(1)) ctx.lineTo(...point); ctx.closePath(); ctx.fill(); ctx.stroke();
  }
  const [x, y] = pointForGeometry(geometry); ctx.font = "600 15px system-ui"; ctx.fillStyle = "#17212b";
  if (label) { ctx.lineWidth = 4; ctx.strokeStyle = "rgba(255,255,255,.92)"; ctx.strokeText(label, x + 10, y + 5); ctx.fillStyle = color; ctx.fillText(label, x + 10, y + 5); }
  ctx.restore();
}

function drawMarker(ctx, x, y, glyph, color, label, selected = false) {
  ctx.save(); ctx.beginPath(); ctx.arc(x, y, selected ? 14 : 12, 0, Math.PI * 2); ctx.fillStyle = "#fff"; ctx.fill(); ctx.lineWidth = selected ? 4 : 2; ctx.strokeStyle = color; ctx.stroke();
  ctx.fillStyle = color; ctx.font = "700 15px system-ui"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(glyph, x, y);
  if (label) { ctx.textAlign = "left"; ctx.textBaseline = "alphabetic"; ctx.font = "600 14px system-ui"; ctx.lineWidth = 4; ctx.strokeStyle = "#fff"; ctx.strokeText(label, x + 18, y + 5); ctx.fillStyle = "#17212b"; ctx.fillText(label, x + 18, y + 5); }
  ctx.restore();
}

function hitTestMap(point) {
  const [x, y] = point;
  const layers = mapLayers();
  for (const item of [...state.mapObjects].reverse()) {
    if (layers.zones && item.objectType === "zone" && geometryContains(item.geometry, x, y)) return { item, kind: "draft" };
    if (layers.navigation && item.objectType === "navigation_node" && Math.hypot(x - item.x, y - item.y) < 20) return { item, kind: "draft" };
    if (layers.access_points && item.objectType === "access_point" && Math.hypot(x - item.x, y - item.y) < 20) return { item, kind: "draft" };
  }
  if (layers.access_points) for (const ap of [...(state.zones?.access_points || [])].reverse()) if (mapFloorZones().some((zone) => zone.zone_id === ap.zone_id) && Math.hypot(x - Number(ap.x || 0), y - Number(ap.y || 0)) < 18) return { item: ap, kind: "access_point" };
  if (layers.navigation) for (const node of [...mapFloorNodes()].reverse()) if (Math.hypot(x - Number(node.x), y - Number(node.y)) < 18) return { item: node, kind: "navigation_node" };
  if (layers.navigation) for (const edge of [...(state.zones?.navigation_edges || [])].reverse()) {
    const nodes = new Map(mapFloorNodes().map((node) => [node.node_id, node]));
    const from = nodes.get(edge.from_node_id), to = nodes.get(edge.to_node_id);
    if (from && to && distanceToSegment(x, y, from.x, from.y, to.x, to.y) < 10) return { item: edge, kind: "navigation_edge" };
  }
  if (layers.facilities) for (const facility of [...(state.zones?.facilities || [])].reverse()) {
    const zone = mapFloorZones().find((item) => item.zone_id === facility.zone_id); if (!zone) continue;
    const [fx, fy] = pointForGeometry(selectedGeometryFor(zone)); if (Math.hypot(x - fx, y - fy) < 18) return { item: facility, kind: "facility" };
  }
  if (layers.zones) for (const zone of [...mapFloorZones()].reverse()) if (geometryContains(selectedGeometryFor(zone), x, y)) return { item: zone, kind: "zone" };
  return null;
}

function distanceToSegment(x, y, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay, length = dx * dx + dy * dy;
  const t = length ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / length)) : 0;
  return Math.hypot(x - (ax + t * dx), y - (ay + t * dy));
}

function geometryContains(g, x, y) {
  if (!g) return false;
  if (g.type === "rectangle") return x >= g.x && x <= g.x + g.width && y >= g.y && y <= g.y + g.height;
  if (g.type === "ellipse") return ((x - g.cx) ** 2 / Math.max(1, g.rx ** 2)) + ((y - g.cy) ** 2 / Math.max(1, g.ry ** 2)) <= 1;
  if (g.type === "polygon" && g.points?.length >= 3) {
    let inside = false;
    for (let i = 0, j = g.points.length - 1; i < g.points.length; j = i++) { const a = g.points[i], b = g.points[j]; if (((a[1] > y) !== (b[1] > y)) && x < ((b[0] - a[0]) * (y - a[1])) / ((b[1] - a[1]) || 1) + a[0]) inside = !inside; }
    return inside;
  }
  return false;
}

function renderMapInspector() {
  const item = state.selectedMapObject;
  const form = $("map-object-form"), empty = $("map-inspector-empty");
  if (!item) {
    form.hidden = true; empty.hidden = false; $("map-inspector-title").textContent = "Object details"; $("map-selection-badge").textContent = "Nothing selected"; $("map-inspector-meta").hidden = true;
    renderZoneTree(); return;
  }
  const type = item.objectType || "zone";
  const isEdge = type === "navigation_edge", isNode = type === "navigation_node", isFacility = type === "facility", isAp = type === "access_point";
  const readonly = false;
  form.hidden = false; empty.hidden = true;
  $("map-inspector-title").textContent = item.isDraft ? "New map object" : (item.name || item.label || "Object details");
  $("map-selection-badge").textContent = item.isDraft ? "Unsaved changes" : (type === "zone" ? "Guest area" : isNode ? "Waypoint" : isAp ? "Wi-Fi point" : isFacility ? "Facility" : "Route");
  $("map-object-kind-wrap").hidden = isEdge || isNode || isAp || isFacility;
  $("map-object-type").value = item.createAs || (isNode ? (item.node_type || "waypoint") : isEdge ? "waypoint" : isAp ? "access_point" : isFacility ? "facility" : (item.category || "zone"));
  $("map-object-type").disabled = readonly || isNode || isEdge || isAp || isFacility;
  $("map-object-name-wrap").hidden = isEdge;
  $("map-object-name").value = item.name || item.label || (isEdge ? "" : "");
  $("map-object-name").disabled = readonly;
  $("map-object-name").required = !isEdge;
  $("map-linked-zone-wrap").hidden = !(isFacility || isAp || isNode || item.createAs === "facility" || item.createAs === "access_point");
  $("map-linked-zone").required = isFacility || isAp || item.createAs === "facility" || item.createAs === "access_point";
  $("map-facility-fields").hidden = !(isFacility || item.createAs === "facility");
  const facilityType = item.facility_type || "amenity";
  if (![...$("map-facility-type").options].some((option) => option.value === facilityType)) $("map-facility-type").add(new Option(facilityType, facilityType));
  $("map-facility-type").value = facilityType;
  $("map-facility-description").value = item.description || "";
  $("map-ap-fields").hidden = !(isAp || item.createAs === "access_point");
  $("map-ap-identifier").required = isAp || item.createAs === "access_point";
  $("map-node-fields").hidden = !isNode;
  $("map-edge-fields").hidden = !isEdge;
  $("map-edge-distance").required = isEdge;
  $("map-object-visible-wrap").hidden = isAp;
  $("map-object-visible").checked = item.guest_visible !== false && item.guest_visible !== 0;
  $("map-object-visible").disabled = readonly;
  $("map-ap-identifier").value = item.identifier || "";
  $("map-ap-identifier").disabled = readonly;
  $("map-node-type").value = item.node_type || "waypoint";
  $("map-node-type").disabled = readonly;
  const zoneSelect = $("map-linked-zone");
  const selectedFloorZones = mapFloorZones();
  zoneSelect.replaceChildren(new Option("Select a zone", ""));
  for (const zone of selectedFloorZones) zoneSelect.appendChild(new Option(zone.name, zone.zone_id));
  zoneSelect.value = item.zone_id || (type === "zone" ? item.zone_id : "");
  zoneSelect.disabled = readonly;
  if (isEdge) {
    const nodes = mapFloorNodes();
    $("map-edge-from").textContent = nodes.find((node) => node.node_id === item.from_node_id)?.label || "Start waypoint";
    $("map-edge-to").textContent = nodes.find((node) => node.node_id === item.to_node_id)?.label || "End waypoint";
    $("map-edge-distance").value = item.distance || ""; $("map-edge-distance").disabled = readonly;
    $("map-edge-bidirectional").checked = item.bidirectional !== false && item.bidirectional !== 0; $("map-edge-bidirectional").disabled = readonly;
  }
  $("save-map-object").hidden = readonly; $("save-map-object").disabled = readonly;
  $("duplicate-map-object").disabled = !(type === "zone" && !item.createAs && mapFloor());
  $("delete-map-object").disabled = readonly;
  $("map-inspector-meta").hidden = !item.isDraft && !item.zone_id && !item.node_id && !item.access_point_id;
  $("map-object-floor").textContent = mapFloor(item.floor_id)?.name || mapFloor()?.name || "—";
  const [x, y] = item.geometry ? pointForGeometry(item.geometry) : [item.x, item.y];
  $("map-object-position").textContent = Number.isFinite(x) && Number.isFinite(y) ? `${Math.round(x)}, ${Math.round(y)}` : "—";
  renderZoneTree();
}

function syncMapObjectType() {
  const item = state.selectedMapObject;
  if (!item) return;
  const type = $("map-object-type").value;
  if (type === "facility" || type === "access_point") item.createAs = type;
  else { item.createAs = ""; item.objectType = "zone"; item.category = type; }
  renderMapInspector();
}

function snapshotMapHistory() { state.mapHistory.push({ objects: structuredClone(state.mapObjects), selected: state.selectedMapObject ? structuredClone(state.selectedMapObject) : null }); if (state.mapHistory.length > 50) state.mapHistory.shift(); state.mapRedo = []; }
function restoreMapSnapshot(snapshot) {
  state.mapObjects = snapshot.objects || [];
  const selected = snapshot.selected;
  if (selected?.draft_id) state.selectedMapObject = state.mapObjects.find((item) => item.draft_id === selected.draft_id) || selected;
  else state.selectedMapObject = selected;
  state.mapDirty = false;
  renderMapCanvas(); renderMapInspector();
}
function mapPoint(event) {
  const canvas = $("floor-map-canvas"), rect = canvas.getBoundingClientRect();
  return [Math.max(0, Math.min(canvas.width, Math.round((event.clientX - rect.left) * canvas.width / rect.width))), Math.max(0, Math.min(canvas.height, Math.round((event.clientY - rect.top) * canvas.height / rect.height)))];
}
function snapMapPoint([x, y]) { return [Math.round(x / 10) * 10, Math.round(y / 10) * 10]; }
function makeMapDraft(type, point) {
  const [x, y] = snapMapPoint(point), draft_id = crypto.randomUUID();
  if (type === "waypoint") return { draft_id, objectType: "navigation_node", isDraft: true, floor_id: currentMapFloorId(), label: "New waypoint", name: "New waypoint", x, y, node_type: "waypoint", guest_visible: true };
  if (type === "access_point") return { draft_id, objectType: "access_point", isDraft: true, floor_id: currentMapFloorId(), name: "New access point", x, y, guest_visible: false };
  return { draft_id, objectType: "zone", isDraft: true, floor_id: currentMapFloorId(), name: "New area", category: "zone", geometry: { type: "rectangle", x, y, width: 1, height: 1 }, guest_visible: true };
}

function handleCanvasPointer(event) {
  if (!currentMapFloorId()) { showToast("Add a building and floor before editing this map.", "error"); return; }
  const point = mapPoint(event), [x, y] = snapMapPoint(point), canvas = $("floor-map-canvas");
  if (state.mapTool === "select") {
    const hit = hitTestMap(point);
    if (!hit) { state.selectedMapObject = null; renderMapInspector(); renderMapCanvas(); return; }
    if (hit.kind === "draft") state.selectedMapObject = hit.item;
    else selectMapObject(hit.item, hit.kind);
    if (state.selectedMapObject?.objectType === "zone") {
      snapshotMapHistory(); state.mapPointer = { mode: "move", start: point, geometry: structuredClone(state.selectedMapObject.geometry), moved: false };
      canvas.setPointerCapture?.(event.pointerId);
    } else if (["access_point", "navigation_node"].includes(state.selectedMapObject?.objectType)) {
      snapshotMapHistory(); state.mapPointer = { mode: "move-marker", start: point, origin: [Number(state.selectedMapObject.x || 0), Number(state.selectedMapObject.y || 0)] };
      canvas.setPointerCapture?.(event.pointerId);
    }
    renderMapInspector(); renderMapCanvas(); return;
  }
  if (state.mapTool === "polygon") {
    state.mapPolygonPoints.push([x, y]);
    $("finish-map-draw").hidden = state.mapPolygonPoints.length < 3;
    $("map-canvas-status").textContent = `${state.mapPolygonPoints.length} points · finish polygon when ready`;
    renderMapCanvas(); return;
  }
  if (state.mapTool === "connect") {
    const hit = hitTestMap(point);
    const node = hit?.kind === "navigation_node" ? hit.item : null;
    if (!node || node.isDraft) { showToast("Choose a saved waypoint. Save new waypoints before connecting them.", "error"); return; }
    if (!state.mapConnectFrom) { state.mapConnectFrom = node; $("map-canvas-status").textContent = `Start: ${node.label}. Choose another waypoint.`; renderMapCanvas(); return; }
    if (state.mapConnectFrom.node_id === node.node_id) { state.mapConnectFrom = null; $("map-canvas-status").textContent = "Route cancelled"; return; }
    snapshotMapHistory();
    const draft = { draft_id: crypto.randomUUID(), objectType: "navigation_edge", isDraft: true, floor_id: currentMapFloorId(), from_node_id: state.mapConnectFrom.node_id, to_node_id: node.node_id, distance: Math.max(1, Math.round(Math.hypot(node.x - state.mapConnectFrom.x, node.y - state.mapConnectFrom.y))), bidirectional: true, guest_visible: true };
    state.mapObjects.push(draft); state.selectedMapObject = draft; state.mapConnectFrom = null; renderMapInspector(); renderMapCanvas(); return;
  }
  if (["waypoint", "access_point"].includes(state.mapTool)) {
    snapshotMapHistory(); const draft = makeMapDraft(state.mapTool, point); state.mapObjects.push(draft); state.selectedMapObject = draft; renderMapInspector(); renderMapCanvas(); return;
  }
  if (["rectangle", "ellipse", "freeform"].includes(state.mapTool)) {
    snapshotMapHistory(); const draft = makeMapDraft(state.mapTool, point);
    if (state.mapTool === "ellipse") draft.geometry = { type: "ellipse", cx: x, cy: y, rx: 1, ry: 1 };
    if (state.mapTool === "freeform") draft.geometry = { type: "polygon", points: [[x, y]] };
    state.mapObjects.push(draft); state.selectedMapObject = draft;
    state.mapPointer = { mode: state.mapTool, start: [x, y], draft };
    canvas.setPointerCapture?.(event.pointerId); renderMapInspector(); renderMapCanvas();
  }
}

function handleCanvasPointerMove(event) {
  if (!state.mapPointer) return;
  const point = snapMapPoint(mapPoint(event)), start = state.mapPointer.start;
  if (state.mapPointer.mode === "move") {
    const dx = point[0] - start[0], dy = point[1] - start[1], original = state.mapPointer.geometry;
    const geometry = structuredClone(original);
    if (geometry.type === "rectangle") { geometry.x += dx; geometry.y += dy; }
    else if (geometry.type === "ellipse") { geometry.cx += dx; geometry.cy += dy; }
    else if (geometry.type === "polygon") geometry.points = geometry.points.map(([x, y]) => [x + dx, y + dy]);
    state.selectedMapObject.geometry = geometry; state.mapPointer.moved ||= dx !== 0 || dy !== 0;
    state.mapDirty ||= state.mapPointer.moved;
  } else if (state.mapPointer.mode === "move-marker") {
    const dx = point[0] - start[0], dy = point[1] - start[1];
    state.selectedMapObject.x = state.mapPointer.origin[0] + dx;
    state.selectedMapObject.y = state.mapPointer.origin[1] + dy;
    state.mapDirty ||= dx !== 0 || dy !== 0;
  } else {
    const draft = state.mapPointer.draft, [x, y] = point;
    if (state.mapPointer.mode === "rectangle") draft.geometry = { type: "rectangle", x: Math.min(start[0], x), y: Math.min(start[1], y), width: Math.abs(x - start[0]), height: Math.abs(y - start[1]) };
    if (state.mapPointer.mode === "ellipse") draft.geometry = { type: "ellipse", cx: (start[0] + x) / 2, cy: (start[1] + y) / 2, rx: Math.abs(x - start[0]) / 2, ry: Math.abs(y - start[1]) / 2 };
    if (state.mapPointer.mode === "freeform") { const points = draft.geometry.points, last = points.at(-1); if (!last || Math.hypot(x - last[0], y - last[1]) >= 5) points.push([x, y]); }
  }
  renderMapCanvas(); renderMapInspector();
}

function finishMapPointer() {
  if (!state.mapPointer) return;
  const pointer = state.mapPointer; state.mapPointer = null;
  if (pointer.mode !== "move" && pointer.draft?.geometry) {
    const g = pointer.draft.geometry;
    if ((g.type === "rectangle" && (g.width < 12 || g.height < 12)) || (g.type === "ellipse" && (g.rx < 6 || g.ry < 6)) || (g.type === "polygon" && g.points.length < 3)) {
      state.mapObjects = state.mapObjects.filter((item) => item !== pointer.draft); state.selectedMapObject = null; showToast("Draw a little larger to create a map area.");
    } else { $("map-canvas-status").textContent = "Unsaved area · add its details, then save"; }
  }
  renderMapCanvas(); renderMapInspector();
}

function finishMapPolygon() {
  if (state.mapPolygonPoints.length < 3) { showToast("A polygon needs at least three points.", "error"); return; }
  snapshotMapHistory(); const draft = { draft_id: crypto.randomUUID(), objectType: "zone", isDraft: true, floor_id: currentMapFloorId(), name: "New area", category: "zone", geometry: { type: "polygon", points: state.mapPolygonPoints.map((point) => [...point]) }, guest_visible: true };
  state.mapObjects.push(draft); state.selectedMapObject = draft; state.mapPolygonPoints = []; $("finish-map-draw").hidden = true; renderMapInspector(); renderMapCanvas();
}

function updateMapTool(tool, button) {
  state.mapTool = tool; state.mapConnectFrom = null;
  for (const candidate of document.querySelectorAll("[data-map-tool]")) { candidate.classList.toggle("active", candidate === button); candidate.setAttribute("aria-pressed", String(candidate === button)); }
  const labels = { select: "Select", rectangle: "Zone", polygon: "Polygon", ellipse: "Ellipse", freeform: "Freehand", waypoint: "Waypoint", connect: "Connect", access_point: "Access point" };
  const hints = { select: "Select and drag a guest area to move it. Select a saved object from the list to inspect it.", rectangle: "Drag across the canvas to draw a rectangular guest area.", polygon: "Click to place each corner, then select Finish polygon.", ellipse: "Drag across the canvas to size an elliptical guest area.", freeform: "Draw a freeform guest area by dragging across the canvas.", waypoint: "Click where guests should be able to navigate from or to.", connect: "Select two saved waypoints in order to create a guest route.", access_point: "Click to place a Wi-Fi access point inside its associated guest area." };
  $("map-active-tool-label").textContent = labels[tool] || "Select"; $("map-tool-hint").textContent = hints[tool] || "";
  $("map-canvas-status").textContent = tool === "select" ? "Ready" : "Choose a point on the map";
  $("finish-map-draw").hidden = tool !== "polygon" || state.mapPolygonPoints.length < 3;
  $("floor-map-canvas").dataset.tool = tool;
  renderMapContext();
}

async function createMapStructure(mode) {
  const isFloor = mode === "floor";
  if (isFloor && !currentMapBuildingId()) { showToast("Add a building before adding a floor.", "error"); return; }
  state.mapStructureMode = mode;
  $("map-structure-title").textContent = isFloor ? "Add floor" : "Add building";
  $("map-structure-help").textContent = isFloor ? `Add a named floor to ${mapBuilding()?.name || "this building"}.` : "Group floors under a building so staff can organize large properties clearly.";
  $("map-structure-name-label").firstChild.textContent = isFloor ? "Floor name" : "Building name";
  $("map-structure-name").placeholder = isFloor ? "For example, Lobby Level" : "For example, Main Building";
  $("map-floor-level-wrap").hidden = !isFloor; $("map-structure-submit").textContent = isFloor ? "Add floor" : "Add building";
  $("map-structure-form").reset(); $("map-floor-level").value = "0"; $("map-structure-dialog").showModal();
  setTimeout(() => $("map-structure-name").focus(), 0);
}

async function submitMapStructure(event) {
  event.preventDefault();
  const name = $("map-structure-name").value.trim(); if (!name) return;
  if (state.mapStructureMode === "floor" && !currentMapBuildingId()) throw new Error("Add a building before adding a floor.");
  if (state.mapStructureMode === "floor") {
    await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/floors`, { method: "POST", body: JSON.stringify({ data: { building_id: currentMapBuildingId(), name, level: Number($("map-floor-level").value || 0) } }) });
  } else {
    await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/buildings`, { method: "POST", body: JSON.stringify({ data: { name } }) });
  }
  $("map-structure-dialog").close(); await loadZones();
  if (state.mapStructureMode === "floor") { const created = [...state.zones.floors].reverse().find((floor) => floor.building_id === currentMapBuildingId() && floor.name === name); if (created) { $("zone-floor-select").value = created.floor_id; state.mapSelectedFloorId = created.floor_id; renderMapContext(); renderMapCanvas(); renderZoneTree(); } }
  showToast(`${state.mapStructureMode === "floor" ? "Floor" : "Building"} added.`);
}

async function saveMapObject(event) {
  event?.preventDefault();
  const item = state.selectedMapObject, floorId = currentMapFloorId();
  if (!item || !floorId) throw new Error("Choose a floor and a map object to save.");
  const type = item.createAs || item.objectType || "zone", name = $("map-object-name").value.trim();
  const visible = $("map-object-visible").checked;
  const base = `/api/admin/properties/${encodeURIComponent(currentPropertyId())}`;
  if (type === "zone") {
    if (!name) throw new Error("Enter a name for this area.");
    const result = await jsonFetch(`${base}/zones`, { method: "PUT", body: JSON.stringify({ data: { zone_id: item.zone_id, floor_id: floorId, name, category: $("map-object-type").value || item.category || "common", geometry: item.geometry, guest_visible: visible } }) });
    state.selectedMapObject = { ...result, objectType: "zone", isDraft: false }; state.mapObjects = state.mapObjects.filter((draft) => draft.draft_id !== item.draft_id);
  } else if (type === "facility") {
    const zoneId = $("map-linked-zone").value || item.zone_id;
    if (!zoneId) throw new Error("Choose the guest area that contains this facility.");
    if (!name) throw new Error("Enter a name for this facility.");
    const method = item.facility_id ? "PUT" : "POST";
    const url = item.facility_id ? `${base}/facilities/${encodeURIComponent(item.facility_id)}` : `${base}/facilities`;
    const result = await jsonFetch(url, { method, body: JSON.stringify({ data: { zone_id: zoneId, name, facility_type: $("map-facility-type").value, description: $("map-facility-description").value.trim(), guest_visible: visible } }) });
    state.selectedMapObject = { ...result, objectType: "facility", isDraft: false };
  } else if (type === "access_point") {
    const zoneId = $("map-linked-zone").value || item.zone_id, identifier = $("map-ap-identifier").value.trim();
    if (!zoneId) throw new Error("Choose the guest area that contains this access point.");
    if (!name || !identifier) throw new Error("Enter an access point name and WLAN identifier.");
    const method = item.access_point_id ? "PUT" : "POST";
    const url = item.access_point_id ? `${base}/access-points/${encodeURIComponent(item.access_point_id)}` : `${base}/access-points`;
    const [zoneX, zoneY] = item.geometry ? pointForGeometry(item.geometry) : [item.x, item.y];
    const result = await jsonFetch(url, { method, body: JSON.stringify({ data: { zone_id: zoneId, name, identifier, x: zoneX, y: zoneY } }) });
    state.mapObjects = state.mapObjects.filter((draft) => draft.draft_id !== item.draft_id);
    state.selectedMapObject = { ...result, objectType: "access_point", isDraft: false };
  } else if (type === "navigation_node") {
    if (!name) throw new Error("Enter a label for this waypoint.");
    const method = item.node_id ? "PUT" : "POST";
    const url = item.node_id ? `${base}/navigation/nodes/${encodeURIComponent(item.node_id)}` : `${base}/navigation/nodes`;
    const result = await jsonFetch(url, { method, body: JSON.stringify({ data: { floor_id: floorId, zone_id: $("map-linked-zone").value || null, label: name, x: item.x, y: item.y, node_type: $("map-node-type").value, guest_visible: visible } }) });
    state.selectedMapObject = { ...result, name: result.label, objectType: "navigation_node", isDraft: false }; state.mapObjects = state.mapObjects.filter((draft) => draft.draft_id !== item.draft_id);
  } else if (type === "navigation_edge") {
    const distance = Number($("map-edge-distance").value);
    if (!Number.isFinite(distance) || distance <= 0) throw new Error("Route distance must be greater than zero.");
    const method = item.edge_id ? "PUT" : "POST";
    const url = item.edge_id ? `${base}/navigation/edges/${encodeURIComponent(item.edge_id)}` : `${base}/navigation/edges`;
    const result = await jsonFetch(url, { method, body: JSON.stringify({ data: { from_node_id: item.from_node_id, to_node_id: item.to_node_id, distance, bidirectional: $("map-edge-bidirectional").checked, guest_visible: visible } }) });
    state.selectedMapObject = { ...result, objectType: "navigation_edge", isDraft: false }; state.mapObjects = state.mapObjects.filter((draft) => draft.draft_id !== item.draft_id);
  }
  state.mapHistory = []; state.mapRedo = [];
  await loadZones(); if (state.selectedMapObject) renderMapInspector(); showToast("Map changes saved.");
  state.mapDirty = false;
}

async function deleteMapObject() {
  const item = state.selectedMapObject; if (!item) return;
  if (item.isDraft) {
    snapshotMapHistory(); state.mapObjects = state.mapObjects.filter((draft) => draft.draft_id !== item.draft_id); state.selectedMapObject = null; renderMapInspector(); renderMapCanvas(); return;
  }
  const base = `/api/admin/properties/${encodeURIComponent(currentPropertyId())}`;
  if (item.objectType === "zone" && item.zone_id) {
    if (!window.confirm(`Delete “${item.name}” and its linked facilities, Wi-Fi points, waypoints, and routes? This cannot be undone.`)) return;
    await jsonFetch(`${base}/zones/${encodeURIComponent(item.zone_id)}`, { method: "DELETE" });
    showToast("Guest area and linked map records deleted.");
  } else {
    const records = { facility: ["facilities", item.facility_id], access_point: ["access-points", item.access_point_id], navigation_node: ["navigation/nodes", item.node_id], navigation_edge: ["navigation/edges", item.edge_id] };
    const record = records[item.objectType]; if (!record?.[1]) return;
    const linked = item.objectType === "navigation_node" ? " Routes connected to it will also be removed." : "";
    if (!window.confirm(`Delete “${item.name || item.label || "this map object"}”?${linked} This cannot be undone.`)) return;
    await jsonFetch(`${base}/${record[0]}/${encodeURIComponent(record[1])}`, { method: "DELETE" });
    showToast("Map object deleted.");
  }
  state.selectedMapObject = null; state.mapDirty = false; state.mapHistory = []; state.mapRedo = []; await loadZones();
}

function duplicateMapObject() {
  const item = state.selectedMapObject; if (!item?.geometry || item.objectType !== "zone" || item.createAs) return;
  snapshotMapHistory(); const copy = { ...structuredClone(item), zone_id: undefined, draft_id: crypto.randomUUID(), isDraft: true, name: `${item.name} copy`, geometry: structuredClone(item.geometry) };
  if (copy.geometry.type === "rectangle") { copy.geometry.x += 24; copy.geometry.y += 24; }
  else if (copy.geometry.type === "ellipse") { copy.geometry.cx += 24; copy.geometry.cy += 24; }
  else if (copy.geometry.type === "polygon") copy.geometry.points = copy.geometry.points.map(([x, y]) => [x + 24, y + 24]);
  state.mapObjects.push(copy); state.selectedMapObject = copy; renderMapInspector(); renderMapCanvas();
}

function undoMap() { const previous = state.mapHistory.pop(); if (previous) { state.mapRedo.push({ objects: structuredClone(state.mapObjects), selected: state.selectedMapObject ? structuredClone(state.selectedMapObject) : null }); restoreMapSnapshot(previous); } }
function redoMap() { const next = state.mapRedo.pop(); if (next) { state.mapHistory.push({ objects: structuredClone(state.mapObjects), selected: state.selectedMapObject ? structuredClone(state.selectedMapObject) : null }); restoreMapSnapshot(next); } }
function setMapZoom(value) {
  state.mapZoom = Math.max(.5, Math.min(2, value));
  $("floor-map-canvas").style.width = `${Math.round(state.mapZoom * 100)}%`;
  $("map-zoom-label").textContent = `${Math.round(state.mapZoom * 100)}%`;
}

async function uploadFloorMap(file) {
  if (!file) return;
  if (!currentMapFloorId()) throw new Error("Choose a floor before uploading its plan.");
  if (file.size > 8 * 1024 * 1024) throw new Error("Floor plans must be 8 MB or smaller.");
  const supported = ["image/png", "image/jpeg", "image/svg+xml", "application/pdf"];
  if (!supported.includes(file.type)) throw new Error("Choose a PNG, JPG, SVG, or PDF floor plan.");
  let width = null, height = null;
  if (file.type.startsWith("image/")) {
    try { const bitmap = await createImageBitmap(file); width = bitmap.width; height = bitmap.height; bitmap.close(); }
    catch { /* dimensions are optional; the server can still store valid SVGs */ }
  }
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = ""; const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/floors/${encodeURIComponent(currentMapFloorId())}/maps`, { method: "POST", body: JSON.stringify({ filename: file.name, content_type: file.type, width, height, content_base64: btoa(binary) }) });
  await loadZones(); showToast("Floor plan uploaded.");
}
function sessionRecordElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function updateStayMemoryEditor(stay) {
  const memory = stay?.memory_summary || {};
  const editable = stay?.status === "active";
  const fields = ["memory-summary", "memory-preferences", "memory-recent-requests", "memory-unresolved-requests", "memory-important-context"];
  for (const id of fields) $(id).disabled = !editable;
  $("save-stay-memory").disabled = !editable;
  $("memory-summary").value = memory.conversation_summary || "";
  $("memory-preferences").value = (memory.preferences || []).join("\n");
  $("memory-recent-requests").value = (memory.recent_requests || []).join("\n");
  $("memory-unresolved-requests").value = (memory.unresolved_service_requests || []).join("\n");
  $("memory-important-context").value = memory.important_context || "";
  $("session-memory-selection").textContent = !stay
    ? "Choose a stay to view or update its saved notes."
    : editable
      ? `Editing active stay ${stay.stay_id}${stay.room ? ` · Room ${stay.room}` : ""}.`
      : `Stay ${stay.stay_id} is checked out. Its notes are read-only.`;
}

function stayMemoryLabel(memory = {}) {
  const parts = [];
  if (String(memory.conversation_summary || "").trim()) parts.push("summary");
  for (const [key, label] of [["preferences", "preference"], ["recent_requests", "recent request"], ["unresolved_service_requests", "unresolved request"]]) {
    const count = Array.isArray(memory[key]) ? memory[key].filter((item) => String(item || "").trim()).length : 0;
    if (count) parts.push(count + " " + label + (count === 1 ? "" : "s"));
  }
  if (String(memory.important_context || "").trim()) parts.push("staff context");
  return parts.length ? parts.join(", ") : "No notes saved";
}

function sessionSearchText(record) {
  return JSON.stringify(record || {}).toLowerCase();
}

function renderSessionSummary() {
  const sessions = state.guestSessions || [];
  const links = state.guestSessionLinks || [];
  const stays = state.guestStays || [];
  const devices = state.guestDevices || [];
  const counts = {
    total: sessions.length + links.length + stays.length + devices.length,
    active: sessions.filter((session) => session.session_status === "active").length,
    stays: stays.filter((stay) => stay.status === "active").length,
    expired: sessions.filter((session) => session.session_status !== "active").length,
    devices: devices.length,
  };
  for (const [key, value] of Object.entries(counts)) $(`session-count-${key}`).textContent = value;
  const activeFilter = $("session-record-filter").value;
  for (const card of document.querySelectorAll("[data-session-filter]")) {
    card.classList.toggle("selected", card.dataset.sessionFilter === activeFilter);
  }
}

function renderSessionRecords() {
  const list = $("session-list");
  const filter = $("session-record-filter").value;
  const query = $("session-record-search").value.trim().toLowerCase();
  const sessions = (state.guestSessions || []).filter((item) => (filter === "all" || filter === "active-sessions" && item.session_status === "active" || filter === "expired-sessions" && item.session_status !== "active") && (!query || sessionSearchText(item).includes(query)));
  const links = (state.guestSessionLinks || []).filter((item) => (filter === "all" || filter === "guest-links") && (!query || sessionSearchText(item).includes(query)));
  const stays = (state.guestStays || []).filter((item) => (filter === "all" || filter === "active-stays" && item.status === "active" || filter === "checked-out-stays" && item.status !== "active") && (!query || sessionSearchText(item).includes(query)));
  const devices = (state.guestDevices || []).filter((item) => (filter === "all" || filter === "devices") && (!query || sessionSearchText(item).includes(query)));
  const total = sessions.length + links.length + stays.length + devices.length;
  $("session-result-count").textContent = `${total} ${total === 1 ? "record" : "records"}`;
  list.replaceChildren();
  renderSessionSummary();

  const appendGroup = (label, items, renderItem) => {
    if (!items.length) return;
    const group = sessionRecordElement("section", "session-record-group");
    group.appendChild(sessionRecordElement("h3", "", `${label} · ${items.length}`));
    const records = sessionRecordElement("div", "session-record-group-list");
    for (const item of items) records.appendChild(renderItem(item));
    group.appendChild(records);
    list.appendChild(group);
  };

  appendGroup("Guest sessions", sessions, (session) => {
    const card = sessionRecordElement("article", "session-record-card");
    const header = sessionRecordElement("header", "session-record-header");
    const title = sessionRecordElement("div", "session-record-title");
    title.append(sessionRecordElement("p", "", "CONCIERGE SESSION"), sessionRecordElement("h4", "", session.session_id));
    const badge = sessionRecordElement("span", `session-record-badge ${session.session_status}`, session.session_status === "active" ? "Active" : "Expired");
    header.append(title, badge);
    const facts = sessionRecordElement("div", "session-record-facts");
    const add = (label, value) => {
      const cell = sessionRecordElement("div", "session-record-detail");
      cell.append(sessionRecordElement("span", "", label), sessionRecordElement("strong", "", String(value || "Not set")));
      facts.appendChild(cell);
    };
    add("Authentication", session.authenticated ? "Authenticated" : "Not authenticated");
    add("Conversation state", String(session.interaction_status || "open").replaceAll("_", " "));
    add("Staff takeover", session.human_takeover ? "Active" : "No");
    add("Messages", `${Number(session.message_count || 0)} messages`);
    add("Started", formatDate(session.created_at));
    add("Last activity", formatDate(session.last_seen_at));
    if (session.last_provider) add("Last AI provider", session.last_provider);
    card.append(header, facts);
    return card;
  });

  appendGroup("WLAN and integration links", links, (link) => {
    const card = sessionRecordElement("article", "session-record-card");
    const header = sessionRecordElement("header", "session-record-header");
    const title = sessionRecordElement("div", "session-record-title");
    title.append(sessionRecordElement("p", "", "WLAN / INTEGRATION LINK"), sessionRecordElement("h4", "", link.guest_session_id));
    const status = link.stay_status === "active" ? "Active stay" : "Checked out";
    header.append(title, sessionRecordElement("span", "session-record-badge", status));
    const facts = sessionRecordElement("div", "session-record-facts");
    const add = (label, value) => {
      const cell = sessionRecordElement("div", "session-record-detail");
      cell.append(sessionRecordElement("span", "", label), sessionRecordElement("strong", "", String(value || "Not linked")));
      facts.appendChild(cell);
    };
    add("Stay ID", link.stay_id);
    add("Room", link.room || "Not recorded");
    add("Device identity", link.device_id);
    add("Concierge session ID", link.concierge_session_id);
    add("ANTlabs session ID", link.antlabs_session_id);
    add("Browser session ID", link.browser_session_id);
    add("Created", formatDate(link.created_at));
    add("Last activity", formatDate(link.last_seen_at));
    card.append(header, facts);
    return card;
  });

  appendGroup("Guest stays", stays, (stay) => {
    const card = sessionRecordElement("article", "session-record-card");
    const header = sessionRecordElement("header", "session-record-header");
    const title = sessionRecordElement("div", "session-record-title");
    title.append(sessionRecordElement("p", "", "GUEST STAY"), sessionRecordElement("h4", "", stay.stay_id));
    const badge = sessionRecordElement("span", `session-record-badge ${stay.status}`, stay.status === "active" ? "Active" : "Checked out");
    header.append(title, badge);
    const facts = sessionRecordElement("div", "session-record-facts");
    const add = (label, value) => {
      const cell = sessionRecordElement("div", "session-record-detail");
      cell.append(sessionRecordElement("span", "", label), sessionRecordElement("strong", "", String(value || "Not set")));
      facts.appendChild(cell);
    };
    add("Room", stay.room || "Not recorded");
    add("Device identity", stay.device_id || "Not linked");
    add("PMS guest ID", stay.pms_guest_id || "Not linked");
    add("Stay notes", stayMemoryLabel(stay.memory_summary));
    add("Created", formatDate(stay.created_at));
    add("Last updated", formatDate(stay.updated_at));
    add("Retention until", stay.retention_until ? formatDate(stay.retention_until) : "No expiry set");
    if (stay.checked_out_at) add("Checked out", formatDate(stay.checked_out_at));
    const action = sessionRecordElement("button", "secondary", stay.status === "active" ? "Edit stay notes" : "View stay notes");
    action.type = "button";
    action.title = stay.status === "active" ? "Load this stay in the notes editor" : "Checked-out stay notes are read-only";
    action.addEventListener("click", () => {
      $("memory-stay-id").value = stay.stay_id;
      updateStayMemoryEditor(stay);
      $("memory-stay-id").scrollIntoView({ behavior: "smooth", block: "center" });
    });
    card.append(header, facts, action);
    return card;
  });

  appendGroup("Pseudonymous device identities", devices, (device) => {
    const card = sessionRecordElement("article", "session-record-card device-record-card");
    const header = sessionRecordElement("header", "session-record-header");
    const title = sessionRecordElement("div", "session-record-title");
    title.append(sessionRecordElement("p", "", "DEVICE IDENTITY · RAW MAC NOT DISPLAYED"), sessionRecordElement("h4", "", device.device_id));
    header.append(title, sessionRecordElement("span", "session-record-badge", String(device.source || "wlan").toUpperCase()));
    const facts = sessionRecordElement("div", "session-record-facts");
    const add = (label, value) => {
      const cell = sessionRecordElement("div", "session-record-detail");
      cell.append(sessionRecordElement("span", "", label), sessionRecordElement("strong", "", String(value || "Not set")));
      facts.appendChild(cell);
    };
    add("First seen", formatDate(device.first_seen_at));
    add("Last seen", formatDate(device.last_seen_at));
    card.append(header, facts);
    return card;
  });

  if (!total) {
    const empty = sessionRecordElement("div", "session-record-empty");
    empty.append(sessionRecordElement("strong", "", query ? "No records match this search" : "No guest records yet"));
    empty.append(sessionRecordElement("span", "", query ? "Try a different session, stay, room, or device search." : "Guest sessions, stays, and pseudonymous WLAN identities will appear here.") );
    list.appendChild(empty);
  }
}

async function loadSessions() {
  const button = $("refresh-sessions");
  const originalLabel = button?.textContent || "Refresh records";
  if (button) { button.disabled = true; button.textContent = "Refreshing…"; }
  try {
    const data = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/sessions`);
    state.guestSessions = data.sessions || [];
    state.guestSessionLinks = data.guest_sessions || [];
    state.guestStays = data.stays || [];
    state.guestDevices = data.devices || [];
    const selector = $("memory-stay-id");
    const previousSelection = selector.value;
    selector.replaceChildren(new Option("Select a stay", ""));
    for (const stay of state.guestStays) {
      const description = [stay.room ? `Room ${stay.room}` : "No room", stay.status === "active" ? "Active" : "Checked out", stay.stay_id].join(" · ");
      selector.appendChild(new Option(description, stay.stay_id));
    }
    selector.value = state.guestStays.some((stay) => stay.stay_id === previousSelection) ? previousSelection : "";
    updateStayMemoryEditor(state.guestStays.find((stay) => stay.stay_id === selector.value) || null);
    renderSessionRecords();
    $("session-last-refreshed").textContent = `Updated ${new Intl.DateTimeFormat(undefined, { timeStyle: "short" }).format(new Date())}`;
  } finally {
    if (button) { button.disabled = false; button.textContent = originalLabel; }
  }
}

async function createStaySession() {
  const rawMac = $("session-raw-mac").value.trim();
  if (!rawMac) throw new Error("Enter an authorized WLAN MAC address to create or restore a stay.");
  const retentionDays = Number($("session-retention-days").value || 2);
  if (!Number.isInteger(retentionDays) || retentionDays < 1 || retentionDays > 60) throw new Error("Set stay retention between 1 and 60 days.");
  const button = $("create-stay-session");
  button.disabled = true;
  button.textContent = "Connecting…";
  try {
    const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/sessions/reconnect`, {
      method: "POST",
      body: JSON.stringify({
        raw_mac: rawMac,
        room: $("session-room").value.trim() || null,
        concierge_session_id: $("session-concierge-id").value.trim() || null,
        antlabs_session_id: $("session-antlabs-id").value.trim() || null,
        browser_session_id: $("session-browser-id").value.trim() || null,
        pms_guest_id: $("session-pms-guest-id").value.trim() || null,
        retention_days: retentionDays,
      }),
    });
    $("session-raw-mac").value = "";
    await loadSessions();
    $("memory-stay-id").value = result.stay.stay_id;
    updateStayMemoryEditor(result.stay);
    showToast("Guest stay created or restored; WLAN identity is pseudonymous.");
  } finally {
    button.disabled = false;
    button.textContent = "Create / Restore Stay";
  }
}

async function saveStayMemory() {
  const stayId = $("memory-stay-id").value;
  const stay = state.guestStays.find((item) => item.stay_id === stayId);
  if (!stayId || !stay) throw new Error("Select a guest stay first.");
  if (stay.status !== "active") throw new Error("Stay notes can only be changed for an active stay.");
  const lines = (id) => $(id).value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean).slice(0, 20);
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/stays/${encodeURIComponent(stayId)}/memory`, {
    method: "PUT",
    body: JSON.stringify({ memory: {
      conversation_summary: $("memory-summary").value.trim(),
      preferences: lines("memory-preferences"),
      recent_requests: lines("memory-recent-requests"),
      unresolved_service_requests: lines("memory-unresolved-requests"),
      important_context: $("memory-important-context").value.trim(),
    } }),
  });
  await loadSessions();
  showToast("Stay notes saved.");
}

async function loadLocationLive() {
  renderManagedLocations();
  const data = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/location/live`);
  $("location-live-metrics").innerHTML = `
    <article><span>Detected devices</span><strong>${data.currently_detected}</strong></article>
    <article><span>Active stays</span><strong>${data.active_sessions}</strong></article>
    <article><span>Busiest zone</span><strong>${escapeHTML(data.busiest_zone_id || "-")}</strong></article>
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
    ${Object.entries(report.area_metrics).map(([zone, metric]) => `<div class="compact-row"><strong>${escapeHTML(zone)}</strong><span>${metric.total_visits} visits · ${metric.average_dwell_seconds}s avg dwell · ${metric.repeat_visits} repeat visits</span></div>`).join("")}
    ${report.movement_patterns.map((item) => `<div class="compact-row"><strong>${escapeHTML(item.source_zone_id)} -> ${escapeHTML(item.destination_zone_id)}</strong><span>${item.count} transitions · ${item.percentage}%</span></div>`).join("")}
  `;
}

async function loadIntro() {
  state.intro = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/intro`);
  $("intro-mode").value = state.intro.mode;
  $("intro-preset").value = state.intro.preset;
  $("intro-duration").value = (Number(state.intro.duration_ms || 1400) / 1000).toFixed(1);
  $("intro-duration-range").value = state.intro.duration_ms || 1400;
  $("intro-message").value = state.intro.welcome_message;
  $("intro-background").value = normalizeColor(state.intro.background);
  $("intro-brand-color").value = normalizeColor(state.intro.brand_color);
  $("intro-first-visit").checked = state.intro.first_visit_only;
  $("intro-skip").checked = state.intro.allow_skip;
  state.introDirty = false;
  updateIntroPreview();
}

function introRelativeLuminance(color) {
  const channels = (color.match(/[a-f\d]{2}/gi) || []).map((channel) => Number.parseInt(channel, 16) / 255);
  if (channels.length !== 3) return 0;
  const linear = channels.map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
  return (0.2126 * linear[0]) + (0.7152 * linear[1]) + (0.0722 * linear[2]);
}

function introContrastRatio(foreground, background) {
  const luminance = [introRelativeLuminance(foreground), introRelativeLuminance(background)].sort((a, b) => b - a);
  return (luminance[0] + 0.05) / (luminance[1] + 0.05);
}

function updateIntroPreview() {
  const mode = $("intro-mode").value;
  const preset = $("intro-preset").value;
  const card = $("intro-preview-card");
  const stage = $("intro-preview-stage");
  card.hidden = mode === "none";
  $("intro-preview-empty").hidden = mode !== "none";
  const backgroundColor = normalizeColor($("intro-background").value);
  const brandColor = normalizeColor($("intro-brand-color").value);
  const assetUrl = state.intro?.asset_url || "";
  const videoAsset = Boolean(assetUrl && ["video/webm", "video/mp4"].includes(state.intro?.asset_type));
  const logoUrl = state.designDraft?.branding?.logoUrl || state.property?.logo_url || "";
  const logoImage = $("intro-preview-logo-image");
  card.dataset.mode = mode;
  card.dataset.preset = preset;
  card.style.setProperty("--intro-background", backgroundColor);
  card.style.setProperty("--intro-brand", brandColor);
  card.style.setProperty("--intro-duration", `${Math.max(300, Math.min(8000, Number($("intro-duration-range").value || 1400)))}ms`);
  stage.style.setProperty("--intro-background", backgroundColor);
  stage.style.setProperty("--intro-brand", brandColor);
  $("intro-background-value").textContent = backgroundColor;
  $("intro-brand-color-value").textContent = brandColor;
  const contrast = introContrastRatio(brandColor, backgroundColor);
  const contrastStatus = $("intro-accessibility-check");
  const contrastLevel = contrast >= 7 ? "AAA" : contrast >= 4.5 ? "AA" : "below AA";
  contrastStatus.classList.toggle("review", contrast < 4.5);
  contrastStatus.textContent = contrast >= 4.5
    ? `Text contrast ${contrast.toFixed(1)}:1 · WCAG ${contrastLevel} for normal text.`
    : `Text contrast ${contrast.toFixed(1)}:1 · review these colors for readability (target 4.5:1 or higher).`;
  $("intro-preview-message").textContent = $("intro-message").value.trim() || "Welcome";
  $("intro-preview-property").textContent = state.property?.hotel_name || "Your property";
  const mark = (state.property?.hotel_name || "C").trim().slice(0, 1).toUpperCase();
  $("intro-preview-logo").textContent = mark;
  if (logoUrl) {
    logoImage.src = logoUrl;
    logoImage.hidden = false;
    $("intro-preview-logo").hidden = true;
  } else {
    logoImage.removeAttribute("src");
    logoImage.hidden = true;
    $("intro-preview-logo").hidden = false;
  }
  $("intro-preview-skip").hidden = mode === "none" || !$("intro-skip").checked;
  $("intro-preview-skip").disabled = !card.classList.contains("playing") || mode === "none" || !$("intro-skip").checked;
  const video = $("intro-preview-video");
  if (videoAsset && video.src !== new URL(assetUrl, window.location.origin).href) {
    video.src = assetUrl;
    video.load();
  }
  video.hidden = !(mode === "custom_upload" && videoAsset);
  $("intro-upload-section").hidden = mode !== "custom_upload";
  $("intro-preset-section").hidden = mode === "none";
  $("intro-content-section").hidden = mode === "none";
  const modeHelp = {
    none: "Guests go straight to the concierge chat.",
    generate_from_logo: logoUrl ? "The current property logo will be animated with your selected motion style." : "No property logo is set yet. A branded initial will be used until you add a logo in Design.",
    custom_upload: videoAsset ? "Your uploaded video plays with the welcome message and guest controls layered above it." : "Upload a silent MP4 or WebM video to finish setting up this mode.",
  };
  $("intro-mode-description").textContent = modeHelp[mode] || modeHelp.none;
  const presetLabels = { none: "No animation", minimal_fade: "Minimal fade", fade_scale: "Fade + scale", luxury_reveal: "Luxury reveal", particle_assemble: "Particle assemble", line_draw: "Line draw", glass_blur: "Glass / blur", split_reveal: "Split reveal", logo_to_chat_header: "Logo to chat" };
  $("intro-selected-preset").textContent = presetLabels[preset] || "No animation";
  $("intro-preset-help").textContent = preset === "none" ? "The brand card appears without an entrance animation." : "Select a style, then press Preview intro to see it in motion.";
  document.querySelectorAll("[data-intro-preset]").forEach((button) => {
    const selected = button.dataset.introPreset === preset;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  const activeTemplate = Object.entries(INTRO_TEMPLATES).find(([, template]) =>
    template.mode === mode
      && template.preset === preset
      && template.duration_ms === Number($("intro-duration-range").value)
      && template.background === backgroundColor
      && template.brand_color === brandColor
      && template.welcome_message === $("intro-message").value.trim()
  )?.[0] || "";
  document.querySelectorAll("[data-intro-template]").forEach((button) => {
    const selected = button.dataset.introTemplate === activeTemplate;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  const assetStatus = $("intro-asset-status");
  const assetTypeLabel = state.intro?.asset_type === "video/webm" ? "WebM video uploaded" : state.intro?.asset_type === "video/mp4" ? "MP4 video uploaded" : "No custom video uploaded.";
  assetStatus.textContent = assetUrl
    ? videoAsset
      ? `${assetTypeLabel} · ready for preview`
      : "An older animation asset is attached. Replace it with MP4 or WebM, or remove it."
    : "No custom video uploaded.";
  assetStatus.classList.toggle("has-asset", Boolean(assetUrl));
  $("intro-remove-asset").hidden = !assetUrl;
  $("play-intro-preview").disabled = mode === "none" || (mode === "custom_upload" && !videoAsset);
  $("play-intro-preview").innerHTML = mode === "none" ? "<span aria-hidden=\"true\">▶</span> Intro is off" : "<span aria-hidden=\"true\">▶</span> Preview intro";
  $("intro-preview-mode-label").textContent = mode === "none" ? "Chat opens directly" : mode === "custom_upload" ? (videoAsset ? "Custom brand video" : "Video needed") : "Logo-led welcome";
  const durationSeconds = (Number($("intro-duration-range").value || 1400) / 1000).toFixed(1);
  $("intro-duration").value = durationSeconds;
  $("intro-preview-duration-label").textContent = `${durationSeconds} seconds`;
  if (!state.introDirty) $("intro-save-status").textContent = mode === "none" ? "Intro is off" : "Saved · active for guests";
}

function markIntroDirty() {
  if (state.introPreviewTimer) stopIntroPreview("");
  state.introDirty = true;
  updateIntroPreview();
  $("intro-save-status").textContent = "Unsaved changes";
}

function introPayload() {
  const duration = Math.round(Number($("intro-duration").value || 1.4) * 1000);
  return {
    mode: $("intro-mode").value,
    preset: $("intro-preset").value,
    duration_ms: Math.max(300, Math.min(8000, duration)),
    background: $("intro-background").value,
    brand_color: $("intro-brand-color").value,
    welcome_message: $("intro-message").value.trim(),
    first_visit_only: $("intro-first-visit").checked,
    allow_skip: $("intro-skip").checked,
  };
}

async function saveIntro({ quiet = false } = {}) {
  const mode = $("intro-mode").value;
  const isVideoAsset = Boolean(state.intro?.asset_url && ["video/webm", "video/mp4"].includes(state.intro?.asset_type));
  if (mode === "custom_upload" && !isVideoAsset) {
    showToast("Upload a WebM or MP4 video before activating custom video mode.", "error");
    return;
  }
  $("save-intro").disabled = true;
  const oldLabel = $("save-intro").textContent;
  $("save-intro").textContent = "Saving…";
  try {
    const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/intro`, {
      method: "PUT",
      body: JSON.stringify({ data: {
        ...introPayload(),
        // Old Lottie/JSON uploads are no longer supported; clear them when saving a video-free mode.
        asset_url: isVideoAsset ? state.intro.asset_url : "",
        asset_type: isVideoAsset ? state.intro.asset_type : "",
      } }),
    });
    state.intro = result;
    state.introDirty = false;
    updateIntroPreview();
    $("intro-save-status").textContent = result.mode === "none" ? "Saved · intro is off" : "Saved · active for guests";
    if (!quiet) showToast("Intro experience saved and activated.");
  } finally {
    $("save-intro").disabled = false;
    $("save-intro").textContent = oldLabel;
  }
}

async function uploadIntroAsset(file) {
  if (!file) return;
  const extension = file.name.split(".").pop()?.toLowerCase();
  const inferredType = extension === "webm" ? "video/webm" : extension === "mp4" ? "video/mp4" : "";
  const declaredType = (file.type || "").toLowerCase();
  const contentType = !declaredType || declaredType === "application/octet-stream" ? inferredType : declaredType;
  if (file.size > 12 * 1024 * 1024) {
    showToast("Video must be 12 MB or smaller.", "error");
    $("intro-upload").value = "";
    return;
  }
  if (![["webm", "video/webm"], ["mp4", "video/mp4"]].some(([ext, type]) => extension === ext && contentType === type)) {
    showToast("Choose an MP4 or WebM video file.", "error");
    $("intro-upload").value = "";
    return;
  }
  const uploadStatus = $("intro-asset-status");
  const uploadButton = $("save-intro");
  uploadStatus.textContent = "Uploading and checking video…";
  uploadStatus.classList.remove("has-asset");
  uploadButton.disabled = true;
  try {
    const previousAssetUrl = state.intro?.asset_url || "";
    const content = await file.arrayBuffer();
    const bytes = new Uint8Array(content);
    let binary = "";
    for (let offset = 0; offset < bytes.length; offset += 0x8000) binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/intro/upload`, {
      method: "POST",
      body: JSON.stringify({ filename: file.name, content_type: contentType, content_base64: btoa(binary) }),
    });
    state.intro = result;
    $("intro-mode").value = "custom_upload";
    await saveIntro({ quiet: true });
    if (previousAssetUrl && previousAssetUrl !== state.intro?.asset_url) {
      const previousFilename = previousAssetUrl.split("?", 1)[0].split("/").pop();
      await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/intro/assets/${encodeURIComponent(previousFilename)}`, { method: "DELETE" }).catch(() => {});
    }
    state.introDirty = false;
    $("intro-upload").value = "";
    updateIntroPreview();
    showToast("Intro video uploaded and saved.");
  } catch (error) {
    uploadStatus.textContent = error.message || "Video upload failed.";
    $("intro-upload").value = "";
    throw error;
  } finally {
    uploadButton.disabled = false;
  }
}

async function removeIntroAsset() {
  const button = $("intro-remove-asset");
  button.disabled = true;
  try {
    state.intro = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/intro/asset`, { method: "DELETE" });
    await loadIntro();
    showToast("Uploaded intro video removed.");
  } finally {
    button.disabled = false;
  }
}

function setIntroDevice(device) {
  $("intro-preview-device").className = `intro-preview-device ${device}`;
  $("intro-preview-device-label").textContent = device === "mobile" ? "Mobile · 390 px" : "Desktop · 1440 px";
  document.querySelectorAll("[data-intro-device]").forEach((button) => {
    const selected = button.dataset.introDevice === device;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}

function stopIntroPreview(message = "Preview ended.") {
  if (state.introPreviewTimer) clearTimeout(state.introPreviewTimer);
  state.introPreviewTimer = null;
  $("intro-preview-card").classList.remove("playing");
  $("intro-preview-skip").disabled = true;
  $("intro-preview-progress-bar").style.transition = "none";
  $("intro-preview-progress-bar").style.width = "0%";
  const video = $("intro-preview-video");
  video.pause();
  try { video.currentTime = 0; } catch {}
  $("play-intro-preview").innerHTML = "<span aria-hidden=\"true\">▶</span> Preview intro";
  if (message) showToast(message);
}

async function playIntroPreview() {
  if ($("play-intro-preview").disabled) return;
  if (state.introPreviewTimer) clearTimeout(state.introPreviewTimer);
  const card = $("intro-preview-card");
  const video = $("intro-preview-video");
  const duration = Math.max(300, Math.min(8000, Number($("intro-duration-range").value || 1400)));
  card.classList.remove("playing");
  void card.offsetWidth;
  card.classList.add("playing");
  $("intro-preview-skip").disabled = !$("intro-skip").checked;
  $("intro-preview-progress-bar").style.transition = "none";
  $("intro-preview-progress-bar").style.width = "0%";
  requestAnimationFrame(() => {
    $("intro-preview-progress-bar").style.transition = `width ${duration}ms linear`;
    $("intro-preview-progress-bar").style.width = "100%";
  });
  if (!video.hidden) {
    video.currentTime = 0;
    await video.play().catch(() => { video.hidden = true; showToast("Video preview could not play. Check that the file is a valid MP4 or WebM.", "error"); });
  }
  $("play-intro-preview").innerHTML = "<span aria-hidden=\"true\">Ⅱ</span> Previewing…";
  state.introPreviewTimer = window.setTimeout(() => stopIntroPreview("Intro preview finished."), duration);
}

async function loadConversations() {
  const button = $("refresh-conversations");
  const originalLabel = button.textContent;
  button.disabled = true;
  button.textContent = "Refreshing…";
  try {
    const data = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/conversations`);
    state.conversations = Array.isArray(data.conversations) ? data.conversations : [];
    $("conversation-retention-days").value = data.retention?.retention_days || 30;
    const selectedId = state.selectedConversation?.session_id;
    state.selectedConversation = selectedId ? state.conversations.find((item) => item.session_id === selectedId) || null : null;
    $("conversation-last-refreshed").textContent = `Updated ${new Intl.DateTimeFormat(undefined, { timeStyle: "short" }).format(new Date())}`;
    renderConversations();
    renderConversationMessages();
  } finally {
    button.disabled = false;
    button.textContent = originalLabel;
  }
}

async function saveConversationRetention() {
  const retentionDays = Number($("conversation-retention-days").value);
  if (!Number.isInteger(retentionDays) || retentionDays < 1 || retentionDays > 365) {
    throw new Error("Choose a retention period from 1 to 365 days.");
  }
  const button = $("save-conversation-retention");
  button.disabled = true;
  try {
    await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/conversations/retention`, { method: "PUT", body: JSON.stringify({ retention_days: retentionDays }) });
    await loadConversations();
    showToast("Conversation retention updated.");
  } finally {
    button.disabled = false;
  }
}

function conversationStateKey(conversation) {
  if (["waiting_for_staff", "assigned", "human_active", "resolved"].includes(conversation?.state)) return conversation.state;
  if (conversation?.status === "closed") return "resolved";
  if (conversation?.status === "escalated") return "waiting_for_staff";
  return "ai_active";
}

function conversationStateLabel(status) {
  return ({
    waiting_for_staff: "Waiting for staff",
    assigned: "Assigned",
    human_active: "Staff handling",
    ai_active: "With AI",
    resolved: "Resolved",
  })[status] || "With AI";
}

function renderConversationSummary() {
  const counts = { all: state.conversations.length, waiting_for_staff: 0, assigned: 0, human_active: 0, ai_active: 0, resolved: 0 };
  for (const item of state.conversations) counts[conversationStateKey(item)] += 1;
  $("conversation-count-all").textContent = counts.all;
  $("conversation-count-waiting").textContent = counts.waiting_for_staff;
  $("conversation-count-assigned").textContent = counts.assigned;
  $("conversation-count-active").textContent = counts.human_active;
  $("conversation-count-ai").textContent = counts.ai_active;
  $("conversation-count-resolved").textContent = counts.resolved;
  const activeFilter = $("conversation-status-filter").value;
  for (const card of document.querySelectorAll("[data-conversation-filter]")) {
    const selected = card.dataset.conversationFilter === activeFilter;
    card.classList.toggle("selected", selected);
    card.setAttribute("aria-pressed", String(selected));
  }
}

function renderConversationEmptyState(list, message, detailText, actionLabel = "", action = null) {
  const empty = document.createElement("div");
  empty.className = "conversation-empty";
  const title = document.createElement("strong");
  title.textContent = message;
  const detail = document.createElement("span");
  detail.textContent = detailText;
  empty.append(title, detail);
  if (actionLabel && action) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.textContent = actionLabel;
    button.addEventListener("click", action);
    empty.appendChild(button);
  }
  list.appendChild(empty);
}

function renderConversations() {
  const query = $("conversation-search").value.trim().toLowerCase();
  const status = $("conversation-status-filter").value;
  const list = $("conversation-list");
  const scrollTop = list.scrollTop;
  list.replaceChildren();
  renderConversationSummary();
  const matching = state.conversations.filter((item) => {
    const statusMatches = !status || conversationStateKey(item) === status;
    const text = [item.session_id, item.client_id, item.restaurant_name, item.assigned_user_name, item.escalation_reason, ...(item.messages || []).map((message) => message.content)]
      .filter(Boolean).join(" ").toLowerCase();
    return statusMatches && (!query || text.includes(query));
  });
  $("conversation-result-count").textContent = query || status
    ? `${matching.length} of ${state.conversations.length} conversations`
    : `${matching.length} ${matching.length === 1 ? "conversation" : "conversations"}`;
  for (const conversation of matching) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "conversation-row";
    const isSelected = conversation.session_id === state.selectedConversation?.session_id;
    row.classList.toggle("selected", isSelected);
    row.setAttribute("aria-pressed", String(isSelected));
    const top = document.createElement("span");
    top.className = "conversation-row-top";
    const title = document.createElement("strong");
    title.textContent = conversation.restaurant_name || "Hotel guest";
    const badge = document.createElement("span");
    const currentStatus = conversationStateKey(conversation);
    badge.className = `conversation-status-badge ${currentStatus}`;
    badge.textContent = conversationStateLabel(currentStatus);
    top.append(title, badge);
    const meta = document.createElement("span");
    meta.className = "conversation-row-meta";
    const latestAt = conversation.last_message_at || conversation.created_at;
    meta.textContent = `${conversation.session_id.slice(0, 12)} · ${conversation.message_count || 0} shared updates · ${formatDate(latestAt)}${conversation.assigned_user_name ? ` · ${conversation.assigned_user_name}` : " · Unassigned"}`;
    const preview = document.createElement("span");
    preview.className = "conversation-row-preview";
    const lastMessage = conversation.messages?.at(-1);
    preview.textContent = conversation.escalation_reason || lastMessage?.content || "No staff request details yet";
    row.append(top, meta, preview);
    row.addEventListener("click", () => {
      state.selectedConversation = conversation;
      renderConversations();
      renderConversationMessages();
    });
    list.appendChild(row);
  }
  list.scrollTop = scrollTop;
  if (!matching.length) {
    const hasFilter = Boolean(query || status);
    renderConversationEmptyState(
      list,
      hasFilter ? "No conversations match these filters" : "No conversations yet",
      hasFilter ? "Try a different status or search term." : "Guest staff requests will appear here when someone asks a restaurant team for help.",
      hasFilter ? "Clear filters" : can("concierge.view") ? "Open guest preview" : "",
      hasFilter ? () => { $("conversation-search").value = ""; $("conversation-status-filter").value = ""; renderConversations(); }
        : can("concierge.view") ? () => activatePanel("guest") : null,
    );
  }
}

function renderConversationMessages() {
  const conversation = state.selectedConversation;
  const list = $("conversation-messages");
  list.replaceChildren();
  if (conversation?.escalation_reason) {
    const row = document.createElement("article");
    row.className = "conversation-message guest";
    const meta = document.createElement("div");
    meta.className = "conversation-message-meta";
    const sender = document.createElement("strong");
    sender.textContent = "Guest request";
    meta.appendChild(sender);
    const bubble = document.createElement("div");
    bubble.className = "conversation-message-bubble";
    bubble.textContent = conversation.escalation_reason;
    row.append(meta, bubble);
    list.appendChild(row);
  }
  for (const message of conversation?.messages || []) {
    const role = String(message.role || "assistant").toLowerCase();
    const roleClass = role === "staff" ? "staff" : ["user", "guest"].includes(role) ? "guest" : role === "system" ? "system" : "assistant";
    const roleLabel = roleClass === "guest" ? "Guest" : roleClass === "staff" ? "Staff" : roleClass === "system" ? "System" : "AI assistant";
    const row = document.createElement("article");
    row.className = `conversation-message ${roleClass}`;
    const meta = document.createElement("div");
    meta.className = "conversation-message-meta";
    const sender = document.createElement("strong");
    sender.textContent = roleLabel;
    const timestamp = document.createElement("time");
    timestamp.textContent = formatDate(message.created_at);
    meta.append(sender, timestamp);
    const bubble = document.createElement("div");
    bubble.className = "conversation-message-bubble";
    bubble.textContent = message.content || "";
    row.append(meta, bubble);
    if (message.error) {
      const error = document.createElement("small");
      error.className = "conversation-message-error-note";
      error.textContent = `Delivery issue: ${message.error}`;
      row.appendChild(error);
    }
    list.appendChild(row);
  }
  const title = $("conversation-detail-name");
  const detail = $("conversation-detail-meta");
  const badge = $("conversation-detail-status");
  if (!conversation) {
    title.textContent = "Select a conversation";
    detail.textContent = "Choose a staff request from the inbox to review the guest's shared reason and staff replies.";
    badge.hidden = true;
    renderConversationEmptyState(list, "Your request details will appear here", "Select a staff request from the inbox to review the guest's shared reason and staff replies.");
  } else {
    const currentStatus = conversationStateKey(conversation);
    title.textContent = conversation.restaurant_name || "Hotel guest";
    detail.textContent = `Session ${conversation.session_id.slice(0, 12)} · ${conversation.message_count || 0} shared updates · Last activity ${formatDate(conversation.last_message_at || conversation.created_at)}`;
    badge.hidden = false;
    badge.className = `conversation-status-badge ${currentStatus}`;
    badge.textContent = conversationStateLabel(currentStatus);
    if (!conversation.messages?.length && !conversation.escalation_reason) renderConversationEmptyState(list, "No staff request was submitted", "Guest concierge messages stay private. Staff replies appear here after a guest requests restaurant support.");
    list.scrollTop = list.scrollHeight;
  }
  const restaurantConversation = Boolean(conversation?.restaurant_id);
  const propertyAdmin = can("properties.all") || can("properties.edit");
  const currentStatus = conversationStateKey(conversation);
  const canAccept = can("conversations.takeover") && restaurantConversation && (currentStatus === "waiting_for_staff" || (currentStatus === "assigned" && conversation?.assigned_user_id === state.auth?.id));
  const canReturn = can("conversations.return_to_ai") && currentStatus === "human_active" && (conversation?.assigned_user_id === state.auth?.id || can("conversations.assign"));
  const takeover = $("toggle-takeover");
  $("conversation-detail-actions").hidden = !conversation;
  takeover.hidden = !conversation || (restaurantConversation
    ? !can("conversations.takeover") && !can("conversations.return_to_ai")
    : !propertyAdmin || !can("conversations.takeover"));
  takeover.disabled = !conversation || (restaurantConversation ? !(canAccept || canReturn) : !propertyAdmin || !can("conversations.takeover") || currentStatus === "resolved");
  takeover.textContent = currentStatus === "human_active" ? "Return to AI" : restaurantConversation ? "Accept Conversation" : "Take Over";
  takeover.title = takeover.disabled && currentStatus === "assigned" ? "Only the assigned staff member can accept this conversation." : "";
  const resolve = $("close-conversation");
  resolve.hidden = !conversation || !can("conversations.resolve");
  resolve.disabled = !conversation || !can("conversations.resolve") || (restaurantConversation ? currentStatus === "resolved" || (conversation?.assigned_user_id !== state.auth?.id && !can("conversations.assign")) : !propertyAdmin || currentStatus === "resolved");
  resolve.textContent = currentStatus === "resolved" ? "Resolved" : restaurantConversation ? "Resolve" : "Close";
  const assignment = $("conversation-assignment");
  assignment.hidden = !restaurantConversation || !can("conversations.assign");
  const staffSelect = $("conversation-staff-select");
  staffSelect.disabled = !restaurantConversation || !can("conversations.assign") || !staffSelect.options.length || staffSelect.options.length < 2;
  const assign = $("assign-conversation");
  assign.hidden = !restaurantConversation || !can("conversations.assign");
  assign.textContent = conversation?.assigned_user_id ? "Reassign" : "Assign";
  assign.disabled = !restaurantConversation || !can("conversations.assign") || !staffSelect.value || staffSelect.value === conversation?.assigned_user_id;
  const canReply = conversation && can("conversations.reply") && currentStatus === "human_active" && (restaurantConversation
    ? conversation.assigned_user_id === state.auth?.id || can("conversations.assign")
    : propertyAdmin);
  $("staff-response").disabled = !canReply;
  $("send-staff-response").disabled = !canReply || !$("staff-response").value.trim();
  $("conversation-reply-hint").textContent = !conversation
    ? "Select a conversation to reply."
    : currentStatus === "resolved" ? "This conversation is resolved."
      : !can("conversations.reply") ? "Your role cannot reply to guest conversations."
        : currentStatus !== "human_active" ? "Accept the conversation before replying as staff."
          : restaurantConversation && conversation.assigned_user_id !== state.auth?.id && !can("conversations.assign") ? "This conversation is assigned to another staff member."
            : "Replies are sent to the guest conversation.";
  loadAssignableRestaurantStaff().catch((error) => showToast(error.message, "error"));
}

async function setConversationState(status, humanTakeover) {
  if (!state.selectedConversation) return;
  const conversation = state.selectedConversation;
  const base = `/api/admin/properties/${encodeURIComponent(currentPropertyId())}/conversations/${encodeURIComponent(conversation.session_id)}`;
  if (conversation.restaurant_id) {
    const action = status === "closed" ? "resolve" : humanTakeover ? "accept" : "return-to-ai";
    await jsonFetch(`${base}/${action}`, { method: "POST" });
  } else {
    await jsonFetch(base, { method: "PUT", body: JSON.stringify({ status, human_takeover: humanTakeover }) });
  }
  await loadConversations(); showToast("Conversation updated.");
}

async function loadAssignableRestaurantStaff() {
  const select = $("conversation-staff-select");
  const conversation = state.selectedConversation;
  if (!select) return;
  select.replaceChildren();
  if (!conversation?.restaurant_id || !can("conversations.assign")) return;
  const selectedId = conversation.session_id;
  select.disabled = true;
  select.appendChild(new Option("Loading staff…", ""));
  const data = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/restaurants/${encodeURIComponent(conversation.restaurant_id)}/staff`);
  if (state.selectedConversation?.session_id !== selectedId) return;
  select.replaceChildren(new Option("Choose a staff member", ""));
  for (const person of data.staff || []) select.appendChild(new Option(person.display_name, person.user_id));
  if (!data.staff?.length) select.options[0].textContent = "No eligible staff available";
  if (conversation.assigned_user_id && [...select.options].some((option) => option.value === conversation.assigned_user_id)) {
    select.value = conversation.assigned_user_id;
  }
  select.disabled = !data.staff?.length;
  const assign = $("assign-conversation");
  assign.textContent = conversation.assigned_user_id ? "Reassign" : "Assign";
  assign.disabled = !select.value || select.value === conversation.assigned_user_id;
}

async function assignSelectedConversation() {
  const conversation = state.selectedConversation;
  const userId = $("conversation-staff-select").value;
  if (!conversation?.restaurant_id || !userId) throw new Error("Choose an assigned restaurant staff member.");
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/conversations/${encodeURIComponent(conversation.session_id)}/assign`, { method: "POST", body: JSON.stringify({ user_id: userId }) });
  await loadConversations(); showToast("Conversation assigned.");
}

async function sendStaffResponse() {
  const message = $("staff-response").value.trim();
  if (!state.selectedConversation || !message) throw new Error("Enter a staff response.");
  const button = $("send-staff-response");
  button.disabled = true;
  button.textContent = "Sending…";
  try {
    await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/conversations/${encodeURIComponent(state.selectedConversation.session_id)}/messages`, { method: "POST", body: JSON.stringify({ message }) });
    $("staff-response").value = "";
    await loadConversations();
    showToast("Staff response sent.");
  } finally {
    button.textContent = "Send Response";
    renderConversationMessages();
  }
}

async function loadServiceCatalog() {
  state.catalog = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/service-catalog`);
  const departmentSelect = $("catalog-service-department");
  const requestSelect = $("service-type");
  const requestDepartment = $("service-department");
  const selectedService = requestSelect.value;
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
  requestDepartment.disabled = true;
  if (state.catalog.services.some((item) => item.service_id === selectedService && item.enabled && !item.archived)) {
    requestSelect.value = selectedService;
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
    const edit = makeActionButton("Edit", () => {
      $("department-id").value = department.department_id;
      $("department-name").value = department.name;
      $("department-sla").value = department.default_sla_minutes;
      $("department-escalation").value = department.escalation_target || "";
      $("department-enabled").checked = department.enabled;
    });
    row.appendChild(edit);
    const remove = makeActionButton("Delete", () => deleteDepartment(department.department_id), true);
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
      const button = makeActionButton(label, handler, label !== "Edit");
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
  $("service-department").disabled = true;
  $("service-sla").disabled = !service;
  if (service) $("service-sla").value = service.sla_minutes;
  updateCreateServiceRequestButton();
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
    const edit = makeActionButton("Edit", () => editRecommendation(recommendation));
    const remove = makeActionButton("Delete", () => deleteRecommendation(recommendation.recommendation_id), true);
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

function updateCreateServiceRequestButton() {
  const hasServices = state.catalog.services.some((item) => item.enabled && !item.archived);
  const serviceSelect = $("service-type");
  const button = $("create-service-request");
  const sla = Number($("service-sla").value);
  const validSla = Number.isInteger(sla) && sla >= 1 && sla <= 1440;
  $("service-catalog-empty").hidden = hasServices;
  $("open-service-catalog").hidden = hasServices;
  serviceSelect.disabled = !hasServices;
  button.disabled = !serviceSelect.value || !$("service-description").value.trim() || !validSla || !hasServices;
}

function serviceStatusLabel(status) {
  return ({ new: "New", assigned: "Assigned", accepted: "Accepted", in_progress: "In progress", delivered: "Delivered", completed: "Completed", cancelled: "Cancelled" })[status] || String(status || "Unknown").replaceAll("_", " ");
}

function serviceRequestIsOpen(request) {
  return !["completed", "cancelled"].includes(request.status);
}

function serviceSlaLabel(request) {
  if (request.status === "completed" || request.sla_state === "completed") return "Completed";
  if (request.status === "cancelled" || request.sla_state === "cancelled") return "Cancelled";
  if (request.sla_state === "overdue") return "Overdue";
  if (request.sla_state === "warning") return "Due soon";
  return "On track";
}

function serviceRequestDateKey(timestamp, timezone = state.property?.timezone || "UTC") {
  const seconds = Number(timestamp);
  if (!Number.isFinite(seconds)) return "";
  const formatter = new Intl.DateTimeFormat("en", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  const parts = Object.fromEntries(formatter.formatToParts(new Date(seconds * 1000)).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function serviceRequestCompletedToday(request, today = serviceRequestDateKey(Date.now() / 1000)) {
  return request.status === "completed"
    && request.completed_at !== null
    && request.completed_at !== undefined
    && serviceRequestDateKey(request.completed_at) === today;
}

function renderServiceRequestSummary() {
  const requests = state.serviceRequests || [];
  const open = requests.filter(serviceRequestIsOpen);
  const counts = {
    open: open.length,
    in_progress: open.filter((request) => request.status === "in_progress").length,
    due_soon: open.filter((request) => request.sla_state === "warning").length,
    overdue: open.filter((request) => request.sla_state === "overdue").length,
    completed_today: requests.filter((request) => serviceRequestCompletedToday(request)).length,
  };
  for (const [key, count] of Object.entries(counts)) $(`request-count-${key}`).textContent = count;
  const activeFilter = $("service-request-status-filter").value || "all";
  for (const card of document.querySelectorAll("[data-request-filter]")) {
    card.classList.toggle("selected", card.dataset.requestFilter === activeFilter);
  }
}

function renderServiceRequestHistory(request, container) {
  const detailText = (event) => {
    const detail = event.detail || {};
    if (event.action === "created") return "Request added to the queue";
    if (event.action === "status_changed") return `Status changed to ${serviceStatusLabel(detail.status)}`;
    const labels = { department: "Department", assigned_to: "Assigned to", priority: "Priority", note: "Note" };
    const changes = Object.entries(detail).map(([key, value]) => `${labels[key] || key.replaceAll("_", " ")}: ${value}`).filter(Boolean);
    return changes.length ? changes.join(" · ") : String(event.action || "Request updated").replaceAll("_", " ");
  };
  container.replaceChildren();
  container.dataset.loaded = "true";
  delete container.dataset.loading;
  if (!container._history?.length) {
    container.textContent = "No activity has been recorded yet.";
    return;
  }
  for (const event of container._history) {
    const row = document.createElement("div");
    row.className = "request-history-event";
    const description = document.createElement("strong");
    description.textContent = detailText(event);
    const date = document.createElement("time");
    date.textContent = formatDate(event.created_at);
    row.append(description, date);
    container.appendChild(row);
  }
}

function renderServiceRequests() {
  const list = $("service-request-list");
  const requests = state.serviceRequests || [];
  const filter = $("service-request-status-filter").value;
  const query = $("service-request-search").value.trim().toLowerCase();
  const today = serviceRequestDateKey(Date.now() / 1000);
  renderServiceRequestSummary();
  const matching = requests.filter((request) => {
    const matchesFilter = !filter
      || filter === "all"
      || (filter === "open" && serviceRequestIsOpen(request))
      || (filter === "due_soon" && serviceRequestIsOpen(request) && request.sla_state === "warning")
      || (filter === "overdue" && serviceRequestIsOpen(request) && request.sla_state === "overdue")
      || (filter === "completed_today" && serviceRequestCompletedToday(request, today))
      || request.status === filter;
    const searchText = [request.request_id, request.request_type, request.room, request.description, request.department, request.assigned_to, ...(request.notes || []).map((note) => note.text)].join(" ").toLowerCase();
    return matchesFilter && (!query || searchText.includes(query));
  });
  $("service-request-result-count").textContent = `${matching.length} ${matching.length === 1 ? "request" : "requests"}`;
  list.replaceChildren();
  if (!matching.length) {
    const empty = document.createElement("div");
    empty.className = "request-queue-empty";
    const title = document.createElement("strong");
    title.textContent = requests.length ? "No requests match these filters" : "No service requests yet";
    const message = document.createElement("span");
    message.textContent = requests.length
      ? "Change the status filter or search term to see other requests."
      : "Guest-submitted and staff-created requests will appear here for assignment and follow-up.";
    empty.append(title, message);
    list.appendChild(empty);
    return;
  }

  const make = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const addDetail = (grid, label, value) => {
    const cell = make("div", "service-request-detail");
    cell.append(make("span", "", label), make("strong", "", value || "Not set"));
    grid.appendChild(cell);
  };
  for (const request of matching) {
    const card = make("article", "service-request-card");
    const header = make("header", "service-request-card-header");
    const title = make("div", "service-request-card-title");
    title.append(make("p", "", `REQUEST ${request.request_id || "—"}`));
    title.append(make("h3", "", `${request.request_type || "Guest request"} · ${request.room ? `Room ${request.room}` : "Room not recorded"}`));
    const badges = make("div", "service-request-badges");
    badges.append(make("span", `request-status-badge status-${request.status}`, serviceStatusLabel(request.status)));
    badges.append(make("span", `request-sla-badge sla-${request.sla_state}`, serviceSlaLabel(request)));
    header.append(title, badges);
    card.appendChild(header);

    const description = make("p", "service-request-description", request.description || "No request description.");
    card.appendChild(description);
    const facts = make("div", "service-request-facts");
    const targetMinutes = request.sla_target_seconds ? Math.ceil(Number(request.sla_target_seconds) / 60) : null;
    addDetail(facts, "Department", request.department || "Unassigned");
    addDetail(facts, "Assigned to", request.assigned_to || "Unassigned");
    addDetail(facts, "Priority", String(request.priority || "normal").replace(/^./, (letter) => letter.toUpperCase()));
    addDetail(facts, "Created", formatDate(request.created_at));
    addDetail(facts, "SLA target", targetMinutes ? `${targetMinutes} minutes` : "No target set");
    addDetail(facts, "SLA due", request.due_at ? formatDate(request.due_at) : "No due time");
    addDetail(facts, "Last updated", formatDate(request.updated_at));
    if (request.completed_at) addDetail(facts, "Completed", formatDate(request.completed_at));
    if (request.stay_id) addDetail(facts, "Guest stay", request.stay_id);
    card.appendChild(facts);

    const notes = Array.isArray(request.notes) ? request.notes.filter((item) => item?.text) : [];
    if (notes.length) {
      const notesSection = make("div", "service-request-notes");
      notesSection.appendChild(make("strong", "", "Operational notes"));
      for (const item of notes) notesSection.appendChild(make("p", "", `${item.text} · ${formatDate(item.created_at)}`));
      card.appendChild(notesSection);
    }

    const controls = make("div", "service-request-edit");
    const departmentLabel = make("label", "", "Route to department");
    const department = document.createElement("select");
    department.setAttribute("aria-label", `Department for request ${request.request_id}`);
    department.appendChild(new Option("Unassigned", ""));
    for (const item of state.catalog.departments) department.appendChild(new Option(item.name, item.name));
    if (request.department && ![...department.options].some((option) => option.value === request.department)) department.appendChild(new Option(request.department, request.department));
    department.value = request.department || "";
    departmentLabel.appendChild(department);
    const assignedLabel = make("label", "", "Assigned staff member");
    const assigned = document.createElement("input");
    assigned.placeholder = "Name or staff ID";
    assigned.setAttribute("aria-label", `Assignee for request ${request.request_id}`);
    assigned.value = request.assigned_to || "";
    assignedLabel.appendChild(assigned);
    const priorityLabel = make("label", "", "Priority");
    const priority = document.createElement("select");
    priority.setAttribute("aria-label", `Priority for request ${request.request_id}`);
    for (const value of ["low", "normal", "high", "urgent"]) priority.appendChild(new Option(value[0].toUpperCase() + value.slice(1), value));
    priority.value = request.priority || "normal";
    priorityLabel.appendChild(priority);
    const noteLabel = make("label", "", "Add a note");
    const note = document.createElement("input");
    note.placeholder = "Visible in this request’s activity history";
    note.setAttribute("aria-label", `Operational note for request ${request.request_id}`);
    noteLabel.appendChild(note);
    const save = make("button", "secondary", "Save updates");
    save.type = "button";
    save.addEventListener("click", () => updateServiceRequest(request.request_id, { department: department.value, assigned_to: assigned.value, priority: priority.value, note: note.value }).catch((error) => showToast(error.message, "error")));
    controls.append(departmentLabel, assignedLabel, priorityLabel, noteLabel, save);
    card.appendChild(controls);

    const actions = make("div", "service-request-actions");
    const next = nextServiceStatus(request.status);
    if (next) {
      const advance = make("button", "secondary", `Mark ${serviceStatusLabel(next)}`);
      advance.type = "button";
      advance.addEventListener("click", () => updateServiceStatus(request.request_id, next).catch((error) => showToast(error.message, "error")));
      actions.appendChild(advance);
    }
    if (serviceRequestIsOpen(request)) {
      const complete = make("button", "secondary", "Mark completed");
      complete.type = "button";
      complete.addEventListener("click", () => updateServiceStatus(request.request_id, "completed").catch((error) => showToast(error.message, "error")));
      actions.appendChild(complete);
    }
    card.appendChild(actions);

    const history = document.createElement("details");
    history.className = "service-request-history";
    const summary = make("summary", "", "View activity history");
    const historyContent = make("div", "service-request-history-content", "Open to load the request’s status and assignment changes.");
    history.append(summary, historyContent);
    history.addEventListener("toggle", async () => {
      if (!history.open || historyContent.dataset.loaded === "true" || historyContent.dataset.loading === "true") return;
      historyContent.dataset.loading = "true";
      historyContent.textContent = "Loading request history…";
      try {
        const response = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/service-requests/${encodeURIComponent(request.request_id)}/history`);
        historyContent._history = response.history || [];
        renderServiceRequestHistory(request, historyContent);
      } catch (error) {
        delete historyContent.dataset.loading;
        historyContent.textContent = "History could not be loaded. Close and reopen this section to try again.";
        showToast(error.message, "error");
      }
    });
    card.appendChild(history);
    list.appendChild(card);
  }
}

async function loadServiceRequests() {
  const button = $("refresh-service-requests");
  const originalLabel = button?.textContent || "Refresh";
  if (button) { button.disabled = true; button.textContent = "Refreshing…"; }
  try {
    await loadServiceCatalog();
    const data = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/hospitality`);
    state.serviceRequests = Array.isArray(data.service_requests) ? data.service_requests : [];
    renderServiceRequests();
    $("request-last-updated").textContent = `Updated ${new Intl.DateTimeFormat(undefined, { timeStyle: "short" }).format(new Date())}`;
  } finally {
    if (button) { button.disabled = false; button.textContent = originalLabel; }
  }
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
  if (!$("service-description").value.trim()) throw new Error("Add a short description of what the guest needs.");
  const slaMinutes = Number($("service-sla").value);
  if (!Number.isInteger(slaMinutes) || slaMinutes < 1 || slaMinutes > 1440) throw new Error("Set an SLA target between 1 and 1,440 minutes.");
  await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/service-requests`, {
    method: "POST",
    body: JSON.stringify({ data: {
      room: $("service-room").value.trim() || null,
      service_id: $("service-type").value,
      description: $("service-description").value.trim(),
      priority: $("service-priority").value,
      sla_target_seconds: slaMinutes * 60,
    } }),
  });
  $("service-description").value = "";
  updateCreateServiceRequestButton();
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
  $("admin-department").value = user?.department_id || "";
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
  await loadRestaurantAssignmentOptions(user?.restaurant_ids || []);
  $("user-dialog").showModal();
}

async function loadRestaurantAssignmentOptions(selectedIds = []) {
  const requestId = ++restaurantAssignmentRequestId;
  const fieldset = $("restaurant-assignment-fieldset");
  const list = $("restaurant-assignment-list");
  const role = state.roles.find((item) => item.role_id === $("admin-role").value);
  const restaurantRole = role?.permissions?.some((permission) => ["restaurant.view", "restaurant.manage"].includes(permission));
  const propertyId = $("admin-property").value;
  list.replaceChildren();
  fieldset.hidden = !restaurantRole || !propertyId;
  if (!restaurantRole || !propertyId) return;
  const data = await jsonFetch("/api/admin/properties/" + encodeURIComponent(propertyId) + "/hospitality");
  if (
    requestId !== restaurantAssignmentRequestId
    || propertyId !== $("admin-property").value
    || role.role_id !== $("admin-role").value
  ) return;
  const selected = new Set(selectedIds);
  for (const restaurant of data.restaurants || []) {
    const label = document.createElement("label");
    label.className = "assignment-option";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = restaurant.restaurant_id;
    checkbox.checked = selected.has(restaurant.restaurant_id);
    const name = document.createElement("span");
    name.textContent = restaurant.name;
    label.append(checkbox, name);
    list.appendChild(label);
  }
  if (!list.children.length) list.textContent = "No restaurants are configured for this property.";
}

function selectedRestaurantAssignments() {
  return [...document.querySelectorAll("#restaurant-assignment-list input:checked")].map((item) => item.value);
}

async function saveUser(event) {
  event.preventDefault();
  const userId = $("user-id").value;
  const creating = !userId;
  const payload = {
    display_name: $("admin-display-name").value.trim(),
    property_id: $("admin-property").value || null,
    department_id: $("admin-department").value.trim() || null,
    role_id: $("admin-role").value,
    email: $("admin-email").value.trim() || null,
    status: $("admin-status").value,
    restaurant_ids: selectedRestaurantAssignments(),
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

function openAssistant(question = "") {
  if (!can("assistant.use")) return;
  activatePanel("ai-assistant");
  if (question) {
    $("assistant-page-input").value = question;
    setAssistantMode(assistantModeForQuestion(question));
  }
  requestAnimationFrame(() => $("assistant-page-input").focus());
}

function bindInvestigateButtons() {
  for (const button of document.querySelectorAll(".investigate-alert:not([data-bound])")) {
    button.dataset.bound = "true";
    button.addEventListener("click", () => openAssistant(button.dataset.question || "Investigate this alert"));
  }
  for (const button of document.querySelectorAll("[data-dashboard-panel]:not([data-bound])")) {
    button.dataset.bound = "true";
    button.addEventListener("click", () => activatePanel(button.dataset.dashboardPanel));
  }
}

function assistantLabel(value) {
  const labels = {
    ai_providers: "AI providers", guest_auth: "Guest authentication", request_queue: "Service request queue",
    restaurant_reporting: "Restaurant report", business_analytics: "Business analytics", sla: "SLA",
  };
  const normalized = String(value || "").replaceAll("_", " ");
  return labels[value] || normalized.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function assistantStatus(value) {
  const normalized = String(value || "").toLowerCase();
  return ["healthy", "warning", "critical", "unavailable", "available", "simulation", "restricted"].includes(normalized)
    ? normalized : "";
}

function appendAssistantEvidence(container, items = []) {
  if (!items.length) return;
  const section = document.createElement("section");
  section.className = "assistant-evidence";
  const heading = document.createElement("h4");
  heading.textContent = "What I checked";
  section.appendChild(heading);
  const list = document.createElement("div");
  list.className = "assistant-evidence-list";
  for (const item of items.slice(0, 18)) {
    const row = document.createElement("article");
    row.className = "assistant-evidence-item";
    const title = document.createElement("strong");
    title.textContent = item.label || "Check";
    row.appendChild(title);
    const state = assistantStatus(item.state);
    if (state) {
      const badge = document.createElement("span");
      badge.className = `assistant-state ${state}`;
      badge.textContent = state.replaceAll("_", " ");
      row.appendChild(badge);
    }
    if (item.detail) {
      const detail = document.createElement("p");
      detail.textContent = item.detail;
      row.appendChild(detail);
    }
    list.appendChild(row);
  }
  section.appendChild(list);
  container.appendChild(section);
}

function appendAssistantInlineText(container, value) {
  const pattern = /(\*\*\*.+?\*\*\*|\*\*.+?\*\*|__.+?__|`[^`]+`|\*[^*]+\*|_[^_]+_)/g;
  let cursor = 0;
  for (const match of value.matchAll(pattern)) {
    if (match.index > cursor) container.appendChild(document.createTextNode(value.slice(cursor, match.index)));
    const token = match[0];
    let element;
    let content;
    if (token.startsWith("***")) {
      element = document.createElement("strong");
      const emphasis = document.createElement("em");
      emphasis.textContent = token.slice(3, -3);
      element.appendChild(emphasis);
    } else if (token.startsWith("**") || token.startsWith("__")) {
      element = document.createElement("strong");
      content = token.slice(2, -2);
      element.textContent = content;
    } else if (token.startsWith("`")) {
      element = document.createElement("code");
      element.textContent = token.slice(1, -1);
    } else {
      element = document.createElement("em");
      content = token.slice(1, -1);
      element.textContent = content;
    }
    container.appendChild(element);
    cursor = match.index + token.length;
  }
  if (cursor < value.length) container.appendChild(document.createTextNode(value.slice(cursor)));
}

function appendAssistantFormattedCopy(container, value) {
  const lines = String(value).replaceAll("\r", "").split("\n");
  let paragraph = [];
  let list = null;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const block = document.createElement("p");
    paragraph.forEach((line, index) => {
      if (index) block.appendChild(document.createElement("br"));
      appendAssistantInlineText(block, line);
    });
    container.appendChild(block);
    paragraph = [];
  };
  const closeList = () => { list = null; };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      closeList();
      continue;
    }
    const headingMatch = trimmed.match(/^#{1,3}\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      closeList();
      const heading = document.createElement("h4");
      appendAssistantInlineText(heading, headingMatch[1]);
      container.appendChild(heading);
      continue;
    }
    const listMatch = trimmed.match(/^([-*+]\s+|\d+[.)]\s+)(.+)$/);
    if (listMatch) {
      flushParagraph();
      const ordered = /^\d/.test(listMatch[1]);
      const tag = ordered ? "ol" : "ul";
      if (!list || list.tagName.toLowerCase() !== tag) {
        closeList();
        list = document.createElement(tag);
        container.appendChild(list);
      }
      const item = document.createElement("li");
      appendAssistantInlineText(item, listMatch[2]);
      list.appendChild(item);
      continue;
    }
    closeList();
    paragraph.push(trimmed);
  }
  flushParagraph();
}

function assistantModeForQuestion(question) {
  const text = String(question || "").toLowerCase();
  if (/\b(report|summary|summarize|export|metrics|analytics|performance|trend|how many|activity for)\b/.test(text)) return "report";
  if (/\b(system|health|issue|problem|error|failure|down|slow|latency|database|provider|server|queue|alert|delayed|failing)\b/.test(text)) return "health";
  return "knowledge";
}

function setAssistantMode(mode) {
  state.assistantMode = ["auto", "knowledge", "report", "health"].includes(mode) ? mode : "auto";
  for (const button of document.querySelectorAll(".assistant-mode")) {
    const selected = button.dataset.assistantMode === state.assistantMode;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
  const periodField = document.querySelector(".assistant-period-field");
  if (periodField) periodField.hidden = state.assistantMode !== "report";
  const input = $("assistant-page-input");
  if (input) input.placeholder = state.assistantMode === "knowledge"
    ? "Ask about hotel policies, amenities, services, or guest information"
    : state.assistantMode === "report"
      ? "Ask for an operational report or trend"
      : state.assistantMode === "health"
        ? "Describe the system issue you want checked"
        : "Ask about hotel information, operations, or a system issue";
}

function assistantModeLabel(mode) {
  return ({ hotel: "Hotel knowledge", knowledge: "Hotel knowledge", report: "Reports", health: "System checks", operations: "Operations" })[mode] || "Operations";
}

function renderAssistantHistory() {
  const list = $("assistant-history-list");
  if (!list) return;
  const items = state.assistantConversations || [];
  $("assistant-history-count").textContent = String(items.length);
  const clearButton = document.querySelector("[data-assistant-clear]");
  if (clearButton) clearButton.disabled = !state.assistantConversationId;
  list.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "assistant-history-empty";
    empty.textContent = "Your saved conversations will appear here.";
    list.append(empty);
    return;
  }
  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `assistant-history-entry${item.conversation_id === state.assistantConversationId ? " active" : ""}`;
    button.setAttribute("aria-current", item.conversation_id === state.assistantConversationId ? "true" : "false");
    const title = document.createElement("strong");
    title.textContent = item.title || "New conversation";
    const date = document.createElement("small");
    date.textContent = formatDate(item.updated_at);
    const tags = document.createElement("span");
    for (const kind of item.types || []) {
      const tag = document.createElement("i");
      tag.textContent = assistantModeLabel(kind);
      tags.append(tag);
    }
    button.append(title, date, tags);
    button.addEventListener("click", () => loadAssistantConversation(item.conversation_id).catch((error) => showToast(error.message, "error")));
    list.append(button);
  }
}

async function loadAssistantConversations() {
  if (!currentPropertyId() || !can("assistant.use")) return;
  const propertyId = currentPropertyId();
  const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(propertyId)}/assistant/conversations`);
  if (propertyId !== currentPropertyId()) return;
  state.assistantConversations = result.conversations || [];
  renderAssistantHistory();
}

async function loadAssistantConversation(conversationId) {
  const propertyId = currentPropertyId();
  if (!propertyId || !conversationId) return;
  const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(propertyId)}/assistant/conversations/${encodeURIComponent(conversationId)}`);
  if (propertyId !== currentPropertyId()) return;
  state.assistantConversationId = result.conversation_id;
  const container = $("assistant-page-messages");
  container.replaceChildren();
  for (const message of result.messages || []) {
    const article = document.createElement("article");
    article.className = `assistant-message ${message.role === "user" ? "user" : "answer"}`;
    if (message.role === "user") {
      article.textContent = message.content;
    } else {
      const meta = document.createElement("span");
      meta.textContent = assistantModeLabel(message.assistant_type);
      const heading = document.createElement("h3");
      heading.textContent = message.assistant_type === "hotel" ? "Hotel knowledge response"
        : message.assistant_type === "report" ? "Operations report"
          : message.assistant_type === "health" ? "System check"
            : "Operations update";
      const body = document.createElement("div");
      body.className = "assistant-answer-copy";
      appendAssistantFormattedCopy(body, message.content || "");
      article.append(meta, heading, body);
    }
    container.append(article);
  }
  $("assistant-current-title").textContent = state.assistantConversations.find((item) => item.conversation_id === conversationId)?.title || "Saved conversation";
  renderAssistantHistory();
  container.scrollTop = container.scrollHeight;
}

function resetAssistantConversationView() {
  state.assistantConversationId = null;
  $("assistant-current-title").textContent = "New conversation";
  $("assistant-page-input").value = "";
  $("assistant-files").value = "";
  state.hotelAIFiles = [];
  renderHotelAIFiles();
  $("assistant-page-messages").innerHTML = `<div class="assistant-empty assistant-welcome"><span class="assistant-welcome-mark">✦</span><strong>What would you like to know?</strong><p>Ask about verified hotel information, request a period report, or check current system health.</p><div class="assistant-suggestions"><button type="button" data-assistant-suggestion="What are the hotel's check-in and checkout times?" data-assistant-mode="knowledge">Check-in information</button><button type="button" data-assistant-suggestion="Give me an operations report for the last 7 days." data-assistant-mode="report">7-day operations report</button><button type="button" data-assistant-suggestion="Check the system for current issues." data-assistant-mode="health">Check system health</button></div></div>`;
  applyAssistantPermissionVisibility();
  setAssistantMode("auto");
  renderAssistantHistory();
}

function renderAssistantAnswer(container, payload, existingQuestion = null) {
  container.querySelector(".assistant-empty")?.remove();
  const question = existingQuestion || document.createElement("article");
  if (!existingQuestion) {
    question.className = "assistant-message user";
    question.textContent = payload.question;
  }
  const answer = document.createElement("article");
  answer.className = "assistant-message answer";
  state.assistantConversationId = payload.conversation_id || state.assistantConversationId;
  if (payload.question) $("assistant-current-title").textContent = payload.question.replaceAll("\n", " ").trim().slice(0, 96);
  const timeframe = payload.timeframe && payload.timeframe !== "current period" ? ` · ${payload.timeframe}` : "";
  const meta = document.createElement("span");
  meta.textContent = `${assistantLabel(payload.component || "operations assistant")}${timeframe}`;
  answer.appendChild(meta);
  const heading = document.createElement("h3");
  heading.textContent = payload.finding || "Here’s what I found";
  answer.appendChild(heading);
  if (payload.answer) {
    const body = document.createElement("div");
    body.className = "assistant-answer-copy";
    appendAssistantFormattedCopy(body, payload.answer);
    answer.appendChild(body);
  }
  appendAssistantEvidence(answer, payload.evidence_items || []);
  if (payload.likely_cause) {
    const cause = document.createElement("p");
    cause.className = "assistant-cause";
    cause.textContent = `Likely cause: ${payload.likely_cause}`;
    answer.appendChild(cause);
  }
  if (payload.confirmation_required) {
    const note = document.createElement("p");
    note.className = "confirmation-note";
    note.textContent = payload.action_status || "No changes were made.";
    answer.appendChild(note);
  }
  if (payload.configuration_proposal) appendConfigurationProposal(answer, payload.configuration_proposal);
  if ((payload.recommendations || []).length) {
    const title = document.createElement("h4");
    title.textContent = "Suggested next steps";
    answer.appendChild(title);
    const list = document.createElement("ul");
    for (const item of payload.recommendations) {
      const entry = document.createElement("li");
      entry.textContent = item;
      list.appendChild(entry);
    }
    answer.appendChild(list);
  }
  const links = document.createElement("div");
  links.className = "assistant-links";
  for (const item of payload.links || []) {
    const button = document.createElement("button");
    button.className = "secondary";
    button.type = "button";
    button.textContent = item.label;
    button.dataset.assistantPanel = item.panel;
    links.appendChild(button);
  }
  for (const item of payload.downloads || []) {
    if (!item.url || !item.url.startsWith("/") || item.url.startsWith("//")) continue;
    const link = document.createElement("a");
    link.className = "secondary assistant-download";
    link.href = item.url;
    link.textContent = item.label || "Download report";
    links.appendChild(link);
  }
  if (links.childElementCount) answer.appendChild(links);
  if (!existingQuestion) container.appendChild(question);
  container.appendChild(answer);
  for (const button of answer.querySelectorAll("[data-assistant-panel]")) button.addEventListener("click", () => activatePanel(button.dataset.assistantPanel));
  container.scrollTop = container.scrollHeight;
}

function appendConfigurationProposal(answer, proposal) {
  const card = document.createElement("section");
  card.className = "assistant-action-proposal";
  card.dataset.proposalId = proposal.proposal_id;
  const title = document.createElement("h4");
  title.textContent = `Proposed action · ${String(proposal.action || "configuration").replaceAll(".", " ")}`;
  const scope = document.createElement("p");
  scope.className = "assistant-action-scope";
  const target = proposal.scope?.restaurant_name
    ? `${proposal.scope.restaurant_name} · ${proposal.scope.property_name || proposal.scope.property_id || "Property"}`
    : `${proposal.scope?.property_name || proposal.scope?.property_id || "Selected property"}`;
  scope.textContent = `Target: ${target}`;
  const values = document.createElement("div");
  values.className = "assistant-action-values";
  for (const [label, value] of [["Current value", proposal.current], ["Proposed value", proposal.proposed]]) {
    const block = document.createElement("div");
    const heading = document.createElement("strong");
    heading.textContent = label;
    const pre = document.createElement("pre");
    pre.textContent = value === null || value === undefined ? "Not set" : JSON.stringify(value, null, 2);
    block.append(heading, pre);
    values.append(block);
  }
  const impact = document.createElement("p");
  impact.className = "assistant-action-impact";
  impact.textContent = proposal.impact || "Review this configuration change before applying it.";
  const meta = document.createElement("p");
  meta.className = "assistant-action-meta";
  meta.textContent = `Permission: ${proposal.permission_used || "—"} · Risk: ${proposal.risk_level || "LOW"}`;
  const buttons = document.createElement("div");
  buttons.className = "assistant-action-buttons";
  const apply = document.createElement("button");
  apply.type = "button";
  apply.textContent = proposal.action === "design.publish" || proposal.action === "menu.publish" || proposal.action === "promotion.publish"
    ? "Publish"
    : proposal.action === "menu.approve_and_publish" || proposal.action === "promotion.approve_and_publish"
      ? "Approve & Publish"
      : proposal.action === "menu.approve" || proposal.action === "promotion.approve"
      ? "Approve"
      : proposal.action === "restaurant.update_hours"
        ? "Apply Hours"
        : proposal.action?.includes("create_draft") || proposal.action === "menu.import_draft" || proposal.action === "design.create_draft"
          ? "Save Draft"
          : "Apply Configuration";
  apply.addEventListener("click", async () => {
    let confirmationPhrase = null;
    if (proposal.confirmation_requirement === "strong") {
      confirmationPhrase = window.prompt(`This is a ${proposal.risk_level} risk change. Review the impact above, then type ${proposal.confirmation_phrase} to continue.`);
      if (confirmationPhrase === null) return;
    }
    apply.disabled = true;
    try {
      const result = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/assistant/actions/${encodeURIComponent(proposal.proposal_id)}/confirm`, {
        method: "POST",
        body: JSON.stringify({ confirmation_phrase }),
      });
      const status = document.createElement("p");
      status.className = "assistant-action-complete";
      const workflow = result.result?.workflow_status ? ` Status: ${String(result.result.workflow_status).replaceAll("_", " ")}.` : "";
      status.textContent = `Confirmed and completed.${workflow}`;
      card.append(status);
      buttons.remove();
      const reviewPanel = proposal.open_panel || "overview";
      if (proposal.action?.includes("create_draft") || proposal.action === "menu.import_draft" || proposal.action === "design.create_draft" || proposal.action === "faq.create" || proposal.action === "knowledge.create_draft") {
        card.append(makeActionButton("Review Draft", () => activatePanel(reviewPanel), true));
      }
      if (result.next_proposal) appendConfigurationProposal(answer, result.next_proposal);
      showToast("Configuration change applied.");
    } catch (error) {
      apply.disabled = false;
      showToast(error.message || "The proposal could not be applied.", "error");
    }
  });
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "secondary";
  cancel.textContent = "Cancel";
  cancel.addEventListener("click", async () => {
    cancel.disabled = true;
    try {
      await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/assistant/actions/${encodeURIComponent(proposal.proposal_id)}`, { method: "DELETE" });
      card.classList.add("is-cancelled");
      const status = document.createElement("p");
      status.className = "assistant-action-complete";
      status.textContent = "Proposal cancelled. No changes were made.";
      card.append(status);
      buttons.remove();
    } catch (error) {
      cancel.disabled = false;
      showToast(error.message || "The proposal could not be cancelled.", "error");
    }
  });
  const openSettings = document.createElement("button");
  openSettings.type = "button";
  openSettings.className = "secondary";
  openSettings.textContent = "Open Settings";
  openSettings.addEventListener("click", () => activatePanel(proposal.open_panel || "overview"));
  buttons.append(apply, cancel, openSettings);
  card.append(title, scope, values, impact, meta, buttons);
  answer.append(card);
}

function renderKnowledgeAssistantAnswer(container, payload, uploadedCount = 0) {
  state.assistantConversationId = payload.conversation_id || state.assistantConversationId;
  if (payload.question) $("assistant-current-title").textContent = payload.question.replaceAll("\n", " ").trim().slice(0, 96);
  const answer = document.createElement("article");
  answer.className = "assistant-message answer";
  const meta = document.createElement("span");
  meta.textContent = "Hotel knowledge";
  const heading = document.createElement("h3");
  heading.textContent = "Property knowledge response";
  const body = document.createElement("div");
  body.className = "assistant-answer-copy";
  appendAssistantFormattedCopy(body, payload.answer || "I couldn't find an answer in the available hotel information.");
  answer.append(meta, heading, body);
  if ((payload.sources || []).length) {
    appendAssistantEvidence(answer, payload.sources.map((source) => ({
      label: source.title || source.source || "Hotel knowledge source",
      state: source.status,
      detail: [source.source, ...Object.entries(source.location || {}).map(([key, value]) => `${key} ${value}`)].filter(Boolean).join(" · "),
    })));
    for (const source of payload.sources) {
      if (!source.source_id || !can("knowledge.edit")) continue;
      const link = document.createElement("a");
      link.className = "secondary assistant-download";
      link.href = `/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge/sources/${encodeURIComponent(source.source_id)}/download`;
      link.textContent = `Open source: ${source.title || source.source || "document"}`;
      answer.append(link);
    }
  }
  if (payload.proposed_draft && can("knowledge.edit")) {
    answer.append(makeActionButton("Save as draft", async () => {
      if (!window.confirm(`Save “${payload.proposed_draft.title}” as an Admin Only draft for review?`)) return;
      await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/knowledge/items`, { method: "POST", body: JSON.stringify(payload.proposed_draft) });
      await loadKnowledge(); activatePanel("knowledge"); showToast("Knowledge draft saved for review.");
    }));
  }
  if (uploadedCount) answer.append(makeActionButton("Review knowledge", () => activatePanel("knowledge"), true));
  container.append(answer);
  container.scrollTop = container.scrollHeight;
}

async function submitUnifiedAssistant(event) {
  event.preventDefault();
  const form = event.currentTarget;
  if (form.dataset.busy === "true") return;
  const input = $("assistant-page-input");
  const question = input.value.trim();
  const files = [...state.hotelAIFiles];
  if (!question && !files.length) return;
  const menuFileRequest = files.length > 0 && /\b(?:menu|breakfast|lunch|dinner|meal period)\b/i.test(question);
  if (menuFileRequest && !can("restaurant.menu.edit")) { showToast("Permission required: restaurant.menu.edit", "error"); return; }
  const mode = menuFileRequest ? "menu" : state.assistantMode === "auto" ? (files.length ? "knowledge" : assistantModeForQuestion(question)) : state.assistantMode;
  if (files.length && mode === "knowledge" && !can("knowledge.edit")) { showToast("Permission required: knowledge.edit", "error"); return; }
  if (files.length && !["knowledge", "menu"].includes(mode)) { showToast("Attached files can be used for a menu draft or hotel knowledge review.", "error"); return; }
  const button = form.querySelector("button[type='submit']");
  const container = $("assistant-page-messages");
  const questionMessage = document.createElement("article");
  questionMessage.className = "assistant-message user";
  questionMessage.textContent = [question || "Please add these documents to the hotel knowledge review queue.", ...files.map((file) => `Attached: ${file.name}`)].join("\n");
  const progress = document.createElement("article");
  progress.className = "assistant-message loading";
  progress.setAttribute("role", "status");
  progress.setAttribute("aria-live", "polite");
  progress.textContent = mode === "knowledge" ? "Checking property knowledge…" : mode === "menu" ? "Reading the menu for a reviewable draft…" : "Checking property evidence and available diagnostics…";
  container.querySelector(".assistant-empty")?.remove();
  container.append(questionMessage, progress);
  container.scrollTop = container.scrollHeight;
  form.dataset.busy = "true";
  button.disabled = true;
  button.textContent = files.length ? "Uploading…" : "Thinking…";
  state.hotelAISubmitting = true;
  const controller = new AbortController();
  const progressTimer = window.setTimeout(() => {
    progress.textContent = "This is taking longer than usual. I’m still checking the available evidence…";
  }, 8000);
  const timeout = window.setTimeout(() => controller.abort(), 30000);
  try {
    let payload;
    if (mode === "menu") {
      const encodedFiles = [];
      for (const file of files) {
        progress.textContent = `Reading ${file.name}…`;
        const bytes = new Uint8Array(await file.arrayBuffer());
        let binary = "";
        for (let offset = 0; offset < bytes.length; offset += 8192) binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
        encodedFiles.push({ filename: file.name, content_type: file.type || "application/octet-stream", content_base64: btoa(binary) });
      }
      payload = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/assistant/menu-import`, {
        method: "POST",
        body: JSON.stringify({ question: question || "Create a menu draft from the attached menu for my assigned restaurant.", conversation_id: state.assistantConversationId, files: encodedFiles }),
        signal: controller.signal,
      });
      state.hotelAIFiles = [];
      renderHotelAIFiles();
      progress.remove();
      renderAssistantAnswer(container, payload, questionMessage);
    } else if (mode === "knowledge") {
      const uploaded = [];
      for (const file of files) {
        progress.textContent = `Uploading ${file.name}…`;
        const source = await uploadKnowledgeDocument(file, (percent) => { progress.textContent = `Uploading ${file.name}… ${percent}%`; });
        uploaded.push(source);
        progress.textContent = `Processing ${file.name}…`;
      }
      state.hotelAIFiles = [];
      renderHotelAIFiles();
      payload = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/assistant/hotel-chat`, {
        method: "POST",
        body: JSON.stringify({ question: question || null, conversation_id: state.assistantConversationId, attached_files: uploaded.map((source) => source.filename || source.title || "Uploaded document") }),
        signal: controller.signal,
      });
      progress.remove();
      renderKnowledgeAssistantAnswer(container, payload, uploaded.length);
      if (uploaded.length) window.setTimeout(() => loadKnowledge().catch(() => {}), 1500);
    } else {
      const period = $("assistant-period").value;
      state.operationsPeriod = period;
      payload = await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/assistant/query`, {
        method: "POST",
        body: JSON.stringify({ question, intent: mode === "knowledge" ? "auto" : mode, period, current_page: state.activeNavId || "overview", conversation_id: state.assistantConversationId }),
        signal: controller.signal,
      });
      progress.remove();
      renderAssistantAnswer(container, payload, questionMessage);
    }
    input.value = "";
    await loadAssistantConversations();
  } catch (error) {
    const answer = document.createElement("article");
    answer.className = "assistant-message answer assistant-message-error";
    const heading = document.createElement("h3");
    const timedOut = error?.name === "AbortError";
    const permissionIssue = /permission|role|access/i.test(error?.message || "");
    heading.textContent = timedOut ? "This check took too long." : permissionIssue ? "This isn't available to your role." : "I couldn't finish this request.";
    const detail = document.createElement("p");
    detail.textContent = timedOut
      ? "Try a narrower question. The request has been stopped."
      : error.message || "Check your connection and try again.";
    answer.append(heading, detail);
    container.append(answer);
    container.scrollTop = container.scrollHeight;
  } finally {
    window.clearTimeout(progressTimer);
    window.clearTimeout(timeout);
    progress.remove();
    form.dataset.busy = "false";
    button.disabled = false;
    button.textContent = "Send";
    state.hotelAISubmitting = false;
  }
}

function downloadReport(format, selectedPeriod = null) {
  const period = selectedPeriod || $("reports-period")?.value || state.operationsPeriod || "7d";
  const url = `/api/admin/properties/${encodeURIComponent(currentPropertyId())}/reports/export.${format}?period=${encodeURIComponent(period)}`;
  window.location.assign(url);
}

function normalizeColor(value) {
  return /^#[0-9a-f]{6}$/i.test(value) ? value : "#18181b";
}

function setup() {
  annotateAdminPages();
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
  for (const target of document.querySelectorAll("[data-dashboard-panel]")) {
    target.dataset.bound = "true";
    target.addEventListener("click", () => activatePanel(target.dataset.dashboardPanel));
  }
  for (const trigger of document.querySelectorAll(".ask-ai-trigger")) trigger.addEventListener("click", () => openAssistant());
  $("assistant-page-form").addEventListener("submit", (event) => submitUnifiedAssistant(event).catch((error) => showToast(error.message, "error")));
  for (const button of document.querySelectorAll(".assistant-mode")) {
    button.addEventListener("click", () => setAssistantMode(button.dataset.assistantMode));
  }
  $("assistant-page-messages").addEventListener("click", (event) => {
    const suggestion = event.target.closest("[data-assistant-suggestion]");
    if (!suggestion || suggestion.hidden) return;
    const question = suggestion.dataset.assistantSuggestion || "";
    setAssistantMode(suggestion.dataset.assistantMode || "auto");
    $("assistant-page-input").value = question;
    $("assistant-page-input").focus();
  });
  document.querySelector("[data-assistant-new]").addEventListener("click", () => {
    resetAssistantConversationView();
    $("assistant-page-input").focus();
  });
  document.querySelector("[data-assistant-clear]").addEventListener("click", async () => {
    if (!state.assistantConversationId || !window.confirm("Permanently delete this conversation from your personal history?")) return;
    try {
      await jsonFetch(`/api/admin/properties/${encodeURIComponent(currentPropertyId())}/assistant/conversation`, {
        method: "DELETE", body: JSON.stringify({ conversation_id: state.assistantConversationId }),
      });
      resetAssistantConversationView();
      await loadAssistantConversations();
      showToast("Conversation deleted from your history.");
    } catch (error) { showToast(error.message, "error"); }
  });
  $("assistant-attach").addEventListener("click", () => $("assistant-files").click());
  $("assistant-files").addEventListener("change", (event) => { addHotelAIFiles(event.target.files || []); event.target.value = ""; });
  $("assistant-page-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      event.currentTarget.form.requestSubmit();
    }
  });
  const assistantComposer = $("assistant-page-form");
  assistantComposer.addEventListener("dragover", (event) => { event.preventDefault(); assistantComposer.classList.add("dragover"); });
  assistantComposer.addEventListener("dragleave", (event) => {
    if (!assistantComposer.contains(event.relatedTarget)) assistantComposer.classList.remove("dragover");
  });
  assistantComposer.addEventListener("drop", (event) => {
    event.preventDefault(); assistantComposer.classList.remove("dragover");
    if (can("knowledge.edit") || can("restaurant.menu.edit")) addHotelAIFiles(event.dataTransfer?.files || []);
    else showToast("Permission required: knowledge.edit or restaurant.menu.edit", "error");
  });
  $("assistant-page-input").addEventListener("paste", (event) => {
    const files = [...(event.clipboardData?.files || [])];
    if (files.length) {
      event.preventDefault();
      if (can("knowledge.edit") || can("restaurant.menu.edit")) addHotelAIFiles(files);
      else showToast("Permission required: knowledge.edit or restaurant.menu.edit", "error");
    }
  });
  setAssistantMode("auto");
  for (const select of document.querySelectorAll(".operations-period")) select.addEventListener("change", async (event) => {
    state.operationsPeriod = event.target.value;
    for (const candidate of document.querySelectorAll(".operations-period")) candidate.value = state.operationsPeriod;
    try { await loadDashboard(); } catch (error) { showToast(error.message, "error"); }
  });
  for (const button of document.querySelectorAll("#refresh-dashboard, #refresh-health, #refresh-alerts")) button.addEventListener("click", async () => {
    const labels = { "refresh-dashboard": "Refresh data", "refresh-health": "Refresh checks", "refresh-alerts": "Refresh alerts" };
    const label = labels[button.id];
    button.disabled = true;
    button.textContent = "Refreshing…";
    try {
      await loadDashboard();
      showToast(button.id === "refresh-health" ? "System checks refreshed." : button.id === "refresh-alerts" ? "Alerts refreshed." : "Dashboard data refreshed.");
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = label;
    }
  });
  $("manager-period").addEventListener("change", (event) => {
    const custom = event.target.value === "custom";
    for (const field of document.querySelectorAll(".custom-date")) field.hidden = !custom;
  });
  $("apply-manager-period").addEventListener("click", async () => {
    const period = $("manager-period").value;
    if (period === "custom") {
      const start = $("manager-start").value;
      const end = $("manager-end").value;
      if (!start || !end) return showToast("Choose a custom start and end date.", "error");
      if (end < start) return showToast("The end date must be on or after the start date.", "error");
      state.operationsStart = Math.floor(new Date(`${start}T00:00:00`).getTime() / 1000);
      state.operationsEnd = Math.floor(new Date(`${end}T23:59:59`).getTime() / 1000);
    } else {
      state.operationsStart = null;
      state.operationsEnd = null;
    }
    state.operationsPeriod = period;
    try { await loadDashboard(); } catch (error) { showToast(error.message, "error"); }
  });
  for (const button of document.querySelectorAll("[data-export]")) button.addEventListener("click", () => downloadReport(button.dataset.export, button.closest(".panel")?.querySelector("[data-export-period]")?.value));
  for (const button of document.querySelectorAll("[data-integration-navigation]")) button.addEventListener("click", () => {
    const item = allNavItems().find((candidate) => candidate.id === button.dataset.integrationNavigation);
    if (item) activatePanel(item.panel, item.id);
  });
  $("property-switcher").addEventListener("change", (event) => switchProperty(event.target.value).catch((error) => showToast(error.message, "error")));
  $("brand-logo-trigger").addEventListener("click", () => $("admin-brand-logo-input").click());
  $("admin-brand-logo-input").addEventListener("change", (event) => uploadAdminPropertyLogo(event.currentTarget));
  $("brand-logo-remove").addEventListener("click", async () => {
    if (!state.property?.logo_url || !window.confirm("Remove this property's logo?")) return;
    try { await saveAdminPropertyLogo(""); } catch (error) { showToast(error.message, "error"); }
  });
  $("onboarding-create-property").addEventListener("click", openPropertyCreation);
  $("property-create-form").addEventListener("submit", createProperty);
  $("property-create-name").addEventListener("input", (event) => {
    if ($("property-create-id").dataset.edited !== "true") $("property-create-id").value = propertyIdFromName(event.target.value);
  });
  $("property-create-id").addEventListener("input", () => { $("property-create-id").dataset.edited = "true"; });
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
  $("admin-property").addEventListener("change", () => loadRestaurantAssignmentOptions(selectedRestaurantAssignments()).catch((error) => showToast(error.message, "error")));
  $("admin-role").addEventListener("change", () => loadRestaurantAssignmentOptions(selectedRestaurantAssignments()).catch((error) => showToast(error.message, "error")));
  $("restaurant-assignment-select-all").addEventListener("click", () => {
    for (const checkbox of document.querySelectorAll("#restaurant-assignment-list input")) checkbox.checked = true;
  });
  $("restaurant-assignment-clear").addEventListener("click", () => {
    for (const checkbox of document.querySelectorAll("#restaurant-assignment-list input")) checkbox.checked = false;
  });
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
      onStatus: (message, status) => {
        $("logo-upload-status").textContent = message;
        $("logo-upload-status").dataset.state = status;
      },
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
  for (const button of document.querySelectorAll("[data-design-inspector]")) {
    button.setAttribute("aria-pressed", String(button.classList.contains("active")));
    button.addEventListener("click", () => setDesignInspector(button.dataset.designInspector));
  }
  for (const button of document.querySelectorAll("[data-design-preset]")) {
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", () => applyDesignPreset(button.dataset.designPreset));
  }
  $("reset-design-template").addEventListener("click", () => {
    if (!state.designDraft) return;
    fillDesignForm(state.designDraft);
    document.querySelectorAll("[data-design-preset]").forEach((button) => {
      button.classList.remove("selected");
      button.setAttribute("aria-pressed", "false");
    });
    updatePreview();
    showToast("Unsaved editor changes reset to the saved draft.");
  });
  $("design-save-shortcut").addEventListener("click", () => saveDraft().catch((error) => showToast(error.message, "error")));
  $("design-discard-shortcut").addEventListener("click", () => discardDesign().catch((error) => showToast(error.message, "error")));
  $("design-publish-shortcut").addEventListener("click", () => publishDesign().catch((error) => showToast(error.message, "error")));
  $("save-draft").addEventListener("click", () => saveDraft().catch((error) => showToast(error.message, "error")));
  $("save-auth-types").addEventListener("click", () => saveAuthenticationTypes().catch((error) => showToast(error.message, "error")));
  $("publish-design").addEventListener("click", () => publishDesign().catch((error) => showToast(error.message, "error")));
  $("discard-design").addEventListener("click", () => discardDesign().catch((error) => showToast(error.message, "error")));
  $("ai-default-provider").addEventListener("change", handleDefaultProviderChange);
  $("ai-local-only").addEventListener("change", handleLocalOnlyChange);
  $("save-ai-settings").addEventListener("click", () => saveAISettings().catch((error) => showToast(error.message, "error")));
  $("save-personalization-policy").addEventListener("click", () => savePersonalizationPolicy().catch((error) => showToast(error.message, "error")));
  $("personalization-retention").addEventListener("change", () => {
    const daysInput = $("personalization-retention-days");
    const configurable = $("personalization-retention").value === "configurable";
    if (configurable) {
      daysInput.disabled = false;
      daysInput.value = daysInput.dataset.configurableValue || daysInput.value || "2";
    } else {
      if (!daysInput.disabled) daysInput.dataset.configurableValue = daysInput.value;
      daysInput.value = "2";
      daysInput.disabled = true;
    }
  });
  $("personalization-retention-days").addEventListener("input", (event) => {
    if (!event.currentTarget.disabled) event.currentTarget.dataset.configurableValue = event.currentTarget.value;
  });
  $("personalization-profile").addEventListener("change", () => {
    const option = $("personalization-default-level").querySelector('option[value="personal"]');
    option.disabled = !$("personalization-profile").checked;
    if (option.disabled && $("personalization-default-level").value === "personal") $("personalization-default-level").value = "stay";
  });
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
    button.addEventListener("click", () => updateMapTool(button.dataset.mapTool, button));
  }
  $("floor-map-canvas").addEventListener("pointerdown", handleCanvasPointer);
  $("floor-map-canvas").addEventListener("pointermove", handleCanvasPointerMove);
  $("floor-map-canvas").addEventListener("pointerup", finishMapPointer);
  $("floor-map-canvas").addEventListener("pointercancel", finishMapPointer);
  $("map-object-form").addEventListener("submit", (event) => saveMapObject(event).catch((error) => showToast(error.message, "error")));
  $("map-object-type").addEventListener("change", syncMapObjectType);
  $("map-object-name").addEventListener("input", () => {
    if (state.selectedMapObject) {
      state.mapDirty = true;
      state.selectedMapObject.name = $("map-object-name").value;
      if (state.selectedMapObject.objectType === "navigation_node") state.selectedMapObject.label = state.selectedMapObject.name;
      renderMapCanvas();
    }
  });
  $("map-node-type").addEventListener("change", () => { if (state.selectedMapObject) { state.mapDirty = true; state.selectedMapObject.node_type = $("map-node-type").value; } });
  $("map-object-visible").addEventListener("change", () => { if (state.selectedMapObject) { state.mapDirty = true; state.selectedMapObject.guest_visible = $("map-object-visible").checked; } });
  for (const id of ["map-linked-zone", "map-ap-identifier", "map-facility-type", "map-facility-description", "map-edge-distance", "map-edge-bidirectional"]) $(id).addEventListener("change", () => { if (state.selectedMapObject) state.mapDirty = true; });
  $("map-object-type").addEventListener("change", () => { if (state.selectedMapObject) state.mapDirty = true; });
  $("delete-map-object").addEventListener("click", () => deleteMapObject().catch((error) => showToast(error.message, "error")));
  $("duplicate-map-object").addEventListener("click", duplicateMapObject);
  $("undo-map").addEventListener("click", undoMap);
  $("redo-map").addEventListener("click", redoMap);
  $("finish-map-draw").addEventListener("click", finishMapPolygon);
  $("add-map-building").addEventListener("click", () => createMapStructure("building"));
  $("add-map-floor").addEventListener("click", () => createMapStructure("floor"));
  $("map-empty-add-building").addEventListener("click", () => createMapStructure(state.zones?.buildings.length ? "floor" : "building"));
  $("map-empty-start-drawing").addEventListener("click", () => {
    const button = document.querySelector('[data-map-tool="rectangle"]');
    updateMapTool("rectangle", button);
    button?.focus();
  });
  $("upload-floor-plan-trigger").addEventListener("click", () => $("floor-map-upload").click());
  $("map-empty-upload").addEventListener("click", () => $("floor-map-upload").click());
  $("map-structure-form").addEventListener("submit", (event) => submitMapStructure(event).catch((error) => showToast(error.message, "error")));
  $("map-zoom-out").addEventListener("click", () => setMapZoom(state.mapZoom - .1));
  $("map-zoom-in").addEventListener("click", () => setMapZoom(state.mapZoom + .1));
  $("map-fit-canvas").addEventListener("click", () => setMapZoom(1));
  $("map-object-search").addEventListener("input", renderZoneTree);
  for (const input of document.querySelectorAll(".layer-toggle")) input.addEventListener("change", renderMapCanvas);
  $("zone-building-select").addEventListener("change", () => {
    if ((state.mapDirty || state.mapObjects.length || state.mapPolygonPoints.length || state.selectedMapObject?.isDraft) && !window.confirm("Discard unsaved map changes before changing buildings?")) {
      $("zone-building-select").value = state.mapSelectedBuildingId; return;
    }
    state.selectedMapObject = null; state.mapObjects = []; state.mapPolygonPoints = []; state.mapDirty = false; state.mapHistory = []; state.mapRedo = [];
    hydrateZoneSelectors(); state.mapSelectedBuildingId = currentMapBuildingId(); state.mapSelectedFloorId = currentMapFloorId();
    renderZoneTree(); renderMapCanvas(); renderMapInspector();
  });
  $("zone-floor-select").addEventListener("change", () => {
    if ((state.mapDirty || state.mapObjects.length || state.mapPolygonPoints.length || state.selectedMapObject?.isDraft) && !window.confirm("Discard unsaved map changes before changing floors?")) {
      $("zone-floor-select").value = state.mapSelectedFloorId; return;
    }
    state.selectedMapObject = null; state.mapObjects = []; state.mapPolygonPoints = []; state.mapDirty = false; state.mapHistory = []; state.mapRedo = []; state.mapSelectedFloorId = currentMapFloorId();
    renderMapContext(); renderZoneTree(); renderMapCanvas(); renderMapInspector();
  });
  $("floor-map-upload").addEventListener("change", (event) => uploadFloorMap(event.target.files?.[0]).catch((error) => showToast(error.message, "error")).finally(() => { event.target.value = ""; }));
  $("create-stay-session").addEventListener("click", () => createStaySession().catch((error) => showToast(error.message, "error")));
  $("save-stay-memory").addEventListener("click", () => saveStayMemory().catch((error) => showToast(error.message, "error")));
  $("memory-stay-id").addEventListener("change", () => updateStayMemoryEditor(state.guestStays.find((stay) => stay.stay_id === $("memory-stay-id").value) || null));
  $("refresh-sessions").addEventListener("click", () => loadSessions().catch((error) => showToast(error.message, "error")));
  $("session-record-search").addEventListener("input", renderSessionRecords);
  $("session-record-filter").addEventListener("change", renderSessionRecords);
  for (const card of document.querySelectorAll("[data-session-filter]")) card.addEventListener("click", () => {
    $("session-record-filter").value = card.dataset.sessionFilter;
    renderSessionRecords();
  });
  $("record-observation").addEventListener("click", () => recordObservation().catch((error) => showToast(error.message, "error")));
  $("load-location-report").addEventListener("click", () => loadLocationReport().catch((error) => showToast(error.message, "error")));
  $("create-service-request").addEventListener("click", () => createServiceRequest().catch((error) => showToast(error.message, "error")));
  $("service-type").addEventListener("change", syncRequestService);
  $("service-description").addEventListener("input", updateCreateServiceRequestButton);
  $("service-sla").addEventListener("input", updateCreateServiceRequestButton);
  $("refresh-service-requests").addEventListener("click", () => loadServiceRequests().catch((error) => showToast(error.message, "error")));
  $("service-request-search").addEventListener("input", renderServiceRequests);
  $("service-request-status-filter").addEventListener("change", renderServiceRequests);
  for (const card of document.querySelectorAll("[data-request-filter]")) card.addEventListener("click", () => {
    $("service-request-status-filter").value = card.dataset.requestFilter === "all" ? "" : card.dataset.requestFilter;
    renderServiceRequests();
  });
  $("open-service-catalog").addEventListener("click", () => activatePanel("service-catalog"));
  $("save-department").addEventListener("click", () => saveDepartment().catch((error) => showToast(error.message, "error")));
  $("save-catalog-service").addEventListener("click", () => saveCatalogService().catch((error) => showToast(error.message, "error")));
  $("save-recommendation").addEventListener("click", () => saveRecommendation().catch((error) => showToast(error.message, "error")));
  $("refresh-conversations").addEventListener("click", () => loadConversations().catch((error) => showToast(error.message, "error")));
  $("save-conversation-retention").addEventListener("click", () => saveConversationRetention().catch((error) => showToast(error.message, "error")));
  $("conversation-search").addEventListener("input", renderConversations);
  $("conversation-status-filter").addEventListener("change", renderConversations);
  for (const card of document.querySelectorAll("[data-conversation-filter]")) card.addEventListener("click", () => {
    $("conversation-status-filter").value = card.dataset.conversationFilter;
    renderConversations();
  });
  $("conversation-staff-select").addEventListener("change", () => {
    const selected = state.selectedConversation;
    $("assign-conversation").disabled = !can("conversations.assign") || !selected?.restaurant_id || !$("conversation-staff-select").value || $("conversation-staff-select").value === selected.assigned_user_id;
  });
  $("staff-response").addEventListener("input", () => {
    $("send-staff-response").disabled = $("staff-response").disabled || !$("staff-response").value.trim();
  });
  $("staff-response").addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && !$("send-staff-response").disabled) {
      event.preventDefault();
      sendStaffResponse().catch((error) => showToast(error.message, "error"));
    }
  });
  $("assign-conversation").addEventListener("click", () => assignSelectedConversation().catch((error) => showToast(error.message, "error")));
  $("toggle-takeover").addEventListener("click", () => setConversationState("open", !state.selectedConversation?.human_takeover).catch((error) => showToast(error.message, "error")));
  $("close-conversation").addEventListener("click", () => setConversationState("closed", false).catch((error) => showToast(error.message, "error")));
  $("send-staff-response").addEventListener("click", () => sendStaffResponse().catch((error) => showToast(error.message, "error")));
  for (const id of ["intro-mode", "intro-preset", "intro-message", "intro-background", "intro-brand-color", "intro-first-visit", "intro-skip"]) {
    $(id).addEventListener("input", markIntroDirty);
    $(id).addEventListener("change", markIntroDirty);
  }
  $("intro-duration").addEventListener("input", () => {
    const milliseconds = Math.max(300, Math.min(8000, Math.round(Number($("intro-duration").value || 1.4) * 1000)));
    $("intro-duration-range").value = milliseconds;
    markIntroDirty();
  });
  $("intro-duration-range").addEventListener("input", () => {
    $("intro-duration").value = (Number($("intro-duration-range").value) / 1000).toFixed(1);
    markIntroDirty();
  });
  for (const button of document.querySelectorAll("[data-intro-template]")) {
    button.addEventListener("click", () => {
      const template = INTRO_TEMPLATES[button.dataset.introTemplate];
      if (!template) return;
      $("intro-mode").value = template.mode;
      $("intro-preset").value = template.preset;
      $("intro-duration").value = (template.duration_ms / 1000).toFixed(1);
      $("intro-duration-range").value = template.duration_ms;
      $("intro-message").value = template.welcome_message;
      $("intro-background").value = template.background;
      $("intro-brand-color").value = template.brand_color;
      markIntroDirty();
    });
  }
  for (const button of document.querySelectorAll("[data-intro-preset]")) {
    button.addEventListener("click", () => {
      $("intro-preset").value = button.dataset.introPreset;
      markIntroDirty();
    });
  }
  for (const button of document.querySelectorAll("[data-intro-device]")) {
    button.addEventListener("click", () => setIntroDevice(button.dataset.introDevice));
  }
  $("play-intro-preview").addEventListener("click", () => playIntroPreview().catch((error) => showToast(error.message, "error")));
  $("intro-preview-skip").addEventListener("click", () => stopIntroPreview("Preview skipped."));
  $("reload-intro").addEventListener("click", () => {
    stopIntroPreview("");
    loadIntro().then(() => showToast("Unsaved intro edits reset.")).catch((error) => showToast(error.message, "error"));
  });
  $("save-intro").addEventListener("click", () => saveIntro().catch((error) => showToast(error.message, "error")));
  $("intro-upload").addEventListener("change", (event) => uploadIntroAsset(event.target.files?.[0]).catch((error) => showToast(error.message, "error")));
  $("intro-remove-asset").addEventListener("click", () => removeIntroAsset().catch((error) => showToast(error.message, "error")));
  setIntroDevice("mobile");
  $("save-hotel-information").addEventListener("click", () => saveHotelInformation().catch((error) => showToast(error.message, "error")));
  for (const [inputId, noteId] of [["hotel-info-checkin", "hotel-info-checkin-note"], ["hotel-info-checkout", "hotel-info-checkout-note"]]) {
    $(inputId).addEventListener("input", () => {
      if (!$(inputId).value) return;
      delete $(inputId).dataset.legacyValue;
      $(noteId).hidden = true;
    });
  }
  $("clear-hotel-information").addEventListener("click", () => {
    for (const id of ["hotel-info-description", "hotel-info-address", "hotel-info-phone", "hotel-info-email", "hotel-info-website", "hotel-info-checkin", "hotel-info-checkout", "hotel-info-breakfast", "hotel-info-wifi", "hotel-info-policies"]) $(id).value = "";
    for (const id of ["hotel-info-checkin", "hotel-info-checkout"]) delete $(id).dataset.legacyValue;
    for (const id of ["hotel-info-checkin-note", "hotel-info-checkout-note"]) $(id).hidden = true;
  });
  $("save-room").addEventListener("click", () => saveRoom().catch((error) => showToast(error.message, "error")));
  $("new-room-type").addEventListener("click", () => { clearRoomFilters(); clearRoomForm({ focus: true, scroll: true }); });
  $("cancel-room-edit").addEventListener("click", () => clearRoomForm({ focus: true, scroll: true }));
  $("room-search").addEventListener("input", renderRooms);
  $("room-status-filter").addEventListener("change", renderRooms);
  $("save-guest-module").addEventListener("click", () => saveGuestModule().catch((error) => showToast(error.message, "error")));
  $("clear-guest-module-form").addEventListener("click", clearGuestModuleForm);
  $("add-facility").addEventListener("click", openNewFacility);
  $("empty-add-facility").addEventListener("click", openNewFacility);
  $("facility-form").addEventListener("submit", (event) => saveFacility(event));
  $("cancel-facility").addEventListener("click", () => $("facility-dialog").close());
  $("facility-search").addEventListener("input", renderFacilities);
  $("add-restaurant").addEventListener("click", openNewRestaurant);
  $("empty-add-restaurant").addEventListener("click", openNewRestaurant);
  $("cancel-restaurant").addEventListener("click", () => $("restaurant-dialog").close());
  $("restaurant-search").addEventListener("input", renderRestaurants);
  $("restaurant-form").addEventListener("submit", (event) => {
    event.preventDefault();
    saveRestaurant().catch((error) => showToast(error.message, "error"));
  });
  $("restaurant-workflow-disclosure").addEventListener("toggle", () => {
    if (!$("restaurant-workflow-disclosure").open) return;
    if ($("restaurant-workflow-select").value) loadRestaurantWorkflows().catch((error) => showToast(error.message, "error"));
    else { state.restaurantMenus = []; state.restaurantPromotions = []; state.restaurantAnalytics = null; renderRestaurantWorkflows(); }
  });
  $("restaurant-workflow-select").addEventListener("change", () => {
    if ($("restaurant-workflow-disclosure").open) loadRestaurantWorkflows().catch((error) => showToast(error.message, "error"));
  });
  $("save-restaurant-menu").addEventListener("click", () => saveRestaurantMenu().catch((error) => showToast(error.message, "error")));
  $("save-restaurant-menu-item").addEventListener("click", () => saveRestaurantMenuItem().catch((error) => showToast(error.message, "error")));
  $("save-restaurant-promotion").addEventListener("click", () => saveRestaurantPromotion().catch((error) => showToast(error.message, "error")));
  $("ai-usage-period").addEventListener("change", () => loadAIUsage().catch((error) => showToast(error.message, "error")));
  $("test-antlabs").addEventListener("click", () => testAntlabs().catch((error) => showToast(error.message, "error")));
  $("save-knowledge").addEventListener("click", () => saveKnowledgeEntry().catch((error) => showToast(error.message, "error")));
  $("save-faq").addEventListener("click", () => saveFAQ().catch((error) => showToast(error.message, "error")));
  $("knowledge-document-upload").addEventListener("change", async (event) => {
    const selected = [...(event.target.files || [])];
    const limit = state.managedKnowledge.limits?.max_files_per_upload || 5;
    if (selected.length > limit) showToast(`Choose up to ${limit} files at a time.`, "error");
    for (const file of selected.slice(0, limit)) {
      try { await uploadKnowledgeDocument(file); } catch (error) { showToast(`${file.name}: ${error.message}`, "error"); }
    }
    event.target.value = "";
  });
  $("managed-knowledge-search")?.addEventListener("input", renderManagedKnowledge);
  $("save-personality").addEventListener("click", () => savePersonality().catch((error) => showToast(error.message, "error")));
  $("save-guardrails").addEventListener("click", () => saveGuardrails().catch((error) => showToast(error.message, "error")));
  $("refresh-guardrail-diagnostics").addEventListener("click", () => loadGuardrailDiagnostics().catch((error) => showToast(error.message, "error")));
  const networkAccessPanel = $("network-access");
  if (networkAccessPanel && !$("network-setup-card")) {
    const card = document.createElement("section");
    card.id = "network-setup-card";
    card.className = "card network-setup-card";
    card.innerHTML = `<div class="network-setup-heading"><div><p class="eyebrow">GUIDED SETUP</p><h2>Guest Wi-Fi access</h2><p>Connect a phone to hotel guest Wi-Fi, open the guest page, then choose Detect connection. Concierge checks the address that reaches the server.</p></div><button class="secondary" id="refresh-network-setup" type="button">Detect connection</button></div><div id="network-setup-status" class="network-setup-status" role="status" aria-live="polite">Refresh diagnostics to check the current connection.</div><div class="network-setup-actions"><label class="check-row network-test-confirm"><input id="confirm-hotel-wifi-test" type="checkbox"> I tested from a device on hotel guest Wi-Fi</label><button class="secondary" id="trust-detected-ip" type="button" hidden>Add detected address (/32)</button></div><p class="field-note">A /32 rule trusts one source IP. If ANTlabs NATs all guests to one shared address, it will match all traffic using that address. Confirm that behavior with your network administrator before saving.</p><p class="field-note">If the detected address is a private VM or WSL address, or differs from the guest device address, configure the network or trusted proxy to pass the real client address. Do not approve a shared server address as a guest subnet.</p><p class="field-note">Changes take effect when you click Save Guest Access. The top-page Publish button is for the guest-page design.</p>`;
    networkAccessPanel.insertBefore(card, $("network-access-overview"));
    if (!can("security.view")) $("refresh-network-setup").hidden = true;
    if (!can("network.manage")) {
      $("confirm-hotel-wifi-test").disabled = true;
      $("trust-detected-ip").hidden = true;
    }
    $("refresh-network-setup").addEventListener("click", () => loadGuardrailDiagnostics().catch((error) => showToast(error.message, "error")));
    $("trust-detected-ip").addEventListener("click", addDetectedAddressRule);
    $("confirm-hotel-wifi-test").addEventListener("change", (event) => {
      const button = $("trust-detected-ip");
      button.hidden = !event.target.checked || !button.dataset.ip;
    });
  }
  $("save-webhook").addEventListener("click", () => saveWebhook().catch((error) => showToast(error.message, "error")));
  $("reset-webhook-form").addEventListener("click", resetWebhookForm);
  $("save-location").addEventListener("click", () => saveManagedLocation().catch((error) => showToast(error.message, "error")));
  $("save-management-access").addEventListener("click", () => saveManagementAccess().catch((error) => showToast(error.message, "error")));
  $("add-management-network").addEventListener("click", addManagementNetwork);
  $("management-network-input").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); addManagementNetwork(); } });
  $("finalize-management-access").addEventListener("click", () => finalizeManagementAccess().catch((error) => showToast(error.message, "error")));
  $("save-guest-access").addEventListener("click", () => saveGuestAccess().catch((error) => showToast(error.message, "error")));
  $("verify-deployment").addEventListener("click", () => verifyDeployment().catch((error) => showToast(error.message, "error")));
  $("save-app-settings").addEventListener("click", () => saveApplicationSettings().catch((error) => showToast(error.message, "error")));
  $("save-smtp").addEventListener("click", () => saveSMTPSettings().catch((error) => showToast(error.message, "error")));
  $("test-smtp").addEventListener("click", () => testSMTP().catch((error) => showToast(error.message, "error")));

  for (const button of document.querySelectorAll(".preview-size")) {
    button.addEventListener("click", () => setPreviewDevice(button.dataset.size));
  }
  for (const button of document.querySelectorAll("[data-preview-zoom]")) {
    button.addEventListener("click", () => {
      if (button.dataset.previewZoom === "fit") fitPreview();
      else updatePreviewZoom(state.designZoom + (button.dataset.previewZoom === "in" ? 0.1 : -0.1));
    });
  }
  setPreviewDevice("mobile");
  setDesignInspector("templates");
}

document.body.dataset.adminReady = "false";
const platformShell = document.querySelector(".platform-shell");
if (platformShell) platformShell.inert = true;
setup();
async function initializeAdmin() {
  populatePropertyTimezones();
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
