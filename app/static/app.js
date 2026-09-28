const state = {
  sessionId: null,
  hotel: null,
  clientId: null,
  messages: [],
  authenticated: false,
  room: null,
  draftKey: "concierge-draft",
  inputPending: false,
  mode: "auto",
  intro: null,
  services: [],
  recommendations: [],
  restaurants: [],
  personalization: null,
  staffMessageIds: new Set(),
  staffMessagingEnabled: false,
  hasPropertyMap: false,
  activeView: "home",
  homeData: null,
};

let startupPromise = null;

const $ = (id) => document.getElementById(id);

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
  if (!response.ok) {
    const error = new Error(errorMessage(data.detail));
    error.status = response.status;
    throw error;
  }
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
  const suggestions = activeSuggestions();
  document.querySelector(".suggestion-heading").hidden = suggestions.length === 0;
  for (const [index, item] of suggestions.entries()) {
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

const guestViewIds = {
  home: "home-view", explore: "explore-view", requests: "requests-view", stay: "stay-view", concierge: "concierge-view",
};

function setupViews() {
  for (const button of document.querySelectorAll(".guest-bottom-nav [data-view]")) {
    button.addEventListener("click", () => setActiveView(button.dataset.view));
  }
  document.querySelectorAll("[data-open-view]").forEach((button) => {
    button.addEventListener("click", () => setActiveView(button.dataset.openView));
  });
  $("manage-preferences").addEventListener("click", () => openMemoryPanel().catch((error) => showToast(error.message, "warning")));
  $("close-menu-view").addEventListener("click", () => {
    state.selectedRestaurantMenu = null;
    $("menu-section").hidden = true;
    renderExplore();
  });
  setActiveView("home");
}

function setActiveView(view) {
  if (!guestViewIds[view]) return;
  state.activeView = view;
  for (const [name, id] of Object.entries(guestViewIds)) {
    const element = $(id);
    element.hidden = name !== view;
    element.setAttribute("aria-hidden", name === view ? "false" : "true");
  }
  for (const button of document.querySelectorAll(".guest-bottom-nav [data-view]")) {
    if (button.dataset.view === view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  document.body.dataset.guestView = view;
  if (view === "requests") {
    renderRequestCatalog();
    ensureStarted().then(() => {
      if (state.activeView === "requests") return loadRequests();
    }).catch(() => {});
  }
  if (view === "explore") renderExplore();
  if (view === "stay") renderStay();
  if (view === "concierge") requestAnimationFrame(() => $("composer-input").focus({ preventScroll: true }));
}

async function refreshHome() {
  if (!state.sessionId) return;
  const data = await jsonFetch(`/api/guest/home?session_id=${encodeURIComponent(state.sessionId)}`);
  state.homeData = data;
  renderHome(data);
  if (state.activeView === "explore") renderExplore();
  if (state.activeView === "stay") renderStay();
}

function createGuestCard(card) {
  const article = document.createElement("article");
  article.className = `guest-content-card guest-card-${card.type || "general"}`;
  const heading = document.createElement("strong");
  heading.textContent = card.title || "Hotel information";
  article.appendChild(heading);
  if (card.subtitle) {
    const subtitle = document.createElement("span");
    subtitle.className = "guest-card-subtitle";
    subtitle.textContent = card.subtitle;
    article.appendChild(subtitle);
  }
  if (card.status) {
    const status = document.createElement("span");
    status.className = "guest-card-status";
    status.textContent = String(card.status).replaceAll("_", " ");
    article.appendChild(status);
  }
  if (card.description) {
    const description = document.createElement("p");
    description.textContent = card.description;
    article.appendChild(description);
  }
  if (card.personalized) {
    const reason = document.createElement("small");
    reason.textContent = "Based on your saved dining preference";
    article.appendChild(reason);
  }
  const actions = document.createElement("div");
  actions.className = "guest-card-actions";
  if (card.type === "restaurant" && card.restaurant_id) {
    actions.appendChild(guestButton("View menu", () => showRestaurantMenu(card.restaurant_id, card.title)));
  }
  if (card.type === "request" && card.request_id) {
    actions.appendChild(guestButton("Track request", () => setActiveView("requests"), "secondary"));
    if (card.cancellable) actions.appendChild(guestButton("Cancel", () => cancelRequest(card.request_id, card.title), "text"));
  }
  if (card.type === "recommendation" && card.map_url) {
    actions.appendChild(guestButton("Directions", () => window.open(card.map_url, "_blank", "noopener,noreferrer")));
  }
  if (card.type === "event") {
    actions.appendChild(guestButton(card.cta || "View event", () => setActiveView("explore")));
  }
  if (actions.childElementCount) article.appendChild(actions);
  return article;
}

function guestButton(label, action, style = "") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = style;
  button.textContent = label;
  button.addEventListener("click", action);
  return button;
}

function renderHome(data) {
  const name = data.preferred_name ? `, ${data.preferred_name}` : "";
  setText("home-greeting", `${data.greeting || "Welcome"}${name}`);
  setText("home-name", "Your stay");
  setText("home-stay-phase", data.stay?.status === "checked_in" ? "Stay in progress" : data.stay?.status === "unverified" ? "Guest services" : "");
  const primary = $("home-primary");
  primary.replaceChildren();
  const primaryCard = data.primary_card;
  if (primaryCard) {
    const label = document.createElement("span");
    label.className = "home-eyebrow";
    label.textContent = data.primary_action?.label || "For you";
    primary.appendChild(label);
    primary.appendChild(createGuestCard(primaryCard));
    primary.hidden = false;
  } else {
    primary.hidden = true;
  }
  const openRequests = data.active_requests || [];
  $("home-requests-section").hidden = openRequests.length === 0;
  const requestList = $("home-requests");
  requestList.replaceChildren();
  for (const item of openRequests.slice(0, 2)) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "home-request-row";
    row.append(document.createTextNode(item.name || "Request"));
    const detail = document.createElement("small");
    detail.textContent = `${item.department || "Hotel team"} · ${String(item.status || "In progress").replaceAll("_", " ")}`;
    row.appendChild(detail);
    row.addEventListener("click", () => setActiveView("requests"));
    requestList.appendChild(row);
  }
  const cards = (data.cards || []).filter((card) => !(primaryCard && card.type === primaryCard.type && card.title === primaryCard.title));
  $("home-cards-section").hidden = cards.length === 0;
  $("home-cards").replaceChildren(...cards.slice(0, 4).map(createGuestCard));
  const quickActions = $("quick-actions");
  quickActions.replaceChildren();
  for (const action of data.quick_actions || []) {
    quickActions.appendChild(guestButton(action.label, () => setActiveView(action.view), "quick-action"));
  }
  if (data.inventory) state.inventory = data.inventory;
  if (state.activeView === "stay") renderStay();
}

function propertyDateTime(timestamp, options = { dateStyle: "medium", timeStyle: "short" }) {
  if (!timestamp) return "";
  try {
    return new Intl.DateTimeFormat(document.documentElement.lang || "en", { ...options, timeZone: state.hotel?.timezone || "UTC" }).format(new Date(timestamp * 1000));
  } catch {
    return "";
  }
}

const requestStatusLabels = { new: "New", assigned: "Staff assigned", accepted: "Accepted", in_progress: "In progress", delivered: "Delivered", completed: "Completed", cancelled: "Cancelled" };

async function loadRequests() {
  if (!state.sessionId) return;
  const data = await jsonFetch(`/api/guest/requests?session_id=${encodeURIComponent(state.sessionId)}`);
  const list = $("request-list");
  list.replaceChildren();
  const records = data.requests || [];
  $("requests-empty").hidden = records.length > 0;
  for (const request of records) {
    const card = document.createElement("article");
    card.className = "request-status-card";
    const title = document.createElement("strong");
    title.textContent = request.name || "Service request";
    const department = document.createElement("span");
    department.textContent = request.department || "Hotel team";
    const status = document.createElement("span");
    status.className = "request-status-pill";
    status.textContent = requestStatusLabels[request.status] || "Status unavailable";
    const description = document.createElement("p");
    description.textContent = request.description || "";
    const submitted = document.createElement("small");
    submitted.textContent = `Submitted ${propertyDateTime(request.created_at)}`;
    card.append(title, department, status, description, submitted);
    if (request.updated_at && request.updated_at !== request.created_at) {
      const updated = document.createElement("small");
      updated.textContent = `Updated ${propertyDateTime(request.updated_at)}`;
      card.appendChild(updated);
    }
    if (request.cancellable) card.appendChild(guestButton("Cancel request", () => cancelRequest(request.request_id, request.name), "text"));
    list.appendChild(card);
  }
  renderRequestCatalog();
}

function renderRequestCatalog() {
  const list = $("request-catalog-list");
  const empty = $("request-catalog-empty");
  if (!list || !empty) return;
  const services = (state.services || []).filter((service) => service.enabled && !service.archived);
  empty.hidden = services.length > 0;
  list.replaceChildren();
  for (const service of services) {
    const row = document.createElement("article");
    row.className = "service-action-row";
    const copy = document.createElement("div");
    copy.className = "service-action-copy";
    const title = document.createElement("strong");
    title.textContent = service.name || "Hotel service";
    copy.appendChild(title);
    const descriptionText = service.guest_description || service.description || "";
    if (descriptionText) {
      const description = document.createElement("p");
      description.textContent = descriptionText;
      copy.appendChild(description);
    }
    const requestButton = guestButton("Request", () => proposeConfiguredService(service));
    requestButton.className = "service-action-button";
    row.append(copy, requestButton);
    list.appendChild(row);
  }
}

async function proposeConfiguredService(service) {
  const confirmation = $("request-action-confirmation");
  confirmation.replaceChildren();
  confirmation.hidden = true;
  try {
    const proposal = await jsonFetch("/api/guest/actions/propose", {
      method: "POST", body: JSON.stringify({ session_id: state.sessionId, message: service.name }),
    });
    if (proposal.status !== "proposed") {
      showToast(proposal.status === "ambiguous" ? "This service needs clarification. Please ask the concierge." : "This service is no longer available.", "warning");
      return;
    }
    const card = document.createElement("article");
    card.className = "request-action-confirmation";
    const title = document.createElement("strong");
    title.textContent = proposal.card?.title || service.name;
    card.appendChild(title);
    if (proposal.card?.department) {
      const department = document.createElement("span");
      department.textContent = proposal.card.department;
      card.appendChild(department);
    }
    const note = document.createElement("p");
    note.textContent = "Send this request to the hotel team?";
    card.appendChild(note);
    const actions = document.createElement("div");
    actions.className = "guest-card-actions";
    const cancel = guestButton("Cancel", () => { confirmation.hidden = true; confirmation.replaceChildren(); }, "secondary");
    const send = guestButton("Send request", async () => {
      send.disabled = true;
      send.textContent = "Sending...";
      try {
        await jsonFetch("/api/guest/actions/confirm", {
          method: "POST", body: JSON.stringify({ session_id: state.sessionId, proposal_token: proposal.proposal_token }),
        });
        confirmation.hidden = true;
        confirmation.replaceChildren();
        await Promise.all([loadRequests(), refreshHome()]);
        showToast(`${service.name} request sent.`);
      } catch (error) {
        send.disabled = false;
        send.textContent = "Send request";
        showToast(error.message, "warning");
      }
    });
    actions.append(cancel, send);
    card.appendChild(actions);
    confirmation.replaceChildren(card);
    confirmation.hidden = false;
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) {
    showToast(error.message, "warning");
  }
}

async function cancelRequest(requestId, name) {
  if (!window.confirm(`Cancel ${name || "this request"}?`)) return;
  try {
    await jsonFetch(`/api/guest/requests/${encodeURIComponent(requestId)}/cancel`, {
      method: "POST", body: JSON.stringify({ session_id: state.sessionId, confirmed: true }),
    });
    await Promise.all([loadRequests(), refreshHome()]);
    showToast("Request cancelled.");
  } catch (error) {
    showToast(error.message, "warning");
  }
}

function renderExplore() {
  const data = state.homeData?.inventory || state.inventory || {};
  const restaurants = data.restaurants || [];
  const facilities = data.facilities || [];
  const events = data.events || [];
  const promotions = data.promotions || [];
  const recommendations = data.recommendations || [];
  const fillCards = (id, items, mapper) => $(id).replaceChildren(...items.map(mapper));
  $("dining-section").hidden = restaurants.length === 0;
  fillCards("dining-list", restaurants, (item) => createGuestCard({
    type: "restaurant", title: item.name, subtitle: [item.cuisine, item.location].filter(Boolean).join(" · "),
    status: item.status === "closed" ? "Closed" : "", description: item.description, restaurant_id: item.restaurant_id,
  }));
  $("facility-section").hidden = facilities.length === 0;
  fillCards("facility-list", facilities, (item) => createGuestCard({
    type: "facility", title: item.name, subtitle: item.facility_type,
    status: item.live_status === "open" ? "" : item.live_status, description: item.description,
  }));
  $("event-section").hidden = events.length === 0;
  fillCards("event-list", events, (item) => createGuestCard({
    type: "event", title: item.title, subtitle: propertyDateTime(item.starts_at), description: item.description,
    event_id: item.event_id, cta: item.cta || "View event",
  }));
  $("promotion-section").hidden = promotions.length === 0;
  fillCards("promotion-list", promotions, (item) => createGuestCard({
    type: "promotion", title: item.title, subtitle: item.starts_at ? propertyDateTime(item.starts_at) : "",
    description: item.description,
  }));
  $("recommendation-section").hidden = recommendations.length === 0;
  fillCards("recommendation-list", recommendations, (item) => createGuestCard({
    type: "recommendation", title: item.name, subtitle: item.category, description: item.description || item.address,
    map_url: item.map_url,
  }));
  $("explore-empty").hidden = Boolean(restaurants.length || facilities.length || events.length || promotions.length || recommendations.length);
  $("menu-section").hidden = !state.selectedRestaurantMenu;
}

async function showRestaurantMenu(restaurantId, restaurantName) {
  setActiveView("explore");
  setText("menu-heading", `${restaurantName} menu`);
  $("menu-list").replaceChildren();
  $("menu-section").hidden = false;
  state.selectedRestaurantMenu = restaurantId;
  try {
    const data = await jsonFetch(`/api/guest/restaurants/${encodeURIComponent(restaurantId)}/menus`);
    $("menu-list").replaceChildren();
    const menus = data.menus || [];
    if (!menus.length) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "A published menu is not available yet. Please ask restaurant staff.";
      $("menu-list").appendChild(empty);
    }
    for (const menu of menus) {
      const group = document.createElement("section");
      group.className = "menu-group";
      const heading = document.createElement("h2");
      heading.textContent = [menu.name, menu.meal_period].filter(Boolean).join(" · ");
      group.appendChild(heading);
      for (const item of menu.items || []) {
        const card = document.createElement("article");
        card.className = "guest-content-card menu-card";
        const title = document.createElement("strong");
        title.textContent = item.name || "Menu item";
        card.appendChild(title);
        if (item.price) { const price = document.createElement("span"); price.className = "guest-card-status"; price.textContent = item.price; card.appendChild(price); }
        if (item.description) { const description = document.createElement("p"); description.textContent = item.description; card.appendChild(description); }
        if ((item.dietary_tags || []).length) { const tags = document.createElement("small"); tags.textContent = item.dietary_tags.join(" · "); card.appendChild(tags); }
        const allergen = document.createElement("small");
        allergen.textContent = (item.allergens || []).length ? `Allergens: ${item.allergens.join(", ")}` : "Confirm allergen details with restaurant staff.";
        card.appendChild(allergen);
        group.appendChild(card);
      }
      $("menu-list").appendChild(group);
    }
    document.querySelector("#explore-view .guest-view-inner").scrollTop = 0;
  } catch (error) {
    showToast(error.message, "warning");
  }
}

function renderStay() {
  if (!state.hotel) return;
  const data = state.homeData || {};
  setText("stay-property-name", state.hotel.name || "");
  const summary = $("stay-summary-card");
  summary.replaceChildren();
  const active = data.active_requests || [];
  const rows = [
    ["Status", data.stay?.status === "checked_in" ? "Stay in progress" : "Guest services available"],
    ["Active requests", String(active.length)],
    ["Dining", String((data.inventory?.restaurants || []).length)],
    ["Upcoming events", String((data.inventory?.events || []).length)],
  ];
  for (const [label, value] of rows) {
    const row = document.createElement("div");
    row.className = "stay-summary-row";
    const term = document.createElement("span"); term.textContent = label;
    const detail = document.createElement("strong"); detail.textContent = value;
    row.append(term, detail); summary.appendChild(row);
  }
  const preferences = (state.personalization?.enabled ? state.personalization.preferences : []) || [];
  const list = $("preference-summary");
  list.replaceChildren();
  if (!preferences.length) {
    const empty = document.createElement("p");
    empty.textContent = "Personalization is private. You can opt in to save preferences for your stay.";
    list.appendChild(empty);
  } else {
    for (const item of preferences) {
      const tag = document.createElement("span");
      tag.className = "preference-chip";
      tag.textContent = item.value;
      list.appendChild(tag);
    }
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
  const contextual = state.homeData?.suggested_prompts;
  if (contextual?.length) return contextual.map((prompt) => ({ label: prompt, prompt }));
  const configured = state.hotel?.design?.suggestions || [];
  const suggestions = configured
    .filter((item) => item.enabled !== false)
    .sort((a, b) => (a.order || 0) - (b.order || 0))
    .map((item) => ({ label: item.label, prompt: item.prompt }));
  return suggestions;
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
    label.textContent = message.sender_label || "Concierge";
    row.appendChild(label);
  }

  if (message.type === "authentication") {
    row.appendChild(renderAuthenticationCard(message));
    return row;
  }

  if (message.type === "recommendation") {
    row.appendChild(renderText(message.text));
    if (message.contactPhone) {
      const phone = String(message.contactPhone).trim();
      const tel = phone.replace(/[^0-9+]/g, "");
      if (/^\+?\d{3,15}$/.test(tel)) {
        const link = document.createElement("a");
        link.className = "concierge-call-link";
        link.href = `tel:${tel}`;
        link.textContent = `Call concierge ${phone}`;
        row.appendChild(link);
      }
    }
    row.appendChild(renderRecommendationResults(message.results || []));
    return row;
  }

  if (message.type === "concierge-contact") {
    row.appendChild(renderText(message.text));
    const phone = String(message.phone || "").trim();
    const tel = phone.replace(/[^0-9+]/g, "");
    if (/^\+?\d{3,15}$/.test(tel)) {
      const link = document.createElement("a");
      link.className = "concierge-call-link";
      link.href = `tel:${tel}`;
      link.textContent = `Call concierge ${phone}`;
      row.appendChild(link);
    }
    return row;
  }

  if (message.type === "confirmation") {
    row.appendChild(renderConfirmationCard(message));
    return row;
  }

  if (message.type === "request-created") {
    row.appendChild(renderRequestCreated(message));
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
  const lines = String(text || "").replace(/\r\n?/g, "\n").split("\n");
  let activeList = null;
  let codeBlock = null;

  for (const rawLine of lines) {
    const line = rawLine.replace(/^\*{4,}([^*\n]*?)\*{4,}$/, "$1");
    if (/^\s*```/.test(line)) {
      codeBlock = codeBlock ? null : document.createElement("pre");
      if (codeBlock) {
        codeBlock.className = "message-code-block";
        body.appendChild(codeBlock);
      }
      activeList = null;
      continue;
    }
    if (codeBlock) {
      codeBlock.textContent += `${line}\n`;
      continue;
    }
    if (!line.trim()) {
      activeList = null;
      continue;
    }
    if (/^\s{0,3}(?:\*{3,}|-{3,}|_{3,})\s*$/.test(line)) {
      activeList = null;
      body.appendChild(document.createElement("hr"));
      continue;
    }

    const heading = line.match(/^\s{0,3}(#{1,6})\s*(.*)$/);
    if (heading) {
      activeList = null;
      if (!heading[2].trim()) continue;
      const section = document.createElement("h3");
      section.className = "message-heading";
      appendInlineMarkdown(section, heading[2]);
      body.appendChild(section);
      continue;
    }

    const listItem = line.match(/^\s{0,3}([-+*]|\d+[.)])\s+(.+)$/);
    if (listItem) {
      const numbered = /^\d/.test(listItem[1]);
      const listTag = numbered ? "ol" : "ul";
      if (!activeList || activeList.tagName.toLowerCase() !== listTag) {
        activeList = document.createElement(listTag);
        activeList.className = "message-list-items";
        body.appendChild(activeList);
      }
      const item = document.createElement("li");
      appendInlineMarkdown(item, listItem[2]);
      activeList.appendChild(item);
      continue;
    }

    const quote = line.match(/^\s{0,3}>\s?(.*)$/);
    const paragraph = document.createElement(quote ? "blockquote" : "p");
    paragraph.className = quote ? "message-quote" : "message-paragraph";
    appendInlineMarkdown(paragraph, quote ? quote[1] : line.trim());
    body.appendChild(paragraph);
    activeList = null;
  }
  return body;
}

function appendInlineMarkdown(target, value, depth = 0) {
  const text = String(value || "");
  if (depth >= 4) {
    target.appendChild(document.createTextNode(text.replace(/(?:\*{2,}|~~|`{1,3})/g, "")));
    return;
  }

  const markdown = /(\*{1,3}|~~|`)(.+?)\1/g;
  let cursor = 0;
  for (const match of text.matchAll(markdown)) {
    if (match.index > cursor) {
      target.appendChild(document.createTextNode(text.slice(cursor, match.index).replace(/(?:\*{2,}|~~|`{1,3})/g, "")));
    }
    const marker = match[1];
    const content = match[2];
    const element = document.createElement(marker === "`" ? "code" : marker === "~~" ? "del" : marker.length > 1 ? "strong" : "em");
    if (marker === "`") element.textContent = content;
    else appendInlineMarkdown(element, content, depth + 1);
    target.appendChild(element);
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) {
    target.appendChild(document.createTextNode(text.slice(cursor).replace(/(?:\*{2,}|~~|`{1,3})/g, "")));
  }
}

const guestAuthFieldDefinitions = {
  complimentary: [],
  local: [{ name: "username", label: "Username", autocomplete: "username" }, { name: "password", label: "Password", type: "password", autocomplete: "current-password" }],
  radius: [{ name: "username", label: "Username", autocomplete: "username" }, { name: "password", label: "Password", type: "password", autocomplete: "current-password" }],
  pms: [{ name: "room", label: "Room number", autocomplete: "off", inputmode: "numeric" }, { name: "last_name", label: "Last name or PMS password", autocomplete: "family-name" }],
  credit_card: [],
  access_code: [{ name: "access_code", label: "Access code", autocomplete: "off" }],
  global_account: [{ name: "username", label: "Username", autocomplete: "username" }, { name: "password", label: "Password", type: "password", autocomplete: "current-password" }],
  global_code: [{ name: "global_code", label: "Global access code", autocomplete: "off" }],
  user_form: [{ name: "name", label: "Full name", autocomplete: "name" }, { name: "email", label: "Email", type: "email", autocomplete: "email" }],
  social_network: [{ name: "social_provider", label: "Social login provider", type: "select", options: ["Facebook", "Google", "Line", "WeChat"] }],
};

function renderAuthenticationCard() {
  const card = document.createElement("form");
  card.className = "inline-card auth-card";
  const enabled = enabledAuthenticationTypes();
  if (!enabled.length) {
    const note = document.createElement("p");
    note.textContent = "No Wi-Fi authentication methods are enabled for this hotel.";
    card.appendChild(note);
    return card;
  }
  const methodLabel = document.createElement("label");
  methodLabel.textContent = "Login method";
  const methodSelect = document.createElement("select");
  methodSelect.name = "authType";
  methodSelect.required = true;
  for (const method of enabled) {
    const option = document.createElement("option");
    option.value = method.id;
    option.textContent = method.label;
    methodSelect.appendChild(option);
  }
  methodLabel.appendChild(methodSelect);
  card.appendChild(methodLabel);

  const fields = document.createElement("div");
  fields.className = "auth-fields";
  card.appendChild(fields);
  const renderFields = () => {
    fields.replaceChildren();
    const method = enabled.find((item) => item.id === methodSelect.value);
    const definitions = guestAuthFieldDefinitions[methodSelect.value] || [];
    if (methodSelect.value === "credit_card") {
      const note = document.createElement("p");
      note.textContent = "Payment details will be entered on the ANTlabs secure payment page.";
      fields.appendChild(note);
    } else if (!definitions.length) {
      const note = document.createElement("p");
      note.textContent = method?.guest_guidance || "Continue to the hotel's configured login page.";
      fields.appendChild(note);
    }
    for (const definition of definitions) {
      const label = document.createElement("label");
      label.textContent = definition.label;
      let input;
      if (definition.type === "select") {
        input = document.createElement("select");
        for (const optionValue of definition.options || []) {
          const option = document.createElement("option");
          option.value = optionValue.toLowerCase();
          option.textContent = optionValue;
          input.appendChild(option);
        }
      } else {
        input = document.createElement("input");
        input.type = definition.type || "text";
        input.autocomplete = definition.autocomplete || "off";
        if (definition.inputmode) input.inputMode = definition.inputmode;
        if (definition.placeholder) input.placeholder = definition.placeholder;
      }
      input.name = definition.name;
      label.appendChild(input);
      fields.appendChild(label);
    }
  };
  methodSelect.addEventListener("change", renderFields);
  renderFields();

  const submit = document.createElement("button");
  submit.type = "submit";
  submit.textContent = "Continue";
  card.appendChild(submit);
  card.addEventListener("submit", async (event) => {
    event.preventDefault();
    const credentials = Object.fromEntries([...fields.querySelectorAll("input, select")].map((input) => [input.name, input.value.trim()]));
    const required = methodSelect.value === "complimentary" ? [] : (guestAuthFieldDefinitions[methodSelect.value] || []);
    if (required.some((definition) => !credentials[definition.name])) {
      showToast(methodSelect.value === "pms" ? "Enter room number and last name." : "Complete the required fields and try again.", "warning");
      return;
    }
    submit.disabled = true;
    submit.textContent = "Checking...";
    await authenticateGuest(methodSelect.value, credentials, card);
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
  card.className = "inline-card confirmation-card guest-action-card";
  const title = document.createElement("strong");
  title.textContent = message.card?.title || "Service request";
  card.appendChild(title);
  if (message.card?.department) {
    const department = document.createElement("span");
    department.textContent = message.card.department;
    card.appendChild(department);
  }
  if (message.card?.description) {
    const description = document.createElement("p");
    description.textContent = message.card.description;
    card.appendChild(description);
  }
  const actions = document.createElement("div");
  actions.className = "guest-card-actions";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "secondary";
  cancel.textContent = "Cancel";
  cancel.addEventListener("click", () => {
    message.dismissed = true;
    card.closest(".message-row")?.remove();
  });
  const button = document.createElement("button");
  button.type = "button";
  button.disabled = Boolean(message.submitting || message.confirmed || message.dismissed);
  button.textContent = message.confirmed ? "Request sent" : message.submitting ? "Sending..." : message.actionLabel || "Send request";
  button.addEventListener("click", async () => {
    if (message.submitting || message.confirmed || message.dismissed) return;
    message.submitting = true;
    button.disabled = true;
    button.textContent = "Sending...";
    try {
      const result = await jsonFetch("/api/guest/actions/confirm", {
        method: "POST",
        body: JSON.stringify({ session_id: state.sessionId, proposal_token: message.proposalToken }),
      });
      message.submitting = false;
      message.confirmed = true;
      message.requestId = result.request.request_id;
      button.textContent = "Request sent";
      cancel.hidden = true;
      addMessage({ role: "assistant", type: "request-created", request: result.request });
      await Promise.all([refreshHome(), loadRequests()]);
    } catch (error) {
      message.submitting = false;
      button.disabled = false;
      button.textContent = message.actionLabel || "Send request";
      addMessage({ role: "assistant", type: "error", text: error.message });
    }
  });
  actions.append(cancel, button);
  card.appendChild(actions);
  return card;
}

function renderRequestCreated(message) {
  const card = document.createElement("div");
  card.className = "inline-card request-created-card";
  const title = document.createElement("strong");
  title.textContent = message.request?.request_type || "Service request";
  const status = document.createElement("span");
  status.textContent = requestStatusLabels[message.request?.status] || "Submitted";
  const button = guestButton("Track request", () => setActiveView("requests"));
  card.append(title, status, button);
  return card;
}

async function authenticateGuest(authType, credentials, card) {
  try {
    await ensureStarted();
    const result = await jsonFetch("/api/authenticate", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        auth_type: authType,
        credentials,
      }),
    });

    if (result.status === "handoff_required" && result.handoff) {
      submitGatewayHandoff(result.handoff);
      return;
    }

    if (result.status === "authenticated") {
      state.authenticated = true;
      state.room = credentials.room || state.room;
      state.messages = state.messages.filter((message) => message.type !== "authentication");
      addMessage({ role: "assistant", type: "text", text: result.message || "Authentication was accepted." });
      await refreshHome().catch(() => {});
      return;
    }

    addMessage({ role: "assistant", type: "error", text: result.message || "I could not verify the stay. Please try again." });
  } catch (error) {
    addMessage({ role: "assistant", type: "error", text: error.message });
  } finally {
    if (card.isConnected) {
      const submit = card.querySelector("button[type='submit']");
      if (submit) {
        submit.disabled = false;
        submit.textContent = "Continue";
      }
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
  if (!message || state.inputPending) return;
  setActiveView("concierge");
  state.inputPending = true;
  updateComposerState();
  try {
    const conversationHistory = state.messages
      .filter((item) => (item.role === "user" && item.type === "text") || (item.role === "assistant" && ["text", "recommendation", "concierge-contact"].includes(item.type)))
      .filter((item) => String(item.text || "").trim())
      .slice(-10)
      .map((item) => ({ role: item.role === "user" ? "guest" : "assistant", content: item.text.slice(0, 2000) }));
    addMessage({ role: "user", type: "text", text: message });

    if (!state.sessionId) {
      try {
        await ensureStarted();
      } catch (error) {
        reportStartupError(error);
        return;
      }
    }

    if (isWifiRequest(message)) {
      clearSubmittedComposer(message);
      handleWifiRequest();
      return;
    }

    if (!isInformationRequest(message) && isServiceActionRequest(message)) {
      try {
        const proposal = await jsonFetch("/api/guest/actions/propose", {
          method: "POST", body: JSON.stringify({ session_id: state.sessionId, message }),
        });
        if (proposal.status === "proposed") {
          addMessage({
            role: "assistant", type: "confirmation", card: proposal.card,
            proposalToken: proposal.proposal_token, actionLabel: "Send request",
          });
          clearSubmittedComposer(message);
          return;
        }
        if (proposal.status === "ambiguous") {
          const choices = (proposal.choices || []).map((item) => item.department ? `${item.name} · ${item.department}` : item.name);
          addMessage({ role: "assistant", type: "text", text: `I found more than one matching hotel service: ${choices.join(", ")}. Which one would you like?` });
          clearSubmittedComposer(message);
          return;
        }
      } catch (error) {
        if (error.status && error.status < 500) {
          addMessage({ role: "assistant", type: "error", text: error.message });
          return;
        }
        // Chat remains an available fallback if the structured action service is offline.
      }
    }

    if (await sendChat(message, conversationHistory)) clearSubmittedComposer(message);
  } finally {
    state.inputPending = false;
    updateComposerState();
  }
}

function isServiceActionRequest(message) {
  return /\b(i need|i want|send|bring|deliver|request|could i have|can i have|please get|please send|please bring|arrange)\b/i.test(message);
}

function clearSubmittedComposer(message) {
  const input = $("composer-input");
  if (input.value.trim() === message) setDraft("");
}

async function sendChat(message, conversationHistory = []) {
  setActiveView("concierge");
  const initialRecommendations = isRestaurantRequest(message) ? state.recommendations : [];
  const thinking = {
    role: "assistant",
    type: initialRecommendations.length ? "recommendation" : "status",
    text: initialRecommendations.length ? "Here are the hotel's verified dining recommendations. I’m also checking for current options." : "Thinking...",
    results: initialRecommendations.map((place) => ({ ...place, category: place.category || "Hotel recommendation", description: place.description || place.address })),
  };
  state.messages.push(thinking);
  renderMessages();
  try {
    const result = await jsonFetch("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        message,
        mode: state.mode,
        conversation_history: conversationHistory,
      }),
    });
    if (result.human_takeover || result.ai_paused) {
      thinking.type = "status";
      thinking.text = result.human_takeover
        ? "Your request is with the restaurant team. A staff member can reply here."
        : "This staff request is closed. Start a new conversation if you need more help.";
      renderMessages();
      return true;
    }
    const livePlaces = result.places || [];
    const savedRecommendations = isRestaurantRequest(message) && !result.personalized_recommendations ? state.recommendations : [];
    const recommendationResults = livePlaces.length ? livePlaces : savedRecommendations;
    thinking.type = result.contact_concierge && !recommendationResults.length ? "concierge-contact" : recommendationResults.length ? "recommendation" : "text";
    thinking.text = result.answer;
    thinking.contactPhone = result.contact_concierge ? result.concierge_phone || "" : "";
    thinking.phone = thinking.contactPhone;
    thinking.results = recommendationResults.map((place) => ({ ...place, category: place.category || "Live Places result", description: place.description || place.address }));
    renderMessages();
    if (result.source === "personalization") {
      jsonFetch(`/api/guest/personalization?session_id=${encodeURIComponent(state.sessionId)}`)
        .then(renderPersonalization)
        .catch(() => {});
    }
    return true;
  } catch (error) {
    const savedRecommendations = isRestaurantRequest(message) ? state.recommendations : [];
    const phone = String(state.hotel?.concierge_phone || "");
    if (!error.status || error.status >= 500) {
      thinking.type = "concierge-contact";
      thinking.text = phone
        ? "I can't reach the concierge service right now. Please call the hotel concierge."
        : "I can't reach the concierge service right now. Please call the hotel concierge directly from your room phone or contact the front desk.";
      thinking.phone = phone;
    } else {
      thinking.type = savedRecommendations.length ? "recommendation" : "error";
      thinking.text = savedRecommendations.length
        ? "The AI service is temporarily unavailable. Here are the hotel's saved recommendations."
        : error.message;
    }
    thinking.results = savedRecommendations.map((place) => ({
      ...place,
      category: place.category || "Hotel recommendation",
      description: place.description || place.address,
    }));
    renderMessages();
    return false;
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
    const authenticationEnabled = state.hotel?.authentication?.enabled;
    addMessage({
      role: "assistant",
      type: "text",
      text: authenticationEnabled === false
        ? "Hotel Wi-Fi sign-in through Concierge is turned off. ANTlabs may still require a gateway login; please contact the front desk if you cannot connect."
        : "No supported Wi-Fi login method is currently enabled for this hotel. Please contact the front desk for access.",
    });
    return;
  }
  const names = enabled.map((item) => item.label).join(", ");
  addMessage({ role: "assistant", type: "text", text: `Choose an enabled Wi-Fi login method: ${names}.` });
  addMessage({ role: "assistant", type: "authentication" });
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
  $("send-button").disabled = state.inputPending || !input.value.trim();
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
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
      event.preventDefault();
      $("composer-form").requestSubmit();
    }
  });

  $("composer-form").addEventListener("submit", (event) => {
    event.preventDefault();
    handleGuestInput(input.value);
  });

}

function setupMenu() {
  $("personalize-cta").addEventListener("click", () => openMemoryPanel().catch((error) => showToast(error.message, "warning")));
  $("menu-button").addEventListener("click", openMenu);
  $("close-menu-button").addEventListener("click", () => closeMenu(true));
  $("hotel-menu").addEventListener("click", (event) => {
    if (event.target === $("hotel-menu")) closeMenu(true);
  });
  for (const button of document.querySelectorAll("[data-menu-action]")) {
    button.addEventListener("click", () => handleMenuAction(button.dataset.menuAction).catch((error) => showToast(error.message, "warning")));
  }
  $("close-map-button").addEventListener("click", closePropertyMap);
  $("close-memory-button").addEventListener("click", closeMemoryPanel);
  $("memory-modal").addEventListener("click", (event) => {
    if (event.target === $("memory-modal")) closeMemoryPanel();
  });
  $("memory-level").addEventListener("change", changePersonalizationLevel);
  $("memory-preference-form").addEventListener("submit", saveMemoryPreference);
  $("restaurant-staff-request-form").addEventListener("submit", requestRestaurantStaff);
  $("close-restaurant-staff-dialog").addEventListener("click", () => $("restaurant-staff-dialog").close());
  $("cancel-restaurant-staff-dialog").addEventListener("click", () => $("restaurant-staff-dialog").close());
  $("clear-memory-button").addEventListener("click", clearMemoryPreferences);
  $("disable-memory-button").addEventListener("click", () => setPersonalization(false, "stay").catch((error) => showToast(error.message, "warning")));
  $("property-map-modal").addEventListener("click", (event) => {
    if (event.target === $("property-map-modal")) closePropertyMap();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && $("hotel-menu").classList.contains("open")) closeMenu(true);
    if (event.key === "Escape" && !$("property-map-modal").hidden) closePropertyMap();
    if (event.key === "Escape" && !$("memory-modal").hidden) closeMemoryPanel();
  });
}

function openMenu() {
  const menu = $("hotel-menu");
  menu.inert = false;
  menu.classList.add("open");
  menu.setAttribute("aria-hidden", "false");
  $("menu-button").setAttribute("aria-expanded", "true");
  $("close-menu-button").focus();
}

function closeMenu(restoreFocus = false) {
  const menu = $("hotel-menu");
  menu.classList.remove("open");
  menu.setAttribute("aria-hidden", "true");
  menu.inert = true;
  $("menu-button").setAttribute("aria-expanded", "false");
  if (restoreFocus) $("menu-button").focus();
}

const memoryCategoryLabels = {
  food: "Food or cuisine", dietary: "Dietary need", budget: "Budget", travel_party: "Travel party",
  transportation: "Getting around", interests: "Interests", activities: "Activities", accessibility: "Accessibility",
  language: "Language", response_style: "Response style", trip_purpose: "Trip purpose", activity_time: "Activity time",
  preferred_name: "Preferred name",
};

async function openMemoryPanel() {
  if (!state.sessionId) await ensureStarted();
  $("memory-modal").hidden = false;
  $("memory-level").disabled = true;
  setText("memory-status", "Loading your settings…");
  const data = await jsonFetch(`/api/guest/personalization?session_id=${encodeURIComponent(state.sessionId)}`);
  renderPersonalization(data);
  $("close-memory-button").focus();
}

function closeMemoryPanel() {
  $("memory-modal").hidden = true;
  $("memory-preference-key").value = "";
  $("memory-preference-form").reset();
}

function renderPersonalization(data) {
  state.personalization = data;
  updatePersonalizedWelcome(data);
  const level = $("memory-level");
  level.value = data.enabled ? data.level : "private";
  level.disabled = !data.personalization_available;
  const personalOption = level.querySelector('option[value="personal"]');
  if (personalOption) personalOption.disabled = !data.allow_guest_profile;
  const nameOption = $("memory-category").querySelector('option[value="preferred_name"]');
  if (nameOption) nameOption.disabled = !data.allow_guest_profile || data.level !== "personal";
  setText("memory-status", data.personalization_available
    ? (data.enabled ? `Personalization is on for this ${data.level === "personal" ? "concierge session" : "stay/session"}.` : `Private mode is on. Saved preferences aren't used while this is selected.${data.suggested_level && data.suggested_level !== "private" ? ` You can choose ${data.suggested_level} to opt in.` : ""}`)
    : "Personalization is turned off by this hotel.");
  const list = $("memory-preference-list");
  list.replaceChildren();
  const preferences = data.preferences || [];
  setText("memory-count", preferences.length ? `${preferences.length} saved` : "Nothing saved");
  for (const preference of preferences) {
    const row = document.createElement("div");
    row.className = "memory-preference-row";
    const copy = document.createElement("div");
    const label = document.createElement("strong");
    label.textContent = memoryCategoryLabels[preference.category] || preference.category;
    const value = document.createElement("span");
    value.textContent = preference.value;
    const source = document.createElement("small");
    source.textContent = preference.persistence === "temporary" ? "Temporary" : preference.source === "inferred" ? "Inferred, lower confidence" : "Saved for this stay/session";
    copy.append(label, value, source);
    const actions = document.createElement("div");
    actions.className = "memory-preference-actions";
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "memory-link-button";
    edit.textContent = "Edit";
    edit.addEventListener("click", () => {
      $("memory-category").value = preference.category;
      $("memory-value").value = preference.value;
      $("memory-preference-key").value = preference.preference_key;
      $("memory-value").focus();
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "memory-link-button";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => removeMemoryPreference(preference.preference_key).catch((error) => showToast(error.message, "error")));
    actions.append(edit, remove);
    row.append(copy, actions);
    list.appendChild(row);
  }
  $("memory-preference-form").hidden = !data.personalization_available;
  $("clear-memory-button").disabled = !preferences.length;
  $("disable-memory-button").disabled = !data.personalization_available || !data.enabled;
}

function updatePersonalizedWelcome(data) {
  const baseGreeting = state.hotel?.design?.welcome?.greeting || "Good evening.";
  const preferredName = (data?.enabled && data.level === "personal" ? data.preferences || [] : [])
    .find((item) => item.category === "preferred_name")?.value;
  if (!preferredName || !document.documentElement.lang.toLowerCase().startsWith("en")) {
    setText("welcome-greeting", state.homeData?.greeting || baseGreeting);
    return;
  }
  const timeGreeting = state.homeData?.greeting || baseGreeting.replace(/[.,!]+$/, "");
  setText("welcome-greeting", `${timeGreeting}, ${preferredName}.`);
}

async function setPersonalization(enabled, level) {
  const data = await jsonFetch("/api/guest/personalization", {
    method: "PUT",
    body: JSON.stringify({ session_id: state.sessionId, enabled, level }),
  });
  renderPersonalization(data);
  await refreshHome().catch(() => {});
  return data;
}

async function changePersonalizationLevel() {
  const level = $("memory-level").value;
  try {
    await setPersonalization(level !== "private", level);
    showToast(level === "private" ? "Private mode enabled." : "Personalization enabled for this stay.");
  } catch (error) {
    showToast(error.message, "warning");
    await openMemoryPanel().catch(() => {});
  }
}

async function saveMemoryPreference(event) {
  event.preventDefault();
  if (!state.sessionId) return;
  try {
    if (!state.personalization?.enabled) await setPersonalization(true, "stay");
    const preference = await jsonFetch("/api/guest/personalization/preferences", {
      method: "PUT",
      body: JSON.stringify({
        session_id: state.sessionId,
        category: $("memory-category").value,
        value: $("memory-value").value.trim(),
        preference_key: $("memory-preference-key").value || null,
      }),
    });
    renderPersonalization(preference);
    await refreshHome().catch(() => {});
    $("memory-preference-form").reset();
    $("memory-preference-key").value = "";
    showToast("Preference saved.");
  } catch (error) {
    showToast(error.message, "warning");
  }
}

async function removeMemoryPreference(key) {
  const data = await jsonFetch(`/api/guest/personalization/preferences/${encodeURIComponent(key)}?session_id=${encodeURIComponent(state.sessionId)}`, { method: "DELETE" });
  renderPersonalization(data);
  await refreshHome().catch(() => {});
  showToast("Preference removed.");
}

async function clearMemoryPreferences() {
  const data = await jsonFetch(`/api/guest/personalization/preferences?session_id=${encodeURIComponent(state.sessionId)}`, { method: "DELETE" });
  renderPersonalization(data);
  await refreshHome().catch(() => {});
  showToast("Saved preferences cleared.");
}

async function handleMenuAction(action) {
  closeMenu();
  if (action === "new-chat") {
    setActiveView("concierge");
    state.messages = [];
    state.sessionId = null;
    state.staffMessagingEnabled = false;
    state.staffMessageIds = new Set();
    sessionStorage.removeItem("concierge-session-id");
    sessionStorage.removeItem("concierge-staff-messaging-session-id");
    await startGuestSession();
    renderMessages();
    showToast("Started a new conversation.");
    return;
  }
  if (action === "property-map") {
    await openPropertyMap();
  } else if (action === "restaurant-staff") {
    openRestaurantStaffRequest();
  } else if (action === "memory") {
    await openMemoryPanel();
  } else if (action === "hotel-info") {
    setActiveView("concierge");
    const location = state.hotel?.location?.address || "Address not configured";
    addMessage({ role: "assistant", type: "text", text: `${state.hotel?.name || "Property not configured"}\n${state.hotel?.description || "Property description not configured."}\n${location}` });
  } else if (action === "language") {
    setActiveView("concierge");
    const languages = state.hotel?.languages || ["en"];
    const current = Math.max(0, languages.indexOf(document.documentElement.lang));
    const next = languages[(current + 1) % languages.length];
    document.documentElement.lang = next;
    localStorage.setItem("concierge-language", next);
    try {
      const memory = await jsonFetch(`/api/guest/personalization?session_id=${encodeURIComponent(state.sessionId)}`);
      if (memory.enabled) {
        await jsonFetch("/api/guest/personalization/preferences", {
          method: "PUT",
          body: JSON.stringify({ session_id: state.sessionId, category: "language", value: next.toUpperCase(), preference_key: "language.preferred" }),
        });
      }
    } catch { /* The visible language switch remains available in private mode. */ }
    addMessage({ role: "assistant", type: "status", text: `Language preference set to ${next}. Available: ${languages.join(", ")}.` });
  } else if (action === "accessibility") {
    setActiveView("concierge");
    const enabled = document.body.classList.toggle("accessibility-mode");
    localStorage.setItem("concierge-accessibility", enabled ? "1" : "0");
    addMessage({ role: "assistant", type: "status", text: `Accessibility display mode ${enabled ? "enabled" : "disabled"}.` });
  } else if (action === "privacy") {
    setActiveView("concierge");
    addMessage({ role: "assistant", type: "text", text: "Your messages are processed by this property's configured AI service and aren't shown to hotel staff. Chat context stays in this open session and expires after inactivity. Confirmed service requests are shared with the hotel team. Personalization is optional; you can review or clear saved preferences in Personalization / Memory." });
  } else if (action === "help") {
    setActiveView("concierge");
    addMessage({ role: "assistant", type: "text", text: "Ask a question about this property. The concierge uses information configured for guests." });
  }
}

function openRestaurantStaffRequest() {
  const select = $("restaurant-staff-select");
  select.replaceChildren();
  for (const restaurant of state.restaurants) {
    if (["disabled", "archived"].includes(restaurant.status) || restaurant.archived) continue;
    select.appendChild(new Option(restaurant.name, restaurant.restaurant_id));
  }
  $("restaurant-staff-status").textContent = "";
  $("restaurant-staff-reason").value = "";
  if (!select.options.length) {
    addMessage({ role: "assistant", type: "status", text: "No restaurant staff contact is configured for this property yet." });
    return;
  }
  $("restaurant-staff-dialog").showModal();
  $("restaurant-staff-select").focus();
}

async function requestRestaurantStaff(event) {
  event.preventDefault();
  if (!state.sessionId) await ensureStarted();
  const form = $("restaurant-staff-request-form");
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  setText("restaurant-staff-status", "Sending your request…");
  try {
    await jsonFetch("/api/guest/conversations/" + encodeURIComponent(state.sessionId) + "/escalate", {
      method: "POST",
      body: JSON.stringify({ restaurant_id: $("restaurant-staff-select").value, reason: $("restaurant-staff-reason").value.trim() }),
    });
    state.staffMessagingEnabled = true;
    sessionStorage.setItem("concierge-staff-messaging-session-id", state.sessionId);
    $("restaurant-staff-dialog").close();
    setActiveView("concierge");
    addMessage({ role: "assistant", type: "status", text: "Your request is with the restaurant team. A team member can reply here." });
    pollStaffMessages();
  } catch (error) {
    setText("restaurant-staff-status", error.message || "We couldn't send your request. Please try again.");
  } finally {
    button.disabled = false;
  }
}

async function openPropertyMap() {
  const modal = $("property-map-modal");
  const markers = $("property-map-markers");
  const image = $("property-map-image");
  const empty = $("property-map-empty");
  markers.innerHTML = "";
  const data = await jsonFetch(`/api/guest/zones?property_id=${encodeURIComponent(state.hotel?.property_id || "")}`);
  const map = data.maps?.[0];
  image.hidden = !map?.url;
  empty.hidden = Boolean(map?.url);
  if (map?.url) {
    image.src = map.url;
    image.alt = `${state.hotel?.name || "Property"} map`;
  } else {
    image.removeAttribute("src");
  }
  for (const zone of map ? (data.zones || []) : []) {
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
  const hotelName = profile.name || "Property not configured";
  const conciergeName = profile.concierge_name || "AI concierge";
  setText("hotel-name", branding.hotelName || hotelName);
  setText("concierge-name", branding.conciergeName || conciergeName);
  setText("hotel-mark", hotelName.slice(0, 1).toUpperCase());
  $("hotel-mark").style.backgroundImage = branding.logoUrl ? `url("${branding.logoUrl}")` : "";
  $("hotel-mark").classList.toggle("has-image", Boolean(branding.logoUrl));
  setText("welcome-greeting", welcome.greeting || "Good evening.");
  setText("welcome-headline", welcome.headline || "How can I help?");
  $("composer-input").placeholder = composer.placeholder || "Ask a question...";
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
    const button = document.createElement("button");
    button.type = "button";
    const icon = document.createElement("span");
    icon.className = "menu-item-icon menu-item-icon-module";
    icon.setAttribute("aria-hidden", "true");
    icon.innerHTML = '<svg viewBox="0 0 24 24"><path d="m12 3 1.6 5.4L19 10l-5.4 1.6L12 17l-1.6-5.4L5 10l5.4-1.6L12 3Z"/><path d="m19 15 .7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7L19 15Z"/></svg>';
    const copy = document.createElement("span");
    copy.className = "menu-item-copy";
    const title = document.createElement("strong");
    title.textContent = module.name;
    const description = document.createElement("small");
    description.textContent = module.description || "Explore this service";
    copy.append(title, description);
    button.append(icon, copy);
    button.addEventListener("click", () => { closeMenu(); sendChat(module.prompt).catch((error) => showToast(error.message, "warning")); });
    list.appendChild(button);
  }
}

async function maybeShowIntro() {
  try {
    const intro = await jsonFetch("/api/guest/intro");
    state.intro = intro;
    if (!intro || intro.mode === "none") return;
    const seenKey = `concierge-intro-seen:${state.hotel?.property_id || "property"}`;
    if (intro.first_visit_only && localStorage.getItem(seenKey) === "1") return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const overlay = $("intro-overlay");
    const stage = $("intro-stage");
    const video = $("intro-video");
    const branding = state.hotel?.design?.branding || {};
    const logoUrl = branding.logoUrl || state.hotel?.logo_url || "";
    overlay.dataset.preset = reducedMotion ? "none" : intro.preset;
    overlay.style.background = intro.background || "#fbfbfa";
    overlay.style.color = intro.brand_color || "#18181b";
    overlay.style.setProperty("--intro-background", intro.background || "#fbfbfa");
    overlay.style.setProperty("--intro-brand", intro.brand_color || "#18181b");
    overlay.style.setProperty("--intro-duration", `${Math.max(300, Math.min(8000, intro.duration_ms || 1400))}ms`);
    $("intro-logo").style.background = intro.brand_color || "#18181b";
    $("intro-logo-mark").textContent = (state.hotel?.name || "Concierge").slice(0, 1).toUpperCase();
    const logoImage = $("intro-logo-image");
    if (logoUrl) {
      logoImage.src = logoUrl;
      logoImage.hidden = false;
      $("intro-logo-mark").hidden = true;
    } else {
      logoImage.removeAttribute("src");
      logoImage.hidden = true;
      $("intro-logo-mark").hidden = false;
    }
    $("intro-message").textContent = intro.welcome_message || state.hotel?.welcome || "Welcome";
    $("intro-skip").hidden = !intro.allow_skip;
    let finished = false;
    let finishTimer = null;
    const finish = () => {
      if (finished) return;
      finished = true;
      if (finishTimer) clearTimeout(finishTimer);
      video.pause();
      video.removeAttribute("src");
      video.hidden = true;
      overlay.hidden = true;
      if (intro.first_visit_only) localStorage.setItem(seenKey, "1");
    };
    $("intro-skip").onclick = finish;
    overlay.hidden = false;
    if (!reducedMotion && intro.mode === "custom_upload" && intro.asset_url && ["video/webm", "video/mp4"].includes(intro.asset_type)) {
      video.hidden = false;
      video.src = intro.asset_url;
      video.load();
      video.play().catch(() => { video.hidden = true; });
    }
    finishTimer = window.setTimeout(finish, reducedMotion ? 450 : Math.max(300, Math.min(8000, intro.duration_ms || 1400)));
    stage.addEventListener("animationend", () => {
      if (state.intro?.duration_ms && Number(state.intro.duration_ms) <= 800) finish();
    }, { once: true });
  } catch {
    $("intro-video").pause();
    $("intro-video").removeAttribute("src");
    $("intro-video").hidden = true;
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
  setupViews();
  let profile;
  try {
    profile = await jsonFetch("/api/hotel");
  } catch (error) {
    if (error.status === 404) {
      $("concierge-shell").hidden = true;
      $("property-unconfigured").hidden = false;
      document.title = "Property not configured | Concierge.Ai";
      return;
    }
    throw error;
  }
  const [catalog, recommendations, zones, hospitality] = await Promise.all([
    jsonFetch("/api/guest/service-catalog"),
    jsonFetch("/api/guest/recommendations"),
    jsonFetch("/api/guest/zones").catch(() => ({ maps: [] })),
    jsonFetch("/api/guest/facilities").catch(() => ({ restaurants: [] })),
  ]);
  state.services = catalog.services || [];
  state.recommendations = recommendations.recommendations || [];
  state.hasPropertyMap = Boolean(zones.maps?.length);
  state.restaurants = hospitality.restaurants || [];
  document.querySelector('[data-menu-action="restaurant-staff"]').hidden = !state.restaurants.some((item) => item.status !== "disabled" && item.status !== "archived" && !item.archived);
  document.querySelector('[data-menu-action="property-map"]').hidden = !state.hasPropertyMap;
  applyHotelProfile(profile);
  await maybeShowIntro();

  state.clientId = localStorage.getItem("concierge-client-id") || createClientId();
  localStorage.setItem("concierge-client-id", state.clientId);

  if (localStorage.getItem("concierge-accessibility") === "1") document.body.classList.add("accessibility-mode");
  document.documentElement.lang = localStorage.getItem("concierge-language")
    || state.hotel?.application?.default_language
    || state.hotel?.languages?.[0]
    || document.documentElement.lang;
  await startGuestSession();
}

async function startGuestSession() {
  let session = null;
  const previousSessionId = sessionStorage.getItem("concierge-session-id");
  if (previousSessionId) {
    try {
      session = await jsonFetch("/api/session/resume", {
        method: "POST",
        body: JSON.stringify({ client_id: state.clientId, session_id: previousSessionId }),
      });
    } catch {
      sessionStorage.removeItem("concierge-session-id");
    }
  }
  if (!session) {
    session = await jsonFetch("/api/session/start", {
      method: "POST",
      body: JSON.stringify({
        client_id: state.clientId,
        property_id: state.hotel?.property_id,
        gateway_context: gatewayContext(),
      }),
    });
  }
  state.sessionId = session.session_id;
  sessionStorage.setItem("concierge-session-id", session.session_id);
  state.staffMessagingEnabled = sessionStorage.getItem("concierge-staff-messaging-session-id") === session.session_id;
  try {
    const memory = await jsonFetch(`/api/guest/personalization?session_id=${encodeURIComponent(state.sessionId)}`);
    renderPersonalization(memory);
  } catch { /* The concierge remains available if optional personalization can't load. */ }
  try { await refreshHome(); } catch { /* The deterministic guest app stays available if the home summary endpoint is offline. */ }
}

async function pollStaffMessages() {
  if (!state.sessionId || !state.staffMessagingEnabled || document.hidden) return;
  try {
    const data = await jsonFetch(`/api/guest/conversations/${encodeURIComponent(state.sessionId)}/staff-messages`);
    for (const message of data.messages || []) {
      if (state.staffMessageIds.has(message.message_id)) continue;
      state.staffMessageIds.add(message.message_id);
      addMessage({ role: "assistant", sender_label: "Restaurant Staff", type: "text", text: message.content });
    }
    if (["resolved", "returned_to_ai"].includes(data.state)) {
      state.staffMessagingEnabled = false;
      sessionStorage.removeItem("concierge-staff-messaging-session-id");
      addMessage({ role: "assistant", type: "status", text: data.state === "resolved"
        ? "The restaurant team resolved this request. Start a new conversation if you need more help."
        : "The restaurant team returned this conversation to your concierge." });
    }
  } catch (error) {
    if (!String(error.message).toLowerCase().includes("expired")) console.warn("Unable to refresh staff replies", error);
  }
}

function ensureStarted() {
  if (!startupPromise) {
    startupPromise = start().catch((error) => {
      startupPromise = null;
      throw error;
    });
  }
  return startupPromise;
}

function reportStartupError(error) {
  const text = "Unable to start the concierge: " + error.message;
  if (state.messages.some((message) => message.role === "assistant" && message.type === "error" && message.text === text)) return;
  addMessage({ role: "assistant", type: "error", text });
}

ensureStarted().catch(reportStartupError);
window.setInterval(pollStaffMessages, 5000);
