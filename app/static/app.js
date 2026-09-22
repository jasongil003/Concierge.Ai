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
  services: [],
  recommendations: [],
  staffMessageIds: new Set(),
  pendingAttachment: null,
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
  for (const [index, item] of activeSuggestions().entries()) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.kind = suggestionKind(item.prompt || item.label, index);

    const icon = document.createElement("span");
    icon.className = "suggestion-icon";
    icon.innerHTML = suggestionIcon(button.dataset.kind);

    const label = document.createElement("span");
    label.className = "suggestion-label";
    label.textContent = item.label;

    const arrow = document.createElement("span");
    arrow.className = "suggestion-arrow";
    arrow.setAttribute("aria-hidden", "true");
    arrow.innerHTML = '<svg viewBox="0 0 20 20"><path d="m7.5 4.5 5 5.5-5 5.5"/></svg>';

    button.append(icon, label, arrow);
    button.addEventListener("click", () => handleGuestInput(item.prompt));
    list.appendChild(button);
  }
}

function suggestionKind(value, index) {
  const prompt = String(value || "").toLowerCase();
  if (prompt.includes("breakfast") || prompt.includes("eat") || prompt.includes("restaurant") || prompt.includes("dining")) return "dining";
  if (prompt.includes("wi-fi") || prompt.includes("wifi") || prompt.includes("internet")) return "wifi";
  if (prompt.includes("pool") || prompt.includes("spa") || prompt.includes("gym")) return "wellness";
  if (prompt.includes("checkout") || prompt.includes("check-out") || prompt.includes("room")) return "stay";
  return ["concierge", "dining", "wellness", "stay"][index % 4];
}

function suggestionIcon(kind) {
  const icons = {
    dining: '<svg viewBox="0 0 24 24"><path d="M7 3v8M4.5 3v5.5A2.5 2.5 0 0 0 7 11v10M9.5 3v5.5A2.5 2.5 0 0 1 7 11M17 3c-2 2.2-2.5 5.8-1.1 8.3.4.7 1.1 1.1 1.9 1.1H19V21"/></svg>',
    wifi: '<svg viewBox="0 0 24 24"><path d="M3.5 8.8a13 13 0 0 1 17 0M6.5 12.2a8.5 8.5 0 0 1 11 0M9.6 15.6a3.8 3.8 0 0 1 4.8 0"/><circle cx="12" cy="19" r="1"/></svg>',
    wellness: '<svg viewBox="0 0 24 24"><path d="M3 15.5c1.5-1.3 3-1.3 4.5 0s3 1.3 4.5 0 3-1.3 4.5 0 3 1.3 4.5 0M3 19c1.5-1.3 3-1.3 4.5 0s3 1.3 4.5 0 3-1.3 4.5 0 3 1.3 4.5 0"/><path d="M5 12h14l-1.2-5H6.2L5 12Z"/></svg>',
    stay: '<svg viewBox="0 0 24 24"><path d="M4 20V7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v13M8 9h3v3H8zM15.5 10.5h.01M8 16h8"/></svg>',
    concierge: '<svg viewBox="0 0 24 24"><path d="M4 18h16M6 18a6 6 0 0 1 12 0M12 8V5M10 5h4"/><path d="M8.5 13.5c1.8-1.4 5.2-1.4 7 0"/></svg>',
  };
  return icons[kind] || icons.concierge;
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
    meta.textContent = [result.category, result.address, result.open_now === true ? "Open now" : result.open_now === false ? "Closed now" : ""].filter(Boolean).join(" · ");

    const detail = document.createElement("p");
    detail.hidden = true;
    detail.textContent = result.description || result.detail || "No additional description supplied.";

    const actions = document.createElement("div");
    const directionsBtn = document.createElement("button");
    directionsBtn.type = "button";
    directionsBtn.textContent = "Directions";
    const mapUrl = result.map_url || result.maps_url;
    directionsBtn.disabled = !mapUrl;
    directionsBtn.addEventListener("click", () => {
      if (mapUrl) window.open(mapUrl, "_blank", "noopener,noreferrer");
    });
    const detailsBtn = document.createElement("button");
    detailsBtn.type = "button";
    detailsBtn.textContent = "Details";
    detailsBtn.addEventListener("click", () => {
      detail.hidden = !detail.hidden;
      detailsBtn.textContent = detail.hidden ? "Details" : "Hide details";
    });
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
  button.disabled = Boolean(message.submitting || message.confirmed);
  button.textContent = message.confirmed ? "Confirmed" : message.submitting ? "Creating..." : message.actionLabel || "Confirm";
  button.addEventListener("click", async () => {
    if (message.submitting || message.confirmed) return;
    message.submitting = true;
    button.disabled = true;
    button.textContent = "Creating...";
    try {
      const result = await jsonFetch("/api/guest/service-requests", {
        method: "POST",
        body: JSON.stringify({ session_id: state.sessionId, service_id: message.service.service_id, description: message.description, room: state.room, client_request_id: message.clientRequestId }),
      });
      message.submitting = false;
      message.confirmed = true;
      message.requestId = result.request.request_id;
      addMessage({ role: "assistant", type: "status", text: `Request ${result.request.request_id} was created. Hotel staff can now track it.` });
    } catch (error) {
      message.submitting = false;
      button.disabled = false;
      button.textContent = message.actionLabel || "Confirm";
      addMessage({ role: "assistant", type: "error", text: error.message });
    }
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

  const matchedService = isInformationRequest(message) ? null : matchService(message);
  if (matchedService) {
    addMessage({
      role: "assistant",
      type: "confirmation",
      text: `Absolutely — I can arrange ${matchedService.name.toLowerCase()} for you. Please confirm and I’ll send it to the hotel team.`,
      actionLabel: "Confirm request",
      service: matchedService,
      description: message,
      clientRequestId: createClientId(),
    });
    return;
  }

  if (isRestaurantRequest(message)) {
    if (state.recommendations.length) {
      addMessage({
        role: "assistant",
        type: "recommendation",
        text: "Here are property-verified recommendations.",
        results: state.recommendations,
      });
      return;
    }
  }

  const messageForAI = state.pendingAttachment ? `${message}\n\n${state.pendingAttachment}` : message;
  state.pendingAttachment = null;
  await sendChat(messageForAI);
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
    thinking.type = result.places?.length ? "recommendation" : "text";
    thinking.text = result.answer;
    thinking.results = (result.places || []).map((place) => ({ ...place, category: "Live Places result", description: place.address }));
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

function matchService(message) {
  const normalized = message.toLowerCase();
  return state.services.find((service) => [service.name, ...(service.keywords || [])].some((word) => normalized.includes(String(word).toLowerCase())));
}

function isInformationRequest(message) {
  const normalized = String(message || "").toLowerCase();
  const asksForFacts = /\b(what|where|when|which|hours?|open|opening|close|closing|located|location)\b/.test(normalized)
    || /\bhow\s+(late|early|long)\b/.test(normalized);
  const asksForAction = /\b(book|reserve|schedule|send|bring|deliver|request|fix|repair|clean|replace)\b/.test(normalized);
  return asksForFacts && !asksForAction;
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

  $("upload-button").addEventListener("click", () => $("upload-input").click());
  $("upload-input").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      await ensureStarted();
      if (file.size > 1_000_000) throw new Error("Guest uploads are limited to 1 MB.");
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = "";
      for (const byte of bytes) binary += String.fromCharCode(byte);
      const result = await jsonFetch("/api/guest/uploads", {
        method: "POST",
        body: JSON.stringify({ session_id: state.sessionId, filename: file.name, content_type: file.type || "text/plain", content_base64: btoa(binary) }),
      });
      addMessage({ role: "user", type: "text", text: `Uploaded ${result.filename}` });
      state.pendingAttachment = result.message_context;
      addMessage({ role: "assistant", type: "text", text: `${result.filename} is ready. Ask me a question about the document.` });
    } catch (error) {
      showToast(error.message, "error");
    }
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
    button.addEventListener("click", () => handleMenuAction(button.dataset.menuAction).catch((error) => showToast(error.message, "warning")));
  }
  $("close-map-button").addEventListener("click", closePropertyMap);
  $("property-map-modal").addEventListener("click", (event) => {
    if (event.target === $("property-map-modal")) closePropertyMap();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("property-map-modal").hidden) closePropertyMap();
  });
}

function closeMenu() {
  $("hotel-menu").classList.remove("open");
  $("hotel-menu").setAttribute("aria-hidden", "true");
}

async function handleMenuAction(action) {
  closeMenu();
  if (action === "new-chat") {
    state.messages = [];
    state.sessionId = null;
    state.staffMessageIds.clear();
    await startGuestSession();
    renderMessages();
    showToast("Started a new conversation.");
    return;
  }
  if (action === "property-map") {
    await openPropertyMap();
  } else if (action === "hotel-info") {
    const location = state.hotel?.location?.address || "Address not configured";
    addMessage({ role: "assistant", type: "text", text: `${state.hotel?.name || "Hotel"}\n${state.hotel?.description || "Property description not configured."}\n${location}` });
  } else if (action === "language") {
    const languages = state.hotel?.languages || ["en"];
    const current = Math.max(0, languages.indexOf(document.documentElement.lang));
    const next = languages[(current + 1) % languages.length];
    document.documentElement.lang = next;
    localStorage.setItem("concierge-language", next);
    addMessage({ role: "assistant", type: "status", text: `Language preference set to ${next}. Available: ${languages.join(", ")}.` });
  } else if (action === "accessibility") {
    const enabled = document.body.classList.toggle("accessibility-mode");
    localStorage.setItem("concierge-accessibility", enabled ? "1" : "0");
    addMessage({ role: "assistant", type: "status", text: `Accessibility display mode ${enabled ? "enabled" : "disabled"}.` });
  } else if (action === "privacy") {
    addMessage({ role: "assistant", type: "text", text: "Your concierge session is temporary. Hotel staff should only receive information needed to fulfill confirmed requests. Avoid sharing payment details or passwords in chat." });
  } else if (action === "help") {
    addMessage({ role: "assistant", type: "text", text: "Ask about verified hotel information, enabled services, dining, facilities, Wi-Fi access, or local recommendations. Operational requests are created only after you confirm them." });
  }
}

async function openPropertyMap() {
  const modal = $("property-map-modal");
  const markers = $("property-map-markers");
  markers.innerHTML = "";
  const data = await jsonFetch(`/api/guest/zones?property_id=${encodeURIComponent(state.hotel?.property_id || "")}`);
  for (const zone of data.zones || []) {
    const geometry = zone.geometry || {};
    if (geometry.type !== "ellipse" || !geometry.sourceCanvas) continue;
    const marker = document.createElement("button");
    marker.type = "button";
    marker.className = "property-map-marker";
    marker.style.left = `${((geometry.x + geometry.width / 2) / geometry.sourceCanvas.width) * 100}%`;
    marker.style.top = `${((geometry.y + geometry.height / 2) / geometry.sourceCanvas.height) * 100}%`;
    marker.textContent = geometry.mapNumber || "•";
    marker.setAttribute("aria-label", zone.name);
    marker.title = zone.name;
    marker.addEventListener("click", () => showToast(zone.name));
    markers.appendChild(marker);
  }
  modal.hidden = false;
  document.body.classList.add("map-open");
  $("close-map-button").focus();
}

function closePropertyMap() {
  $("property-map-modal").hidden = true;
  document.body.classList.remove("map-open");
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
  renderConfiguredModules(profile.guest_modules || []);
  const maintenance = $("maintenance-banner");
  const application = profile.application || {};
  maintenance.hidden = !application.maintenance_enabled;
  maintenance.textContent = application.maintenance_message || "Concierge maintenance is in progress. Some requests may take longer than usual.";
  renderWelcomeState();
}

function renderConfiguredModules(modules) {
  const list = $("configured-module-list");
  list.innerHTML = "";
  for (const module of [...modules].sort((a, b) => Number(a.order || 0) - Number(b.order || 0))) {
    const button = document.createElement("button"); button.type = "button"; button.textContent = module.name;
    button.addEventListener("click", () => { closeMenu(); sendChat(module.prompt).catch((error) => showToast(error.message, "warning")); });
    list.appendChild(button);
  }
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
  root.style.setProperty("--button-color", theme.buttonColor || theme.accent || "#18181b");
  root.style.setProperty("--accent-text", theme.accentText || "#ffffff");
  root.style.setProperty("--border", theme.border || "#e4e4e7");
  root.style.setProperty("--user-message-bg", theme.userMessageBackground || "#eeeeee");
  root.style.setProperty("--user-message-text", theme.userMessageText || "#18181b");
  root.style.setProperty("--assistant-text", theme.assistantText || theme.textPrimary || "#18181b");
  root.style.setProperty("--column-width", (layout.contentWidth || 840) + "px");
  root.style.setProperty("--composer-max", (layout.composerWidth || 840) + "px");
  root.style.setProperty("--message-width", (layout.messageWidth || 680) + "px");
  root.style.setProperty("--message-spacing", (messages.messageSpacing || layout.messageSpacing || 24) + "px");
  root.style.setProperty("--message-radius", (messages.radius || theme.radius || 18) + "px");
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
  document.body.classList.toggle("concierge-name-hidden", header.showConciergeName === false);
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
  const [profile, catalog, recommendations] = await Promise.all([
    jsonFetch("/api/hotel"),
    jsonFetch("/api/guest/service-catalog"),
    jsonFetch("/api/guest/recommendations"),
  ]);
  state.services = catalog.services || [];
  state.recommendations = recommendations.recommendations || [];
  applyHotelProfile(profile);
  await maybeShowIntro();

  state.clientId = localStorage.getItem("concierge-client-id") || createClientId();
  localStorage.setItem("concierge-client-id", state.clientId);

  if (localStorage.getItem("concierge-accessibility") === "1") document.body.classList.add("accessibility-mode");
  document.documentElement.lang = localStorage.getItem("concierge-language") || document.documentElement.lang;
  await startGuestSession();
}

async function startGuestSession() {
  const session = await jsonFetch("/api/session/start", {
    method: "POST",
    body: JSON.stringify({
      client_id: state.clientId,
      gateway_context: gatewayContext(),
    }),
  });
  state.sessionId = session.session_id;
}

async function pollStaffMessages() {
  if (!state.sessionId || document.hidden) return;
  try {
    const data = await jsonFetch(`/api/guest/conversations/${encodeURIComponent(state.sessionId)}/staff-messages`);
    for (const message of data.messages || []) {
      if (state.staffMessageIds.has(message.message_id)) continue;
      state.staffMessageIds.add(message.message_id);
      addMessage({ role: "assistant", type: "text", text: message.content });
    }
  } catch (error) {
    if (!String(error.message).toLowerCase().includes("expired")) console.warn("Unable to refresh staff replies", error);
  }
}

function ensureStarted() {
  if (!startupPromise) startupPromise = start();
  return startupPromise;
}

ensureStarted().catch((error) => {
  addMessage({ role: "assistant", type: "error", text: "Unable to start the concierge: " + error.message });
});
window.setInterval(pollStaffMessages, 3000);
