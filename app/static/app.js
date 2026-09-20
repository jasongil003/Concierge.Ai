const state = {
  sessionId: null,
  hotel: null,
  clientId: null,
  messages: [],
  authenticated: false,
  room: null,
  draftKey: "concierge-draft",
  mode: "auto",
  intro: null,
};

let startupPromise = null;

const $ = (id) => document.getElementById(id);

const defaultSuggestions = [
  { label: "What time is breakfast?", prompt: "What time is breakfast?" },
  { label: "Connect me to Wi-Fi", prompt: "Connect me to Wi-Fi" },
  { label: "What time does the pool close?", prompt: "What time does the pool close?" },
  { label: "Recommend somewhere nearby to eat", prompt: "Recommend somewhere nearby to eat" },
  { label: "Can I request a late checkout?", prompt: "Can I request a late checkout?" },
];

const recommendationResults = [
  {
    name: "Lusso Bistro",
    meta: "Italian · 350 m · Open until 11 PM",
    detail: "Quiet dining room, good for a relaxed dinner after check-in.",
  },
  {
    name: "Harbor Kitchen",
    meta: "Seafood · 600 m · Open until 10:30 PM",
    detail: "Casual, nearby, and usually easy to get a table.",
  },
  {
    name: "Matsuya Table",
    meta: "Japanese · 900 m · Open until 10 PM",
    detail: "Good option for sushi, rice bowls, and lighter dishes.",
  },
];

function setText(id, value) {
  const element = $(id);
  if (element) element.textContent = value;
}

function showToast(message, tone = "default") {
  const toast = $("toast");
  toast.textContent = message;
  toast.className = "toast show " + tone;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.className = "toast";
  }, 2800);
}

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(errorMessage(data.detail));
  return data;
}

function errorMessage(detail) {
  if (!detail) return "Request failed";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item.msg || item.message || JSON.stringify(item))
      .join(" ");
  }
  return detail.msg || detail.message || JSON.stringify(detail);
}

function gatewayContext() {
  const params = new URLSearchParams(window.location.search);
  return Object.fromEntries(params.entries());
}

function createClientId() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return "client-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
}

function renderWelcomeState() {
  const list = $("suggestion-list");
  list.innerHTML = "";
  for (const item of activeSuggestions()) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = item.label;
    button.addEventListener("click", () => handleGuestInput(item.prompt));
    list.appendChild(button);
  }
}

function activeSuggestions() {
  const configured = state.hotel?.design?.suggestions || [];
  const suggestions = configured
    .filter((item) => item.enabled !== false)
    .sort((a, b) => (a.order || 0) - (b.order || 0))
    .map((item) => ({ label: item.label, prompt: item.prompt }));
  return suggestions.length ? suggestions : defaultSuggestions;
}

function addMessage(message) {
  state.messages.push({
    id: "msg-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2),
    ...message,
  });
  renderMessages();
}

function renderMessages() {
  $("welcome-state").classList.toggle("hidden", state.messages.length > 0);
  const list = $("message-list");
  list.innerHTML = "";
  for (const message of state.messages) {
    list.appendChild(renderMessage(message));
  }
  requestAnimationFrame(() => {
    const region = document.querySelector(".conversation-region");
    const nearBottom = region.scrollHeight - region.scrollTop - region.clientHeight < 160;
    if (nearBottom || state.messages.length <= 2) {
      region.scrollTop = region.scrollHeight;
    }
  });
}

function renderMessage(message) {
  const row = document.createElement("article");
  row.className = "message-row " + message.role + " " + (message.type || "text");

  if (message.role === "assistant") {
    const label = document.createElement("div");
    label.className = "message-label";
    label.textContent = "Concierge";
    row.appendChild(label);
  }

  if (message.type === "authentication") {
    row.appendChild(renderAuthenticationCard(message));
    return row;
  }

  if (message.type === "recommendation") {
    row.appendChild(renderText(message.text));
    row.appendChild(renderRecommendationResults(message.results || []));
    return row;
  }

  if (message.type === "confirmation") {
    row.appendChild(renderText(message.text));
    row.appendChild(renderConfirmationCard(message));
    return row;
  }

  if (message.type === "status" || message.type === "error") {
    const status = document.createElement("div");
    status.className = "status-message";
    status.textContent = message.text;
    row.appendChild(status);
    return row;
  }

  row.appendChild(renderText(message.text));
  return row;
}

function renderText(text) {
  const body = document.createElement("div");
  body.className = "message-text";
  const lines = String(text || "").split("\n");
  for (const [index, line] of lines.entries()) {
    if (index) body.appendChild(document.createElement("br"));
    body.appendChild(document.createTextNode(line));
  }
  return body;
}

function renderAuthenticationCard() {
  const card = document.createElement("form");
  card.className = "inline-card auth-card";
  card.innerHTML = `
    <label>Room number<input name="room" autocomplete="off" inputmode="numeric" placeholder="1503"></label>
    <label>Last name<input name="lastName" autocomplete="family-name" placeholder="Surname"></label>
    <button type="submit">Continue</button>
  `;
  card.addEventListener("submit", async (event) => {
    event.preventDefault();
    const room = card.elements.room.value.trim();
    const lastName = card.elements.lastName.value.trim();
    if (!room || !lastName) {
      showToast("Enter room number and last name.", "warning");
      return;
    }
    card.querySelector("button").disabled = true;
    card.querySelector("button").textContent = "Checking...";
    await authenticateGuest(room, lastName, card);
  });
  return card;
}

function renderRecommendationResults(results) {
  const wrap = document.createElement("div");
  wrap.className = "recommendation-list";
  for (const result of results) {
    const card = document.createElement("article");
    card.className = "recommendation-card";

    const name = document.createElement("strong");
    name.textContent = result.name;

    const meta = document.createElement("span");
    meta.textContent = result.meta;

    const detail = document.createElement("p");
    detail.textContent = result.detail;

    const actions = document.createElement("div");
    const directionsBtn = document.createElement("button");
    directionsBtn.type = "button";
    directionsBtn.textContent = "Directions";
    directionsBtn.addEventListener("click", () => showToast("Directions will connect to maps and booking integrations."));
    const detailsBtn = document.createElement("button");
    detailsBtn.type = "button";
    detailsBtn.textContent = "Details";
    detailsBtn.addEventListener("click", () => showToast("Details will connect to maps and booking integrations."));
    actions.appendChild(directionsBtn);
    actions.appendChild(detailsBtn);

    card.appendChild(name);
    card.appendChild(meta);
    card.appendChild(detail);
    card.appendChild(actions);
    wrap.appendChild(card);
  }
  return wrap;
}

function renderConfirmationCard(message) {
  const card = document.createElement("div");
  card.className = "inline-card confirmation-card";
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = message.actionLabel || "Confirm";
  button.addEventListener("click", () => {
    button.disabled = true;
    button.textContent = "Confirmed";
    addMessage({ role: "assistant", type: "status", text: "Request confirmed. Hotel staff will follow up shortly." });
  });
  card.appendChild(button);
  return card;
}

async function authenticateGuest(room, lastName, card) {
  try {
    await ensureStarted();
    const result = await jsonFetch("/api/authenticate", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        room,
        last_name: lastName,
      }),
    });

    if (result.status === "handoff_required" && result.handoff) {
      submitGatewayHandoff(result.handoff);
      return;
    }

    if (result.status === "authenticated") {
      state.authenticated = true;
      state.room = room;
      state.messages = state.messages.filter((message) => message.type !== "authentication");
      addMessage({ role: "assistant", type: "text", text: "You're connected. You can continue using the internet." });
      return;
    }

    addMessage({ role: "assistant", type: "error", text: result.message || "I could not verify the stay. Please try again." });
  } catch (error) {
    addMessage({ role: "assistant", type: "error", text: error.message });
  } finally {
    if (card.isConnected) {
      card.querySelector("button").disabled = false;
      card.querySelector("button").textContent = "Continue";
    }
  }
}

function submitGatewayHandoff(handoff) {
  const form = document.createElement("form");
  form.method = handoff.method || "POST";
  form.action = handoff.url;

  for (const [name, value] of Object.entries(handoff.fields || {})) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = name;
    input.value = value;
    form.appendChild(input);
  }

  document.body.appendChild(form);
  form.submit();
}

async function handleGuestInput(rawMessage) {
  const message = rawMessage.trim();
  if (!message) return;
  if (!state.sessionId) {
    try {
      await ensureStarted();
    } catch (error) {
      addMessage({ role: "assistant", type: "error", text: "Unable to start the concierge: " + error.message });
      return;
    }
  }
  addMessage({ role: "user", type: "text", text: message });
  setDraft("");

  if (isWifiRequest(message)) {
    handleWifiRequest();
    return;
  }

  if (isServiceRequest(message)) {
    addMessage({
      role: "assistant",
      type: "confirmation",
      text: "I can send that request to housekeeping. Please confirm before I create it.",
      actionLabel: "Confirm request",
    });
    return;
  }

  if (isRestaurantRequest(message)) {
    addMessage({
      role: "assistant",
      type: "recommendation",
      text: "Here are a few nearby options that should work well. I can narrow these by cuisine, budget, or walking distance.",
      results: recommendationResults,
    });
    return;
  }

  await sendChat(message);
}

async function sendChat(message) {
  addMessage({ role: "assistant", type: "status", text: "Thinking..." });
  const thinking = state.messages[state.messages.length - 1];
  try {
    const result = await jsonFetch("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        message,
        mode: state.mode,
      }),
    });
    thinking.type = "text";
    thinking.text = result.answer;
    renderMessages();
  } catch (error) {
    thinking.type = "error";
    thinking.text = error.message;
    renderMessages();
  }
}

function isWifiRequest(message) {
  const normalized = message.toLowerCase();
  return normalized.includes("wi-fi") || normalized.includes("wifi") || normalized.includes("internet") || normalized.includes("connect me");
}

function enabledAuthenticationTypes() {
  return state.hotel?.authentication?.enabled_types || [];
}

function handleWifiRequest() {
  const enabled = enabledAuthenticationTypes();
  if (!enabled.length) {
    addMessage({
      role: "assistant",
      type: "text",
      text: "Wi-Fi authentication is not enabled for this hotel in the admin settings yet. Please contact the front desk for access.",
    });
    return;
  }
  const names = enabled.map((item) => item.label).join(", ");
  addMessage({ role: "assistant", type: "text", text: `This hotel currently supports: ${names}.` });
  if (enabled.some((item) => item.id === "pms")) {
    addMessage({ role: "assistant", type: "text", text: "Please verify your stay with your room number and last name." });
    addMessage({ role: "assistant", type: "authentication" });
    return;
  }
  addMessage({
    role: "assistant",
    type: "text",
    text: "Please use one of the enabled login methods shown on the hotel Wi-Fi portal. I can explain the available options, but this prototype only submits PMS room login from chat.",
  });
}

function isRestaurantRequest(message) {
  const normalized = message.toLowerCase();
  return ["restaurant", "dining", "eat", "food", "nearby", "japanese"].some((word) => normalized.includes(word));
}

function isServiceRequest(message) {
  const normalized = message.toLowerCase();
  return ["towel", "towels", "housekeeping", "room service", "maintenance", "send"].some((word) => normalized.includes(word));
}

function setDraft(value) {
  $("composer-input").value = value;
  localStorage.setItem(state.draftKey, value);
  updateComposerState();
}

function updateComposerState() {
  const input = $("composer-input");
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 148) + "px";
  $("send-button").disabled = !input.value.trim();
}

function setupComposer() {
  const input = $("composer-input");
  const savedDraft = localStorage.getItem(state.draftKey);
  if (savedDraft) input.value = savedDraft;
  updateComposerState();

  input.addEventListener("input", () => {
    localStorage.setItem(state.draftKey, input.value);
    updateComposerState();
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      $("composer-form").requestSubmit();
    }
  });

  $("composer-form").addEventListener("submit", (event) => {
    event.preventDefault();
    handleGuestInput(input.value);
  });

  $("plus-button").addEventListener("click", () => {
    showToast("Photo upload and location sharing are disabled for this POC.", "warning");
  });
}

function setupMenu() {
  $("menu-button").addEventListener("click", () => {
    $("hotel-menu").classList.add("open");
    $("hotel-menu").setAttribute("aria-hidden", "false");
  });
  $("options-button").addEventListener("click", () => {
    $("hotel-menu").classList.add("open");
    $("hotel-menu").setAttribute("aria-hidden", "false");
  });
  $("close-menu-button").addEventListener("click", closeMenu);
  $("hotel-menu").addEventListener("click", (event) => {
    if (event.target === $("hotel-menu")) closeMenu();
  });
  for (const button of document.querySelectorAll("[data-menu-action]")) {
    button.addEventListener("click", () => handleMenuAction(button.dataset.menuAction));
  }
}

function closeMenu() {
  $("hotel-menu").classList.remove("open");
  $("hotel-menu").setAttribute("aria-hidden", "true");
}

function handleMenuAction(action) {
  closeMenu();
  if (action === "new-chat") {
    state.messages = [];
    renderMessages();
    showToast("Started a new conversation.");
    return;
  }
  const labels = {
    "hotel-info": "Hotel information",
    language: "Language preferences",
    accessibility: "Accessibility controls",
    privacy: "Privacy information",
    help: "Help",
  };
  showToast((labels[action] || "Menu item") + " will open in the next POC pass.");
}

function applyHotelProfile(profile) {
  state.hotel = profile;
  const design = profile.design || {};
  const branding = design.branding || {};
  const welcome = design.welcome || {};
  const composer = design.composer || {};
  const hotelName = profile.name || "Concierge";
  const conciergeName = profile.concierge_name || "AI concierge";
  setText("hotel-name", branding.hotelName || hotelName);
  setText("concierge-name", branding.conciergeName || conciergeName);
  setText("hotel-mark", hotelName.slice(0, 1).toUpperCase());
  $("hotel-mark").style.backgroundImage = branding.logoUrl ? `url("${branding.logoUrl}")` : "";
  $("hotel-mark").classList.toggle("has-image", Boolean(branding.logoUrl));
  setText("welcome-greeting", welcome.greeting || "Good evening.");
  setText("welcome-headline", welcome.headline || "How can I help with your stay?");
  $("composer-input").placeholder = composer.placeholder || "Ask your concierge...";
  applyDesignTokens(design);
  renderWelcomeState();
}

async function maybeShowIntro() {
  try {
    const intro = await jsonFetch("/api/guest/intro");
    state.intro = intro;
    if (!intro || intro.mode === "none") return;
    if (intro.first_visit_only && localStorage.getItem("concierge-intro-seen") === "1") return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const overlay = $("intro-overlay");
    const stage = $("intro-stage");
    overlay.dataset.preset = reducedMotion ? "none" : intro.preset;
    overlay.style.background = intro.background || "#fbfbfa";
    overlay.style.color = intro.brand_color || "#18181b";
    $("intro-logo").style.background = intro.brand_color || "#18181b";
    $("intro-logo").textContent = (state.hotel?.name || "Concierge").slice(0, 1).toUpperCase();
    $("intro-message").textContent = intro.welcome_message || state.hotel?.welcome || "Welcome";
    $("intro-skip").hidden = !intro.allow_skip;
    overlay.hidden = false;
    const finish = () => {
      overlay.hidden = true;
      localStorage.setItem("concierge-intro-seen", "1");
    };
    $("intro-skip").onclick = finish;
    window.setTimeout(finish, reducedMotion ? 450 : intro.duration_ms || 1400);
    stage.addEventListener("animationend", () => {}, { once: true });
  } catch {
    $("intro-overlay").hidden = true;
  }
}

function applyDesignTokens(design) {
  const theme = design.theme || {};
  const typography = design.typography || {};
  const layout = design.layout || {};
  const messages = design.messages || {};
  const header = design.header || {};
  const composer = design.composer || {};

  const root = document.documentElement;
  root.style.setProperty("--background", theme.background || "#fbfbfa");
  root.style.setProperty("--background-image", theme.backgroundImageUrl ? `url("${theme.backgroundImageUrl}")` : "none");
  root.style.setProperty("--background-overlay", (theme.backgroundOverlay || 0) / 100);
  root.style.setProperty("--surface", theme.surface || "#ffffff");
  root.style.setProperty("--surface-elevated", composer.background || theme.composerBackground || "#ffffff");
  root.style.setProperty("--text-primary", theme.textPrimary || "#18181b");
  root.style.setProperty("--text-secondary", theme.textSecondary || "#71717a");
  root.style.setProperty("--accent", theme.accent || "#18181b");
  root.style.setProperty("--accent-text", theme.accentText || "#ffffff");
  root.style.setProperty("--border", theme.border || "#e4e4e7");
  root.style.setProperty("--user-message-bg", theme.userMessageBackground || "#eeeeee");
  root.style.setProperty("--user-message-text", theme.userMessageText || "#18181b");
  root.style.setProperty("--assistant-text", theme.assistantText || theme.textPrimary || "#18181b");
  root.style.setProperty("--column-width", (layout.contentWidth || 840) + "px");
  root.style.setProperty("--composer-max", (layout.composerWidth || 840) + "px");
  root.style.setProperty("--message-width", (layout.messageWidth || 680) + "px");
  root.style.setProperty("--message-spacing", (messages.messageSpacing || layout.messageSpacing || 24) + "px");
  root.style.setProperty("--message-radius", (messages.radius || 18) + "px");
  root.style.setProperty("--composer-radius", (composer.radius || 24) + "px");
  root.style.setProperty("--base-font-size", (typography.baseFontSize || 15) + "px");
  root.style.setProperty("--heading-weight", typography.headingWeight || 600);
  root.style.setProperty("--body-weight", typography.bodyWeight || 400);
  root.style.setProperty("--letter-spacing", (typography.letterSpacing || 0) + "em");
  root.style.setProperty("--font-family", fontStack(typography.fontFamily || theme.font || "Geist"));

  document.body.dataset.userMessageStyle = messages.userStyle || "bubble";
  document.body.dataset.assistantMessageStyle = messages.assistantStyle || "minimal";
  document.body.dataset.density = theme.density || "comfortable";
  document.body.dataset.suggestionLayout = layout.suggestionLayout || "stack";
  document.body.classList.toggle("header-hidden", header.enabled === false);
  const logoDisplay = design.branding?.logoDisplay || "mark_name";
  document.body.classList.toggle("hotel-logo-hidden", header.showLogo === false || logoDisplay === "name_only");
  document.body.classList.toggle("hotel-name-hidden", header.showHotelName === false || logoDisplay === "logo_only");
}

function fontStack(font) {
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

async function start() {
  setupComposer();
  setupMenu();
  const profile = await jsonFetch("/api/hotel");
  applyHotelProfile(profile);
  await maybeShowIntro();

  state.clientId = localStorage.getItem("concierge-client-id") || createClientId();
  localStorage.setItem("concierge-client-id", state.clientId);

  const session = await jsonFetch("/api/session/start", {
    method: "POST",
    body: JSON.stringify({
      client_id: state.clientId,
      gateway_context: gatewayContext(),
    }),
  });
  state.sessionId = session.session_id;
}

function ensureStarted() {
  if (!startupPromise) startupPromise = start();
  return startupPromise;
}

ensureStarted().catch((error) => {
  addMessage({ role: "assistant", type: "error", text: "Unable to start the concierge: " + error.message });
});
