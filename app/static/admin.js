const state = {
  property: null,
  designDraft: null,
  designPublished: null,
  versions: [],
  ai: null,
  activeProvider: null,
  providerDirty: false,
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
