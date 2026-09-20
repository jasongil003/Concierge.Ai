const state = {
  property: null,
  designDraft: null,
  designPublished: null,
  versions: [],
  ai: null,
  activeProvider: null,
  providerDirty: false,
  zones: null,
  mapTool: "select",
  mapObjects: [],
  selectedMapObject: null,
  mapHistory: [],
  mapRedo: [],
  intro: null,
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

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
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

function activatePanel(panelId) {
  for (const panel of document.querySelectorAll(".panel")) {
    panel.classList.toggle("active", panel.id === panelId);
  }
  for (const item of document.querySelectorAll(".nav-item")) {
    item.classList.toggle("active", item.dataset.panel === panelId);
  }
  if (panelId === "ai" && currentPropertyId()) {
    loadAI().catch((error) => showToast(error.message, "error"));
  }
  if (panelId === "zones" && currentPropertyId()) loadZones().catch((error) => showToast(error.message, "error"));
  if (panelId === "sessions" && currentPropertyId()) loadSessions().catch((error) => showToast(error.message, "error"));
  if (panelId === "location" && currentPropertyId()) loadLocationLive().catch((error) => showToast(error.message, "error"));
  if (panelId === "intro" && currentPropertyId()) loadIntro().catch((error) => showToast(error.message, "error"));
}

function currentPropertyId() {
  return state.property?.property_id || $("property-id").value;
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
  for (const provider of providers) {
    const row = document.createElement("article");
    row.className = "provider-row";
    row.innerHTML = `
      <div class="provider-name-cell">
        <span class="provider-icon">${providerLabel(provider)}</span>
        <div>
          <h3>${provider.name}</h3>
          <p>${provider.auth_method.replaceAll("_", " ")}</p>
        </div>
      </div>
      <span class="status-pill ${statusClass(provider.status)}">${statusLabel(provider.status)}</span>
      <div class="provider-selected-model">${provider.selected_model || "Not selected"}</div>
      <div class="provider-models" aria-label="${provider.name} models">${renderModelChips(provider)}</div>
      <div class="provider-credential">${provider.credentials?.[0]?.display_hint || (provider.provider_id === "local" ? "No cloud key" : "Not configured")}</div>
      <div class="provider-actions">
        <button type="button" data-action="configure">${provider.unavailable ? "Details" : "Configure"}</button>
        <button type="button" data-action="test">Test</button>
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
  $("drawer-model").value = provider.selected_model || "";
  renderDrawerModelList(provider);
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
  const list = $("drawer-model-list");
  list.innerHTML = "";
  for (const model of modelOptions(provider)) {
    const option = document.createElement("option");
    option.value = model;
    option.label = model;
    list.appendChild(option);
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
  const list = $("drawer-model-list");
  list.innerHTML = "";
  for (const model of result.models || []) {
    const option = document.createElement("option");
    option.value = model.id;
    option.label = model.name || model.id;
    list.appendChild(option);
  }
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
  $("background-image-url-input").value = config.theme?.backgroundImageUrl || "";
  $("background-overlay-input").value = config.theme?.backgroundOverlay ?? 0;
  $("font-input").value = config.typography?.fontFamily || "Geist";
  $("density-input").value = config.theme?.density || "comfortable";
  $("content-width-input").value = config.layout?.contentWidth || 840;
  $("message-width-input").value = config.layout?.messageWidth || 680;
  $("user-style-input").value = config.messages?.userStyle || "bubble";
  $("assistant-style-input").value = config.messages?.assistantStyle || "minimal";
  $("header-enabled-input").checked = config.header?.enabled !== false;
  $("show-logo-input").checked = config.header?.showLogo !== false;
  $("show-name-input").checked = config.header?.showHotelName !== false;
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
    composerBackground: $("surface-input").value,
    buttonColor: $("accent-input").value,
    radius: Number(base.theme?.radius || 14),
    density: $("density-input").value,
    backgroundImageUrl: $("background-image-url-input").value,
    backgroundOverlay: Number($("background-overlay-input").value || 0),
  };
  base.typography = {
    ...(base.typography || {}),
    fontFamily: $("font-input").value,
  };
  base.layout = {
    ...(base.layout || {}),
    contentWidth: Number($("content-width-input").value || 840),
    messageWidth: Number($("message-width-input").value || 680),
  };
  base.header = {
    ...(base.header || {}),
    enabled: $("header-enabled-input").checked,
    showLogo: $("show-logo-input").checked,
    showHotelName: $("show-name-input").checked,
  };
  base.welcome = {
    ...(base.welcome || {}),
    greeting: $("greeting-input").value.trim() || "Good evening.",
    headline: $("welcome-input").value.trim() || "How can I help with your stay?",
  };
  base.composer = {
    ...(base.composer || {}),
    placeholder: $("composer-placeholder-input").value.trim() || "Ask your concierge...",
    background: $("surface-input").value,
  };
  base.messages = {
    ...(base.messages || {}),
    userStyle: $("user-style-input").value,
    assistantStyle: $("assistant-style-input").value,
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
  $("hotel-name-input").value = $("design-hotel-name").value || $("hotel-name-input").value;
  $("concierge-name-input").value = $("design-concierge-name").value || $("concierge-name-input").value;
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
  hydrateProperty(data.properties[0]);
  await loadDesign();
  await loadAI();
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
  ctx.strokeStyle = "#d4d4d8";
  ctx.lineWidth = 1;
  for (let x = 0; x < canvas.width; x += 40) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
  }
  for (let y = 0; y < canvas.height; y += 40) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
  }
  const layers = Object.fromEntries([...document.querySelectorAll(".layer-toggle")].map((input) => [input.dataset.layer, input.checked]));
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
  if (!["rectangle", "ellipse", "polygon"].includes(state.mapTool)) return;
  state.mapHistory.push(structuredClone(state.mapObjects));
  const snap = (value) => Math.round(value / 10) * 10;
  const geometry = state.mapTool === "ellipse"
    ? { type: "ellipse", cx: snap(x), cy: snap(y), rx: 80, ry: 50 }
    : state.mapTool === "polygon"
      ? { type: "polygon", points: [[snap(x), snap(y)], [snap(x + 140), snap(y + 20)], [snap(x + 80), snap(y + 100)]] }
      : { type: "rectangle", x: snap(x), y: snap(y), width: 180, height: 110 };
  state.mapObjects.push({ name: $("map-object-name").value || "Draft", geometry });
  state.mapRedo = [];
  renderMapCanvas();
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
  for (const stay of data.stays) {
    const row = document.createElement("div");
    row.className = "compact-row";
    row.innerHTML = `<strong>${stay.stay_id}</strong><span>${stay.status} · ${stay.device_id} · room ${stay.room || "none"}</span>`;
    row.addEventListener("click", () => {
      $("memory-stay-id").value = stay.stay_id;
      $("memory-summary").value = stay.memory_summary?.conversation_summary || "";
    });
    list.appendChild(row);
  }
  if (!data.stays.length) list.textContent = "No stay sessions yet.";
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

function normalizeColor(value) {
  return /^#[0-9a-f]{6}$/i.test(value) ? value : "#18181b";
}

function setup() {
  for (const item of document.querySelectorAll(".nav-item")) {
    item.addEventListener("click", () => activatePanel(item.dataset.panel));
  }

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
    "background-overlay-input",
    "font-input",
    "density-input",
    "content-width-input",
    "message-width-input",
    "user-style-input",
    "assistant-style-input",
    "header-enabled-input",
    "show-logo-input",
    "show-name-input",
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

  for (const button of document.querySelectorAll("[data-map-tool]")) {
    button.addEventListener("click", () => {
      state.mapTool = button.dataset.mapTool;
      for (const candidate of document.querySelectorAll("[data-map-tool]")) candidate.classList.toggle("active", candidate === button);
    });
  }
  $("floor-map-canvas").addEventListener("pointerdown", handleCanvasPointer);
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
  for (const id of ["intro-mode", "intro-preset", "intro-duration", "intro-message", "intro-background", "intro-brand-color", "intro-first-visit", "intro-skip"]) {
    $(id).addEventListener("input", updateIntroPreview);
    $(id).addEventListener("change", updateIntroPreview);
  }
  $("save-intro").addEventListener("click", () => saveIntro().catch((error) => showToast(error.message, "error")));
  $("intro-upload").addEventListener("change", (event) => uploadIntroAsset(event.target.files?.[0]).catch((error) => showToast(error.message, "error")));

  for (const button of document.querySelectorAll(".preview-size")) {
    button.addEventListener("click", () => {
      for (const candidate of document.querySelectorAll(".preview-size")) {
        candidate.classList.toggle("active", candidate === button);
      }
      $("chat-preview").className = "phone-preview " + button.dataset.size;
    });
  }
}

setup();
loadProperty().catch((error) => showToast(error.message, "error"));
