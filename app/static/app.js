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
  homeActionsExpanded: false,
  homeSuggestionsExpanded: false,
  experiencePage: null,
  fixedNavigationResizeObserver: null,
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
  const { headers = {}, ...fetchOptions } = options;
  const sessionHeader = state.sessionId ? { "X-Concierge-Session": state.sessionId } : {};
  const response = await fetch(url, {
    ...fetchOptions,
    headers: { "Content-Type": "application/json", ...sessionHeader, ...headers },
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
  $("guest-bottom-nav").addEventListener("click", (event) => {
    const button = event.target.closest("[data-view]");
    if (button) setActiveView(button.dataset.view);
  });
  document.querySelectorAll("[data-open-view]").forEach((button) => {
    button.addEventListener("click", () => setActiveView(button.dataset.openView));
  });
  $("home-actions-toggle").addEventListener("click", () => {
    state.homeActionsExpanded = !state.homeActionsExpanded;
    if (state.homeData) renderHome(state.homeData);
  });
  $("home-suggestions-more").addEventListener("click", () => {
    state.homeSuggestionsExpanded = !state.homeSuggestionsExpanded;
    if (state.homeData) renderHome(state.homeData);
  });
  $("manage-preferences").addEventListener("click", () => openMemoryPanel().catch((error) => showToast(error.message, "warning")));
  window.addEventListener("popstate", () => {
    const path = window.location.pathname.replace(/\/$/, "") || "/";
    const page = (state.hotel?.design?.pages || []).find((item) => item.slug === path && item.enabled !== false);
    setActiveView(page?.id || "home", false);
  });
  $("close-menu-view").addEventListener("click", () => {
    state.selectedRestaurantMenu = null;
    $("menu-section").hidden = true;
    renderExplore();
  });
  setActiveView("home");
}

function setActiveView(view, focusComposer = true) {
  const configuredPages = state.hotel?.design?.pages || [];
  const page = configuredPages.find((item) => item.id === view && item.enabled !== false);
  if (!guestViewIds[view] && !page) return;
  state.activeView = view;
  state.experiencePage = page || null;
  const dynamicRoute = Boolean(page && view !== "home" && (page.id.startsWith("page-") || page.sections?.length));
  for (const [name, id] of Object.entries(guestViewIds)) {
    const element = $(id);
    const visible = !dynamicRoute && name === view;
    element.hidden = !visible;
    element.setAttribute("aria-hidden", visible ? "false" : "true");
  }
  $("custom-page-view").hidden = !dynamicRoute;
  $("custom-page-view").setAttribute("aria-hidden", dynamicRoute ? "false" : "true");
  for (const button of document.querySelectorAll(".guest-bottom-nav [data-view]")) {
    if (button.dataset.view === view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  for (const button of document.querySelectorAll(".experience-configured-navigation [data-page-id]")) {
    if (button.dataset.pageId === view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  document.body.dataset.guestView = view;
  if (page && (page.id.startsWith("page-") || page.id.startsWith("custom-"))) {
    const nextPath = page.slug || "/";
    if (window.location.pathname !== nextPath) history.pushState({ guestPage: page.id }, "", nextPath);
  } else if (view === "home" && !["/", ""].includes(window.location.pathname)) {
    history.pushState({ guestPage: "home" }, "", "/");
  }
  if (view === "home" && page && state.homeData) {
    renderHome(state.homeData);
  } else if (dynamicRoute && page) {
    renderConfiguredExperience(page, $("custom-experience-page"));
    renderComposerForPage(page, $("custom-experience-page"), state.hotel?.design || {});
  } else if (page) {
    renderComposerForPage(page, $("custom-experience-page"), state.hotel?.design || {});
  }
  renderMessages();
  if (view === "requests") {
    renderRequestCatalog();
    ensureStarted().then(() => {
      if (state.activeView === "requests") return loadRequests();
    }).catch(() => {});
  }
  if (view === "explore") renderExplore();
  if (view === "stay") renderStay();
  if (view === "concierge" && focusComposer) requestAnimationFrame(() => $("composer-input").focus({ preventScroll: true }));
}

async function refreshHome() {
  if (!state.sessionId) return;
  const data = await jsonFetch("/api/guest/home");
  state.homeData = data;
  renderHome(data);
  if (state.activeView === "explore") renderExplore();
  if (state.activeView === "stay") renderStay();
}

function safeGuestUrl(value, { allowDataImage = false, allowExternalHttp = false } = {}) {
  const raw = String(value || "").trim();
  if (!raw || /[\u0000-\u001f\\]/.test(raw)) return "";
  if (allowDataImage && /^data:image\/(?:png|jpeg|webp);base64,[a-z0-9+/=]+$/i.test(raw)) return raw;
  if (raw.startsWith("/") && !raw.startsWith("//")) return raw;
  try {
    const parsed = new URL(raw, window.location.href);
    if (!['https:', 'http:'].includes(parsed.protocol) || parsed.username || parsed.password) return "";
    if (parsed.protocol === "http:" && parsed.origin !== window.location.origin && !allowExternalHttp) return "";
    return parsed.href;
  } catch {
    return "";
  }
}

function openGuestUrl(value) {
  const url = safeGuestUrl(value, { allowExternalHttp: true });
  if (url) window.open(url, "_blank", "noopener,noreferrer");
}

function cardInventoryItem(card) {
  const inventory = state.homeData?.inventory || state.inventory || {};
  const collections = {
    restaurant: inventory.restaurants || [],
    facility: inventory.facilities || [],
    event: inventory.events || [],
    recommendation: inventory.recommendations || [],
  };
  const idFields = {
    restaurant: "restaurant_id", facility: "facility_id", event: "event_id", recommendation: "recommendation_id",
  };
  const idField = idFields[card.type];
  const id = card[idField];
  if (idField && id) return collections[card.type].find((item) => String(item[idField]) === String(id)) || null;
  return collections[card.type]?.find((item) => item.name === card.title || item.title === card.title) || null;
}

function createGuestCard(card) {
  const article = document.createElement("article");
  const knownTypes = new Set(["restaurant", "request", "recommendation", "event", "facility", "promotion", "general"]);
  const type = knownTypes.has(card.type) ? card.type : "general";
  article.className = `guest-content-card guest-card-${type}`;
  const inventoryItem = cardInventoryItem(card);
  const imageUrl = safeGuestUrl(inventoryItem?.images?.[0], { allowDataImage: true });
  if (imageUrl) {
    article.classList.add("guest-card-has-image");
    const media = document.createElement("div");
    media.className = "guest-card-media";
    const image = document.createElement("img");
    image.src = imageUrl;
    image.alt = card.title ? `${card.title} image` : "Property suggestion image";
    image.loading = "lazy";
    image.decoding = "async";
    image.addEventListener("error", () => {
      media.remove();
      article.classList.remove("guest-card-has-image");
    }, { once: true });
    media.appendChild(image);
    article.appendChild(media);
  }
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
  if (type === "restaurant" && card.restaurant_id) {
    actions.appendChild(guestButton("View menu", () => showRestaurantMenu(card.restaurant_id, card.title)));
    const reservationUrl = inventoryItem?.reservation_available ? safeGuestUrl(inventoryItem.external_reservation_url) : "";
    if (reservationUrl) actions.appendChild(guestButton("Reserve", () => openGuestUrl(reservationUrl), "secondary"));
  }
  if (type === "request" && card.request_id) {
    actions.appendChild(guestButton("Track request", () => setActiveView("requests"), "secondary"));
    if (card.cancellable) actions.appendChild(guestButton("Cancel", () => cancelRequest(card.request_id, card.title), "text"));
  }
  if (type === "recommendation" && safeGuestUrl(card.map_url, { allowExternalHttp: true })) {
    actions.appendChild(guestButton("Directions", () => openGuestUrl(card.map_url)));
  }
  if (type === "event") {
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

function experienceInventory(source) {
  const inventory = state.homeData?.inventory || state.inventory || {};
  if (source === "services") return (state.services || []).filter((item) => item.enabled !== false && !item.archived);
  return Array.isArray(inventory[source]) ? inventory[source] : [];
}

function experienceAction(action) {
  if (!action || typeof action !== "object") return false;
  switch (action.type) {
    case "prompt":
      if (!action.prompt) return false;
      handleGuestInput(action.prompt);
      return true;
    case "internal_page":
      setActiveView(action.page_id);
      return true;
    case "concierge":
      setActiveView("concierge");
      return true;
    case "external_url": {
      const url = safeGuestUrl(action.url, { allowExternalHttp: true });
      if (!url) return false;
      if (action.open_in === "same_tab") window.location.assign(url);
      else window.open(url, "_blank", "noopener,noreferrer");
      return true;
    }
    case "phone":
      window.location.assign(`tel:${action.phone}`);
      return true;
    case "email": {
      const subject = action.subject ? `?subject=${encodeURIComponent(action.subject)}` : "";
      window.location.assign(`mailto:${action.email}${subject}`);
      return true;
    }
    case "map": {
      let url = safeGuestUrl(action.url, { allowExternalHttp: true });
      const location = state.hotel?.location || {};
      if (!url && Number.isFinite(Number(location.latitude)) && Number.isFinite(Number(location.longitude))) {
        url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${location.latitude},${location.longitude}`)}`;
      }
      if (!url) return false;
      window.open(url, "_blank", "noopener,noreferrer");
      return true;
    }
    case "service_request":
    case "room_service":
    case "housekeeping":
    case "transportation": {
      const service = (state.services || []).find((item) => String(item.service_id) === String(action.service_id) && item.enabled !== false && !item.archived);
      if (!service) return false;
      proposeConfiguredService(service);
      return true;
    }
    case "restaurant":
    case "restaurant_menu":
    case "resource":
      if (["restaurant", "restaurant_menu"].includes(action.type) || action.resource_type === "restaurant") {
        const item = experienceInventory("restaurants").find((entry) => String(entry.restaurant_id) === String(action.resource_id || action.restaurant_id));
        if (!item) return false;
        showRestaurantMenu(item.restaurant_id, item.name || "Restaurant");
        return true;
      }
      if (["promotion", "event", "facility"].includes(action.resource_type) || ["promotion", "event"].includes(action.type)) {
        setActiveView("explore");
        return true;
      }
      return false;
    default:
      return false;
  }
}

function experienceActionConfigured(action) {
  if (!action || typeof action !== "object") return false;
  switch (action.type) {
    case "none": return false;
    case "prompt": return Boolean(String(action.prompt || "").trim());
    case "external_url": return Boolean(safeGuestUrl(action.url, { allowExternalHttp: true }));
    case "internal_page": return Boolean((state.hotel?.design?.pages || []).some((page) => page.id === action.page_id && page.enabled !== false) || guestViewIds[action.page_id]);
    case "concierge": return true;
    case "phone": return Boolean(String(action.phone || "").trim());
    case "email": return Boolean(String(action.email || "").trim());
    case "map": {
      const location = state.hotel?.location || {};
      return Boolean(safeGuestUrl(action.url, { allowExternalHttp: true }) || (Number.isFinite(Number(location.latitude)) && Number.isFinite(Number(location.longitude))));
    }
    case "service_request": case "room_service": case "housekeeping": case "transportation":
      return Boolean((state.services || []).some((item) => String(item.service_id) === String(action.service_id) && item.enabled !== false && !item.archived));
    case "restaurant": case "restaurant_menu":
      return Boolean(experienceInventory("restaurants").some((item) => String(item.restaurant_id) === String(action.resource_id || action.restaurant_id)));
    case "resource": {
      const source = ({ restaurant: "restaurants", promotion: "promotions", event: "events", facility: "facilities" })[action.resource_type];
      return Boolean(source && experienceInventory(source).some((item) => String(item.restaurant_id || item.promotion_id || item.event_id || item.facility_id) === String(action.resource_id)));
    }
    case "promotion": return Boolean(experienceInventory("promotions").some((item) => String(item.promotion_id) === String(action.resource_id)));
    case "event": return Boolean(experienceInventory("events").some((item) => String(item.event_id) === String(action.resource_id)));
    default: return false;
  }
}

function createExperienceButton(config) {
  if (!config?.label || !experienceActionConfigured(config.action)) return null;
  const button = document.createElement("button");
  button.type = "button";
  button.className = `experience-button experience-button-${config.style || "primary"} experience-button-${config.size || "medium"}`;
  button.textContent = [config.icon, config.label].filter(Boolean).join(" ");
  button.addEventListener("click", () => experienceAction(config.action));
  return button;
}

function experienceCard(item, source) {
  if (source === "services") {
    if (!item.service_id || !item.name) return null;
    const card = document.createElement("article");
    card.className = "guest-content-card guest-card-general";
    const title = document.createElement("strong");
    title.textContent = item.name;
    card.appendChild(title);
    const description = document.createElement("p");
    description.textContent = item.guest_description || item.description || "";
    if (description.textContent) card.appendChild(description);
    card.appendChild(guestButton("Request", () => proposeConfiguredService(item)));
    return card;
  }
  const typeBySource = {
    restaurants: "restaurant", facilities: "facility", events: "event",
    promotions: "promotion", recommendations: "recommendation",
  };
  const type = typeBySource[source] || "general";
  const title = item.name || item.title || "";
  if (!title) return null;
  const card = createGuestCard({
    type, title, description: item.description || item.address || "",
    subtitle: item.cuisine || item.category || item.facility_type || "",
    restaurant_id: item.restaurant_id, facility_id: item.facility_id,
    event_id: item.event_id, recommendation_id: item.recommendation_id,
    map_url: item.map_url, cta: item.cta || "View details",
  });
  if (item.images?.length && !card.classList.contains("guest-card-has-image")) {
    const imageUrl = safeGuestUrl(item.images[0], { allowDataImage: true });
    if (imageUrl) {
      const image = document.createElement("img");
      image.className = "experience-card-image";
      image.src = imageUrl;
      image.alt = `${title} image`;
      image.loading = "lazy";
      image.decoding = "async";
      image.addEventListener("error", () => image.remove(), { once: true });
      card.prepend(image);
    }
  }
  return card;
}

function attachExperienceAnimation(element, section) {
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const animation = section.animation || {};
  const entrance = motion ? "none" : (animation.entrance || "none");
  const interaction = motion ? "none" : (animation.interaction || "none");
  element.dataset.animation = entrance;
  element.dataset.interaction = interaction;
  element.style.setProperty("--experience-duration", ({ fast: "180ms", normal: "320ms", slow: "520ms" })[animation.duration] || "320ms");
  element.style.setProperty("--experience-delay", `${Math.min(500, Number(animation.delay) || 0)}ms`);
  const device = window.matchMedia("(max-width: 640px)").matches ? "phone" : (window.matchMedia("(max-width: 900px)").matches ? "tablet" : "desktop");
  if (section.responsive?.[device] === false) element.hidden = true;
  if (device === "phone" && (section.responsive?.mobile === "hide" || section.responsive?.mobile_behavior === "hide")) element.hidden = true;
  const columns = Math.max(1, Math.min(4, Number(section.responsive?.columns) || 2));
  element.style.setProperty("--experience-columns", columns);
  if (device === "phone" && (section.responsive?.mobile === "scroll" || section.responsive?.mobile_behavior === "scroll")) element.classList.add("experience-scroll-mobile");
  if (entrance === "none") return;
  const show = () => element.classList.add("experience-visible");
  if (animation.trigger === "page_load" || !("IntersectionObserver" in window)) {
    requestAnimationFrame(show);
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) {
        if (animation.repeat === "each") element.classList.remove("experience-visible");
        continue;
      }
      show();
      if (animation.repeat !== "each") observer.unobserve(element);
    }
  }, { threshold: 0.12 });
  observer.observe(element);
}

function renderExperienceSection(section, design) {
  if (!section || section.enabled === false) return null;
  const type = section.type;
  const supportedTypes = ["hero", "heading", "text", "image", "button", "divider", "spacer", "container", "columns", "quick_actions", "card_grid", "carousel", "restaurant", "room_service", "housekeeping", "transportation", "amenities", "promotions", "events", "banner", "concierge_composer", "ai_suggestion", "header", "bottom_navigation"];
  if (!supportedTypes.includes(type)) return null;
  const p = section.properties || {};
  const outer = document.createElement("section");
  outer.className = `experience-section experience-${type}`;
  outer.dataset.sectionId = section.id;
  if (section.title) outer.setAttribute("aria-label", section.title);

  const addSectionTitle = () => {
    if (!p.title || ["hero", "button", "image", "text", "heading", "spacer", "divider", "concierge_composer"].includes(type)) return;
    const title = document.createElement("h2");
    title.className = "experience-section-title";
    title.textContent = p.title;
    outer.appendChild(title);
  };

  if (type === "hero") {
    outer.classList.add(`experience-hero-${p.height || "large"}`, `experience-align-${p.alignment || "left"}`);
    if (p.background) outer.style.backgroundColor = p.background;
    if (p.text_color) outer.style.color = p.text_color;
    const imageUrl = safeGuestUrl(p.image_url || design.theme?.backgroundImageUrl, { allowDataImage: true });
    if (imageUrl) {
      const image = document.createElement("img");
      image.className = "experience-hero-image";
      image.src = imageUrl;
      image.alt = p.alt || "";
      image.loading = "eager";
      image.decoding = "async";
      image.addEventListener("error", () => { image.remove(); outer.classList.remove("experience-hero-has-image"); }, { once: true });
      outer.classList.add("experience-hero-has-image");
      outer.prepend(image);
    }
    if (p.eyebrow) { const eyebrow = document.createElement("p"); eyebrow.className = "experience-eyebrow"; eyebrow.textContent = p.eyebrow; outer.appendChild(eyebrow); }
    const heading = document.createElement("h1");
    heading.textContent = p.headline || design.welcome?.headline || state.hotel?.name || "";
    if (heading.textContent) outer.appendChild(heading);
    const description = document.createElement("p");
    description.textContent = p.description || design.welcome?.description || "";
    if (description.textContent) outer.appendChild(description);
    for (const buttonConfig of p.buttons || []) {
      const button = createExperienceButton(buttonConfig);
      if (button) outer.appendChild(button);
    }
  } else if (type === "heading") {
    const heading = document.createElement(`h${Math.max(1, Math.min(6, Number(p.level) || 2))}`); heading.textContent = p.text || p.headline || section.title; outer.appendChild(heading);
    outer.classList.add(`experience-align-${p.alignment || "left"}`);
  } else if (type === "text") {
    const text = document.createElement("p"); text.textContent = p.content || p.body || p.description || ""; if (text.textContent) outer.appendChild(text);
    outer.classList.add(`experience-align-${p.alignment || "left"}`);
  } else if (type === "image") {
    const url = safeGuestUrl(p.url, { allowDataImage: true });
    if (!url) return null;
    const image = document.createElement("img"); image.src = url; image.alt = p.alt || ""; image.loading = "lazy"; image.decoding = "async"; image.className = `experience-image experience-image-${p.fit || "cover"}`;
    image.addEventListener("error", () => outer.remove(), { once: true }); outer.appendChild(image);
  } else if (type === "button") {
    const button = createExperienceButton(p); if (button) outer.appendChild(button);
  } else if (type === "divider") {
    outer.setAttribute("role", "separator");
  } else if (type === "spacer") {
    outer.dataset.spacer = p.size || "medium";
  } else if (type === "container") {
    outer.dataset.width = p.width || "contained";
    const copy = document.createElement("p"); copy.textContent = p.content || ""; if (copy.textContent) outer.appendChild(copy);
  } else if (type === "columns") {
    const columns = document.createElement("div"); columns.className = "experience-columns";
    for (const content of [p.primary, p.secondary]) { const column = document.createElement("div"); column.textContent = content || ""; if (column.textContent) columns.appendChild(column); }
    if (columns.childElementCount) outer.appendChild(columns);
  } else if (["header", "bottom_navigation"].includes(type)) {
    if (type === "header") {
      outer.classList.add("experience-configured-header");
      if (p.show_menu !== false) { const menu = document.createElement("button"); menu.type = "button"; menu.className = "experience-configured-menu"; menu.textContent = "Menu"; menu.setAttribute("aria-label", "Open hotel menu"); menu.addEventListener("click", () => p.menu_action && p.menu_action.type !== "none" ? experienceAction(p.menu_action) : $("menu-button")?.click()); outer.appendChild(menu); }
      const identity = document.createElement("div"); identity.className = "experience-configured-identity";
      if (p.show_logo !== false && design.branding?.logoUrl) { const logoUrl = safeGuestUrl(design.branding.logoUrl, { allowDataImage: true }); if (logoUrl) { const logo = document.createElement("img"); logo.className = "experience-configured-logo"; logo.src = logoUrl; logo.alt = `${design.branding.hotelName || state.hotel?.name || "Property"} logo`; identity.appendChild(logo); } }
      const identityCopy = document.createElement("span"); identityCopy.className = "experience-configured-identity-copy";
      if (p.show_hotel_name !== false) { const title = document.createElement("strong"); title.textContent = design.branding?.hotelName || state.hotel?.name || ""; identityCopy.appendChild(title); }
      if (p.show_concierge_label !== false) { const concierge = document.createElement("small"); concierge.textContent = design.branding?.conciergeName || "Concierge"; identityCopy.appendChild(concierge); }
      if (identityCopy.childElementCount) identity.appendChild(identityCopy);
      if (identity.childElementCount) outer.appendChild(identity);
    } else {
      outer.classList.add("experience-configured-navigation");
      outer.setAttribute("role", "navigation");
      outer.setAttribute("aria-label", "Guest navigation");
      const items = (p.items || []).filter((item) => item.enabled !== false && item.label && experienceActionConfigured(item.action));
      if (!items.length) return null;
      outer.style.setProperty("--navigation-count", String(items.length));
      outer.dataset.position = p.position || "fixed"; outer.dataset.height = p.height || "medium"; outer.dataset.iconSize = p.icon_size || "medium"; outer.dataset.safeArea = String(p.safe_area_padding !== false);
      const appearance = section.appearance || {};
      outer.style.setProperty("--experience-active-color", appearance.active_color || design.theme?.accent || "#9b7337");
      outer.style.setProperty("--experience-border-color", appearance.border_color || "#e8e4dc");
      const iconMarks = { home: "⌂", explore: "◇", requests: "✓", stay: "▤", concierge: "○", dining: "♨", restaurant: "♨", spa: "✦", events: "▣", event: "▣", transport: "↗", transportation: "↗", help: "?" };
      for (const item of items) { const button = document.createElement("button"); button.type = "button"; if (item.action?.type === "internal_page") button.dataset.pageId = item.action.page_id; else if (item.action?.type === "concierge") button.dataset.pageId = "concierge"; if (button.dataset.pageId === state.activeView) button.setAttribute("aria-current", "page"); if (item.icon) { const icon = document.createElement("span"); icon.setAttribute("aria-hidden", "true"); const key = String(item.icon).trim().toLowerCase(); icon.textContent = iconMarks[key] || item.icon; button.appendChild(icon); } if (p.show_labels !== false) { const label = document.createElement("small"); label.textContent = item.label; button.appendChild(label); } button.addEventListener("click", () => experienceAction(item.action)); outer.appendChild(button); }
    }
  } else if (type === "quick_actions") {
    addSectionTitle();
    const sourceItems = Array.isArray(p.items) ? p.items : (design.suggestions || []).map((item, index) => ({
      id: `prompt-${index}`, label: item.label, description: item.description, icon: item.icon,
      enabled: item.enabled !== false,
      action: item.action || { type: "prompt", prompt: item.prompt },
    }));
    const items = sourceItems.filter((item) => item.enabled !== false && item.label && experienceActionConfigured(item.action));
    const seenLabels = new Set(items.map((item) => String(item.label).trim().toLocaleLowerCase()));
    for (const route of state.homeData?.quick_actions || []) {
      const label = String(route?.label || "").trim();
      if (!label || !guestViewIds[route.view] || route.view === "home" || seenLabels.has(label.toLocaleLowerCase())) continue;
      seenLabels.add(label.toLocaleLowerCase());
      items.push({ id: `route-${route.view}`, label, description: "", enabled: true, route: route.view });
    }
    const grid = document.createElement("div"); grid.className = "experience-action-grid";
    const visible = state.homeActionsExpanded ? items : items.slice(0, 4);
    for (const item of visible) {
      const actionButton = document.createElement("button"); actionButton.type = "button"; actionButton.className = "experience-action-card";
      if (item.style_mode === "custom") { const appearance = item.appearance || {}; if (appearance.text_color) actionButton.style.color = appearance.text_color; if (appearance.background_color) actionButton.style.backgroundColor = appearance.background_color; if (appearance.border_color) actionButton.style.borderColor = appearance.border_color; if (appearance.radius) actionButton.style.borderRadius = ({ none: "0", small: "4px", medium: "9px", large: "16px", pill: "999px" })[appearance.radius] || ""; if (appearance.shadow) actionButton.style.boxShadow = ({ none: "none", subtle: "0 4px 15px rgba(25,25,25,.06)", raised: "0 12px 28px rgba(25,25,25,.12)" })[appearance.shadow] || ""; }
      if (item.icon) { const icon = document.createElement("span"); icon.className = "experience-action-icon"; icon.textContent = item.icon; actionButton.appendChild(icon); }
      const copy = document.createElement("span"); copy.className = "experience-action-copy";
      const label = document.createElement("strong"); label.textContent = item.label; copy.appendChild(label);
      if (item.description) { const desc = document.createElement("small"); desc.textContent = item.description; copy.appendChild(desc); }
      actionButton.appendChild(copy);
      actionButton.dataset.actionType = item.route ? "route" : "configured";
      actionButton.addEventListener("click", () => item.route ? setActiveView(item.route) : experienceAction(item.action));
      grid.appendChild(actionButton);
    }
    outer.appendChild(grid);
    if (items.length > 4) {
      const toggle = guestButton(state.homeActionsExpanded ? "Show less" : "See all", () => {
        state.homeActionsExpanded = !state.homeActionsExpanded;
        const home = state.hotel?.design?.pages?.find((page) => page.id === "home" && page.enabled !== false);
        if (state.activeView === "home" && home) renderConfiguredExperience(home, $("guest-experience-page"));
        else refreshHome().catch(() => {});
      }, "experience-see-all");
      toggle.setAttribute("aria-expanded", String(state.homeActionsExpanded)); outer.appendChild(toggle);
    }
  } else if (["card_grid", "carousel", "restaurant", "room_service", "housekeeping", "transportation", "amenities", "promotions", "events"].includes(type)) {
    addSectionTitle();
    const source = p.source || ({ restaurant: "restaurants", room_service: "services", housekeeping: "services", transportation: "services", amenities: "facilities", promotions: "promotions", events: "events" })[type] || "recommendations";
    if (type === "card_grid" && Array.isArray(p.items)) {
      const grid = document.createElement("div"); grid.className = "experience-card-grid"; grid.style.setProperty("--experience-columns", Number(section.responsive?.columns) || Number(p.columns) || 2);
      for (const item of p.items.filter((card) => card.enabled !== false && String(card.title || "").trim())) {
        const card = document.createElement("article"); card.className = "guest-content-card guest-card-custom";
        if (item.style_mode === "custom") { const itemStyle = item.appearance || {}; if (itemStyle.text_color) card.style.color = itemStyle.text_color; if (itemStyle.background_color) card.style.backgroundColor = itemStyle.background_color; if (itemStyle.border_color) card.style.borderColor = itemStyle.border_color; if (itemStyle.radius) card.style.borderRadius = ({ none: "0", small: "4px", medium: "9px", large: "16px", pill: "999px" })[itemStyle.radius] || ""; if (itemStyle.shadow) card.style.boxShadow = ({ none: "none", subtle: "0 4px 15px rgba(25,25,25,.06)", raised: "0 12px 28px rgba(25,25,25,.12)" })[itemStyle.shadow] || ""; }
        const imageUrl = safeGuestUrl(item.image_url, { allowDataImage: true });
        if (imageUrl) { const image = document.createElement("img"); image.className = "experience-card-image"; image.src = imageUrl; image.alt = item.title || ""; image.loading = "lazy"; card.appendChild(image); }
        const content = document.createElement("div");
        if (item.badge) { const badge = document.createElement("small"); badge.className = "experience-card-badge"; badge.textContent = item.badge; content.appendChild(badge); }
        if (item.icon) { const icon = document.createElement("span"); icon.className = "experience-action-icon"; icon.textContent = item.icon; content.appendChild(icon); }
        const title = document.createElement("strong"); title.textContent = item.title; content.appendChild(title);
        if (item.description) { const description = document.createElement("p"); description.textContent = item.description; content.appendChild(description); }
        if (item.cta && experienceActionConfigured(item.action)) { const cta = guestButton(item.cta, () => experienceAction(item.action)); content.appendChild(cta); }
        else if (experienceActionConfigured(item.action)) { card.tabIndex = 0; card.setAttribute("role", "link"); card.setAttribute("aria-label", `${item.title} action`); card.addEventListener("click", () => experienceAction(item.action)); card.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); experienceAction(item.action); } }); }
        card.appendChild(content); grid.appendChild(card);
      }
      if (!grid.childElementCount) return null;
      outer.appendChild(grid);
      // Custom cards are schema-owned, so the property inventory is not also rendered.
      const appearance = section.appearance || {};
      if (appearance.text_color) outer.style.color = appearance.text_color;
      if (appearance.background_color) outer.style.backgroundColor = appearance.background_color;
      if (appearance.active_color) outer.style.setProperty("--experience-active-color", appearance.active_color);
      if (appearance.border_color) outer.style.setProperty("--experience-border-color", appearance.border_color);
      if (appearance.radius) outer.style.borderRadius = ({ none: "0", small: "4px", medium: "9px", large: "16px", pill: "999px" })[appearance.radius] || "";
      if (appearance.shadow) outer.style.boxShadow = ({ none: "none", subtle: "0 4px 15px rgba(25,25,25,.06)", raised: "0 12px 28px rgba(25,25,25,.12)" })[appearance.shadow] || "";
      attachExperienceAnimation(outer, section);
      return outer;
    }
    let items = experienceInventory(source);
    if (p.resource_id) items = items.filter((item) => [item.restaurant_id, item.facility_id, item.promotion_id, item.event_id, item.recommendation_id].some((id) => String(id) === String(p.resource_id)));
    items = items.slice(0, Number(p.limit) || 4);
    if (!items.length) return null;
    const grid = document.createElement("div"); grid.className = `experience-card-grid${type === "carousel" ? " experience-carousel" : ""}`;
    grid.style.setProperty("--experience-columns", Number(p.columns) || Number(section.responsive?.columns) || 2);
    for (const item of items) { const card = experienceCard(item, source); if (card) grid.appendChild(card); }
    if (!grid.childElementCount) return null;
    outer.appendChild(grid);
  } else if (type === "banner") {
    const imageUrl = safeGuestUrl(p.image_url, { allowDataImage: true });
    if (imageUrl) { const image = document.createElement("img"); image.src = imageUrl; image.alt = p.alt || ""; image.loading = "lazy"; image.decoding = "async"; image.className = "experience-banner-image"; image.addEventListener("error", () => image.remove(), { once: true }); outer.appendChild(image); }
    const heading = document.createElement("h2"); heading.textContent = p.headline || p.title || section.title; if (heading.textContent) outer.appendChild(heading);
    const desc = document.createElement("p"); desc.textContent = p.description || ""; if (desc.textContent) outer.appendChild(desc);
    if (p.action) { const button = createExperienceButton(p.action); if (button) outer.appendChild(button); }
    if (!heading.textContent && !desc.textContent && !imageUrl) return null;
  } else if (type === "concierge_composer") {
    if (p.enabled === false) return null;
    return null;
  } else if (type === "ai_suggestion") {
    const heading = document.createElement("h2"); heading.textContent = p.title || ""; if (heading.textContent) outer.appendChild(heading);
    const content = document.createElement("p"); content.textContent = p.content || ""; if (content.textContent) outer.appendChild(content);
  }

  if (!outer.childElementCount && !["divider", "spacer", "container"].includes(type)) return null;
  const appearance = section.appearance || {};
  if (appearance.text_color) outer.style.color = appearance.text_color;
  if (appearance.background_color) outer.style.backgroundColor = appearance.background_color;
  if (appearance.radius) outer.style.borderRadius = ({ none: "0", small: "4px", medium: "9px", large: "16px", pill: "999px" })[appearance.radius] || "";
  if (appearance.shadow) outer.style.boxShadow = ({ none: "none", subtle: "0 4px 15px rgba(25,25,25,.06)", raised: "0 12px 28px rgba(25,25,25,.12)" })[appearance.shadow] || "";
  if (appearance.overlay_color && ["hero", "banner"].includes(type)) outer.style.setProperty("--experience-overlay", `${appearance.overlay_color}${Math.round((appearance.overlay_opacity ?? 30) * 2.55).toString(16).padStart(2, "0")}`);
  if (section.layout?.width && type === "container") outer.dataset.width = section.layout.width;
  if (section.layout?.height && ["hero", "banner"].includes(type)) outer.classList.add(`experience-${type}-${section.layout.height}`);
  if (section.layout?.spacing) outer.dataset.spacing = section.layout.spacing;
  if (section.layout?.alignment && ["hero", "heading", "text", "container"].includes(type)) outer.classList.add(`experience-align-${section.layout.alignment}`);
  attachExperienceAnimation(outer, section);
  return outer;
}

function renderConfiguredExperience(page, target) {
  if (!page || !target) return;
  const design = state.hotel?.design || {};
  const sections = [...(page.sections || [])].sort((a, b) => Number(a.order || 0) - Number(b.order || 0));
  const hasHeader = sections.some((section) => section.enabled !== false && section.type === "header");
  const hasNavigation = sections.some((section) => section.enabled !== false && section.type === "bottom_navigation");
  const schemaOwnsHeader = Number(page.version || 1) >= 2 || hasHeader;
  const globalHeader = document.querySelector(".concierge-header");
  if (globalHeader) globalHeader.hidden = schemaOwnsHeader;
  document.body.classList.toggle("header-hidden", schemaOwnsHeader || state.hotel?.design?.header?.enabled === false);
  const globalNavigation = $("guest-bottom-nav");
  if (globalNavigation) globalNavigation.hidden = Number(page.version || 1) >= 2 || hasNavigation;
  const navigationSlot = $("guest-configured-navigation-slot");
  const fixedNavigationSection = sections.find((section) => section.type === "bottom_navigation" && section.enabled !== false && section.properties?.position !== "inline");
  if (navigationSlot && (page.id === "home" || fixedNavigationSection)) {
    navigationSlot.replaceChildren();
    navigationSlot.hidden = true;
    if (fixedNavigationSection) {
      const navigation = renderExperienceSection(fixedNavigationSection, state.hotel?.design || {});
      if (navigation) { navigationSlot.appendChild(navigation); navigationSlot.hidden = false; }
    }
  }
  const activeFixedNavigation = navigationSlot?.querySelector(".experience-configured-navigation") || null;
  const composerSection = sections.find((section) => section.type === "concierge_composer");
  const pageHasBuilderSections = Array.isArray(page.sections) && page.sections.length > 0;
  const composerEnabled = design.composer?.enabled !== false && (composerSection
    ? composerSection.enabled !== false && composerSection.properties?.enabled !== false
    : !pageHasBuilderSections);
  const composerRegion = $("composer-region");
  composerRegion?.classList.toggle("has-fixed-navigation", Boolean(activeFixedNavigation) && composerEnabled);
  document.body.classList.toggle("has-configured-fixed-navigation", Boolean(activeFixedNavigation));
  document.body.classList.toggle("has-fixed-navigation-composer", Boolean(activeFixedNavigation) && composerEnabled);
  state.fixedNavigationResizeObserver?.disconnect();
  if (activeFixedNavigation) {
    const updateFixedNavigationSpacing = () => {
      const navigationHeight = Math.ceil(activeFixedNavigation.getBoundingClientRect().height);
      const composerHeight = composerEnabled ? Math.ceil(composerRegion?.getBoundingClientRect().height || 0) : 0;
      document.body.style.setProperty("--experience-navigation-height", `${navigationHeight}px`);
      document.body.style.setProperty("--experience-footer-clearance", `${navigationHeight + composerHeight + 12}px`);
    };
    updateFixedNavigationSpacing();
    if ("ResizeObserver" in window) {
      state.fixedNavigationResizeObserver = new ResizeObserver(updateFixedNavigationSpacing);
      state.fixedNavigationResizeObserver.observe(activeFixedNavigation);
      if (composerEnabled && composerRegion) state.fixedNavigationResizeObserver.observe(composerRegion);
    }
  }
  target.replaceChildren();
  target.dataset.pageId = page.id;
  target.style.paddingBottom = "";
  for (const section of sections) {
    if (section.type === "bottom_navigation" && section.properties?.position !== "inline") {
      continue;
    }
    const element = renderExperienceSection(section, state.hotel?.design || {});
    if (element && !element.hidden) {
      target.appendChild(element);
    }
  }
  const empty = target.childElementCount === 0;
  target.hidden = empty;
}

function renderGuestNavigation(design) {
  const nav = $("guest-bottom-nav");
  if (!nav) return;
  const pages = design.pages || [];
  const pageNames = new Map(pages.filter((page) => page.enabled !== false).map((page) => [page.id, page]));
  const items = (design.navigation || []).filter((item) => item.enabled !== false && pageNames.has(item.page_id));
  const homePage = pages.find((page) => page.id === "home" && page.enabled !== false);
  const schemaOwnsNavigation = Boolean(homePage && (
    Number(homePage.version || 1) >= 2
    || (homePage.sections || []).some((section) => section.enabled !== false && section.type === "bottom_navigation")
  ));
  const iconMarks = { home: "⌂", explore: "◇", requests: "✓", stay: "▤", concierge: "○" };
  nav.replaceChildren();
  nav.hidden = schemaOwnsNavigation || items.length === 0;
  nav.style.setProperty("--navigation-count", Math.max(1, items.length));
  for (const item of items) {
    const button = document.createElement("button"); button.type = "button"; button.dataset.view = item.page_id;
    const icon = document.createElement("span"); icon.setAttribute("aria-hidden", "true");
    const iconKey = ["home", "explore", "requests", "stay", "concierge"].includes(item.icon) ? item.icon : item.page_id;
    icon.textContent = iconMarks[iconKey] || item.icon || item.label.slice(0, 1).toUpperCase();
    const label = document.createElement("small"); label.textContent = item.label || pageNames.get(item.page_id)?.name || "Page";
    button.append(icon, label); nav.appendChild(button);
  }
}

function renderHome(data) {
  const design = state.hotel?.design || {};
  const homePage = (design.pages || []).find((page) => page.id === "home" && page.enabled !== false);
  if (homePage) {
    state.inventory = data.inventory || state.inventory;
    $("legacy-home-content").hidden = true;
    $("home-view").setAttribute("aria-label", homePage.name || "Home");
    renderConfiguredExperience(homePage, $("guest-experience-page"));
    renderComposerForPage(homePage, $("guest-experience-page"), design);
    renderGuestNavigation(design);
    if (state.activeView !== "home") {
      const page = (design.pages || []).find((item) => item.id === state.activeView && item.enabled !== false);
      if (page && (page.id.startsWith("page-") || page.sections?.length)) {
        renderConfiguredExperience(page, $("custom-experience-page"));
        renderComposerForPage(page, $("custom-experience-page"), design);
      }
    }
    return;
  }
  $("legacy-home-content").hidden = false;
  const firstName = String(data.preferred_name || "").trim().split(/\s+/)[0];
  const name = firstName ? `, ${firstName}` : "";
  const designWelcome = state.hotel?.design?.welcome || {};
  const greeting = String(designWelcome.greeting || data.greeting || "Welcome").trim().replace(/[.,!]+$/, "");
  setText("home-greeting", greeting + name);
  setText("home-name", designWelcome.headline || "How can I help with your stay today?");
  setText("home-description", designWelcome.description || "Your personal concierge is here to make your stay more comfortable.");
  const stayPhase = $("home-stay-phase");
  const phaseLabels = { checked_in: "Stay in progress", unverified: "Guest services", checked_out: "Thank you for staying with us" };
  const phase = phaseLabels[data.stay?.status] || "";
  stayPhase.textContent = phase;
  stayPhase.hidden = !phase;
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
  const visibleCards = state.homeSuggestionsExpanded ? cards : cards.slice(0, 2);
  $("home-cards-section").hidden = visibleCards.length === 0;
  const suggestionsToggle = $("home-suggestions-more");
  suggestionsToggle.hidden = cards.length <= 2;
  suggestionsToggle.setAttribute("aria-expanded", String(state.homeSuggestionsExpanded));
  suggestionsToggle.replaceChildren(document.createTextNode(state.homeSuggestionsExpanded ? "Show less" : "See all"));
  if (!state.homeSuggestionsExpanded && cards.length > 2) {
    const arrow = document.createElement("span");
    arrow.setAttribute("aria-hidden", "true");
    arrow.textContent = " ›";
    suggestionsToggle.appendChild(arrow);
  }
  $("home-cards").replaceChildren(...visibleCards.map(createGuestCard));
  const quickActions = $("quick-actions");
  quickActions.replaceChildren();
  const hasConfiguredSuggestions = Array.isArray(state.hotel?.design?.suggestions);
  const configured = (hasConfiguredSuggestions ? state.hotel.design.suggestions : [])
    .filter((item) => item.enabled !== false && item.label && item.prompt)
    .sort((a, b) => Number(a.order || 0) - Number(b.order || 0))
    .map((item) => ({ label: item.label, prompt: item.prompt, description: item.description || "" }));
  const promptActions = hasConfiguredSuggestions
    ? configured
    : (Array.isArray(data.suggested_prompts) ? data.suggested_prompts : []).map((prompt) => ({ label: prompt, prompt }));
  const actions = promptActions.map((action) => ({ ...action, actionType: "prompt" }));
  const routeActions = Array.isArray(data.quick_actions) ? data.quick_actions : [];
  const seenLabels = new Set(actions.map((action) => String(action.label || "").trim().toLocaleLowerCase()));
  for (const action of routeActions) {
    const label = String(action?.label || "").trim();
    if (!label || !guestViewIds[action.view] || action.view === "home" || seenLabels.has(label.toLocaleLowerCase())) continue;
    seenLabels.add(label.toLocaleLowerCase());
    actions.push({ label, view: action.view, actionType: "route" });
  }
  $("home-actions-section").hidden = actions.length === 0;
  const actionToggle = $("home-actions-toggle");
  actionToggle.hidden = actions.length <= 4;
  actionToggle.setAttribute("aria-expanded", String(state.homeActionsExpanded));
  actionToggle.replaceChildren(document.createTextNode(state.homeActionsExpanded ? "Show less" : "See all"));
  if (!state.homeActionsExpanded && actions.length > 4) {
    const arrow = document.createElement("span");
    arrow.setAttribute("aria-hidden", "true");
    arrow.textContent = " ›";
    actionToggle.appendChild(arrow);
  }
  const visibleActions = state.homeActionsExpanded ? actions : actions.slice(0, 4);
  for (const [index, action] of visibleActions.entries()) {
    const activate = action.actionType === "route"
      ? () => setActiveView(action.view)
      : () => handleGuestInput(action.prompt);
    const button = guestButton(action.label, activate, "quick-action");
    button.dataset.actionType = action.actionType;
    button.dataset.kind = suggestionKind(action.prompt || action.label, index);
    const icon = document.createElement("span");
    icon.className = "quick-action-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.innerHTML = suggestionIcon(button.dataset.kind);
    const label = document.createElement("span");
    label.className = "quick-action-label";
    label.textContent = action.label;
    const copy = document.createElement("span");
    copy.className = "quick-action-copy";
    const description = document.createElement("small");
    const copyByKind = {
      dining: "Restaurants, menus and reservations",
      wifi: "Get connected during your stay",
      wellness: "Explore hotel facilities",
      stay: "Guest services and stay details",
      concierge: "Ask about your stay",
      room_service: "Request available in-room services",
      housekeeping: "Request available housekeeping services",
      transportation: "Explore configured transport options",
    };
    const routeCopy = { explore: "Browse property dining and facilities", requests: "Request and track hotel services", stay: "See details for your stay", concierge: "Continue with your concierge" };
    description.textContent = action.description || (action.actionType === "route" && routeCopy[action.view]) || copyByKind[button.dataset.kind] || "Ask your concierge";
    copy.append(label, description);
    const arrow = document.createElement("span");
    arrow.className = "quick-action-arrow";
    arrow.setAttribute("aria-hidden", "true");
    arrow.textContent = "›";
    button.replaceChildren(icon, copy, arrow);
    quickActions.appendChild(button);
  }
  if (data.inventory) state.inventory = data.inventory;
  renderComposerShortcuts(data.quick_actions || []);
  if (state.activeView === "stay") renderStay();
}

function renderComposerShortcuts(configuredActions = []) {
  const sheet = $("composer-action-sheet");
  const toggle = $("composer-actions-toggle");
  if (!sheet || !toggle) return;
  const actions = [
    { label: "Explore", view: "explore" },
    { label: "Requests", view: "requests" },
    ...configuredActions.filter((action) => guestViewIds[action.view] && action.view !== "explore"),
    { label: "My Stay", view: "stay" },
    { label: "Concierge", view: "concierge" },
  ];
  const seen = new Set();
  sheet.replaceChildren();
  for (const action of actions) {
    if (!guestViewIds[action.view] || seen.has(action.view)) continue;
    seen.add(action.view);
    const button = guestButton(action.label, () => {
      closeComposerShortcuts();
      setActiveView(action.view);
    }, "composer-shortcut");
    sheet.appendChild(button);
  }
}

function closeComposerShortcuts() {
  const sheet = $("composer-action-sheet");
  const toggle = $("composer-actions-toggle");
  if (!sheet || !toggle) return;
  sheet.hidden = true;
  toggle.setAttribute("aria-expanded", "false");
  toggle.setAttribute("aria-label", "Open concierge shortcuts");
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
  const data = await jsonFetch("/api/guest/requests");
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
    await ensureStarted();
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
  if (prompt.includes("transport") || prompt.includes("airport transfer") || prompt.includes("car service")) return "transportation";
  if (prompt.includes("housekeeping") || prompt.includes("cleaning") || prompt.includes("towel")) return "housekeeping";
  if (prompt.includes("room service") || prompt.includes("in-room dining")) return "room_service";
  if (prompt.includes("breakfast") || prompt.includes("eat") || prompt.includes("restaurant") || prompt.includes("dining")) return "dining";
  if (prompt.includes("wi-fi") || prompt.includes("wifi") || prompt.includes("internet")) return "wifi";
  if (prompt.includes("pool") || prompt.includes("spa") || prompt.includes("gym")) return "wellness";
  if (prompt.includes("checkout") || prompt.includes("check-out") || prompt.includes("room") || prompt.includes("stay") || prompt.includes("service") || prompt.includes("request")) return "stay";
  if (prompt.includes("explore")) return "concierge";
  return ["concierge", "dining", "wellness", "stay"][index % 4];
}

function suggestionIcon(kind) {
  const icons = {
    dining: '<svg viewBox="0 0 24 24"><path d="M7 3v8M4.5 3v5.5A2.5 2.5 0 0 0 7 11v10M9.5 3v5.5A2.5 2.5 0 0 1 7 11M17 3c-2 2.2-2.5 5.8-1.1 8.3.4.7 1.1 1.1 1.9 1.1H19V21"/></svg>',
    wifi: '<svg viewBox="0 0 24 24"><path d="M3.5 8.8a13 13 0 0 1 17 0M6.5 12.2a8.5 8.5 0 0 1 11 0M9.6 15.6a3.8 3.8 0 0 1 4.8 0"/><circle cx="12" cy="19" r="1"/></svg>',
    wellness: '<svg viewBox="0 0 24 24"><path d="M3 15.5c1.5-1.3 3-1.3 4.5 0s3 1.3 4.5 0 3-1.3 4.5 0 3 1.3 4.5 0M3 19c1.5-1.3 3-1.3 4.5 0s3 1.3 4.5 0 3-1.3 4.5 0 3 1.3 4.5 0"/><path d="M5 12h14l-1.2-5H6.2L5 12Z"/></svg>',
    stay: '<svg viewBox="0 0 24 24"><path d="M4 20V7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v13M8 9h3v3H8zM15.5 10.5h.01M8 16h8"/></svg>',
    concierge: '<svg viewBox="0 0 24 24"><path d="M4 18h16M6 18a6 6 0 0 1 12 0M12 8V5M10 5h4"/><path d="M8.5 13.5c1.8-1.4 5.2-1.4 7 0"/></svg>',
    room_service: '<svg viewBox="0 0 24 24"><path d="M3.5 18h17M5.5 18a6.5 6.5 0 0 1 13 0M12 7.5v-3M10.5 4.5h3M7 12.5h.01M17 12.5h.01"/><path d="M8 7.5c1.1-.8 2.4-1.2 4-1.2s2.9.4 4 1.2"/></svg>',
    housekeeping: '<svg viewBox="0 0 24 24"><path d="m14.5 4-8 8M13 5.5l2.5 2.5M6 12l3 3M4 17l3-3 3 3-3 3-3-3ZM15.5 12.5l4.5 4.5M18 10l2 2M14 15l-2 2"/></svg>',
    transportation: '<svg viewBox="0 0 24 24"><path d="m5 11 1.5-5h11L19 11v8h-2v-2H7v2H5v-8ZM5 11h14M8 14h.01M16 14h.01M8 19v2M16 19v2"/><circle cx="8" cy="14" r="1"/><circle cx="16" cy="14" r="1"/></svg>',
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

function placeComposerRegion() {
  const region = $("composer-region");
  if (!region) return;
  if (state.activeView === "concierge") {
    const conversation = $("concierge-card");
    if (conversation && region.parentElement !== conversation) conversation.appendChild(region);
    return;
  }
  const homeConversation = $("home-conversation");
  if (state.activeView === "home" && homeConversation && !homeConversation.hidden) {
    const conversation = homeConversation;
    if (conversation && region.parentElement !== conversation) conversation.appendChild(region);
    return;
  }
  const shell = $("concierge-shell");
  const navigation = $("guest-bottom-nav");
  if (shell && region.parentElement !== shell) shell.insertBefore(region, navigation || null);
}

function renderMessages() {
  const isConversation = state.activeView === "concierge";
  const isHome = state.activeView === "home";
  $("welcome-state").classList.toggle("hidden", state.messages.length > 0);
  const list = $("message-list");
  const homeList = $("home-message-list");
  list.replaceChildren();
  homeList.replaceChildren();
  const destination = isHome ? homeList : isConversation ? list : null;
  $("home-conversation").hidden = !isHome || state.messages.length === 0;
  placeComposerRegion();
  if (destination) {
    for (const message of state.messages) destination.appendChild(renderMessage(message));
  }
  requestAnimationFrame(() => {
    const region = isConversation ? document.querySelector(".conversation-region") : null;
    if (region && !region.hidden) {
      const nearBottom = region.scrollHeight - region.scrollTop - region.clientHeight < 160;
      if (nearBottom || state.messages.length <= 2) {
      region.scrollTop = region.scrollHeight;
      }
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
  const keepHome = state.activeView === "home";
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

    if (await sendChat(message, conversationHistory, false, keepHome)) clearSubmittedComposer(message);
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

async function sendChat(message, conversationHistory = [], focusComposer = true, keepHome = false) {
  if (!keepHome) setActiveView("concierge", focusComposer);
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
      jsonFetch("/api/guest/personalization")
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
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
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
    if (!input.value.trim() || state.inputPending) return;
    handleGuestInput(input.value);
    if (isIOS) input.blur();
  });
  const shortcutsToggle = $("composer-actions-toggle");
  shortcutsToggle.addEventListener("click", () => {
    const sheet = $("composer-action-sheet");
    const open = sheet.hidden;
    sheet.hidden = !open;
    shortcutsToggle.setAttribute("aria-expanded", String(open));
    shortcutsToggle.setAttribute("aria-label", open ? "Close concierge shortcuts" : "Open concierge shortcuts");
    if (open) sheet.querySelector("button")?.focus();
  });
  document.addEventListener("pointerdown", (event) => {
    if (!$("composer-action-sheet").hidden && !$("composer-stack").contains(event.target)) closeComposerShortcuts();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("composer-action-sheet").hidden) {
      closeComposerShortcuts();
      shortcutsToggle.focus();
    }
  });
  setupVoiceInput();
}

function setupVoiceInput() {
  const button = $("composer-voice-button");
  const status = $("composer-status");
  const SpeechRecognitionApi = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognitionApi || !window.isSecureContext) {
    button.hidden = true;
    return;
  }
  button.hidden = false;
  let recognition = null;
  const announce = (message, hideAfter = 0) => {
    status.textContent = message;
    status.hidden = !message;
    window.clearTimeout(announce.timer);
    if (hideAfter) announce.timer = window.setTimeout(() => { status.hidden = true; }, hideAfter);
  };
  button.addEventListener("click", () => {
    if (recognition) {
      recognition.stop();
      return;
    }
    try {
      recognition = new SpeechRecognitionApi();
      recognition.lang = document.documentElement.lang || navigator.language || "en-US";
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;
      recognition.addEventListener("start", () => {
        button.setAttribute("aria-pressed", "true");
        button.setAttribute("aria-label", "Stop voice input");
        announce("Listening. Speak now.");
      });
      recognition.addEventListener("result", (event) => {
        const transcript = String(event.results?.[0]?.[0]?.transcript || "").trim();
        if (!transcript) return;
        const prefix = input.value.trim() ? `${input.value.trim()} ` : "";
        setDraft(`${prefix}${transcript}`);
        announce("Voice input added.", 2200);
      });
      recognition.addEventListener("error", (event) => {
        const message = event.error === "not-allowed" || event.error === "service-not-allowed"
          ? "Microphone access is blocked. Check your browser permissions."
          : event.error === "no-speech" ? "No speech was detected. Try again."
            : "Voice input is unavailable right now.";
        announce(message, 3200);
      });
      recognition.addEventListener("end", () => {
        recognition = null;
        button.setAttribute("aria-pressed", "false");
        button.setAttribute("aria-label", "Start voice input");
        if (status.textContent === "Listening. Speak now.") announce("Voice input ended.", 1800);
      });
      recognition.start();
    } catch {
      recognition = null;
      button.setAttribute("aria-pressed", "false");
      announce("Voice input could not start. Check your browser permissions.", 3200);
    }
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
  const data = await jsonFetch("/api/guest/personalization");
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
  const data = await jsonFetch(`/api/guest/personalization/preferences/${encodeURIComponent(key)}`, { method: "DELETE" });
  renderPersonalization(data);
  await refreshHome().catch(() => {});
  showToast("Preference removed.");
}

async function clearMemoryPreferences() {
  const data = await jsonFetch("/api/guest/personalization/preferences", { method: "DELETE" });
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
      const memory = await jsonFetch("/api/guest/personalization");
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
  const displayHotelName = branding.hotelName || hotelName;
  const conciergeName = profile.concierge_name || "AI concierge";
  setText("hotel-name", displayHotelName);
  setText("concierge-name", branding.conciergeName || conciergeName);
  const initial = $("hotel-initial");
  const logo = $("hotel-logo");
  const logoUrl = safeGuestUrl(branding.logoUrl || profile.logo_url, { allowDataImage: true });
  initial.textContent = Array.from(displayHotelName.trim())[0]?.toLocaleUpperCase() || "H";
  logo.hidden = !logoUrl;
  logo.onload = () => { initial.hidden = true; };
  logo.onerror = () => {
    logo.hidden = true;
    logo.removeAttribute("src");
    initial.hidden = false;
  };
  if (logoUrl) logo.src = logoUrl;
  else { logo.removeAttribute("src"); initial.hidden = false; }
  $("hotel-mark").classList.toggle("has-image", Boolean(logoUrl));
  setText("welcome-greeting", welcome.greeting || "Good evening.");
  setText("welcome-headline", welcome.headline || "How can I help?");
  const heroUrl = safeGuestUrl(design.theme?.backgroundImageUrl, { allowDataImage: true });
  const heroMedia = $("home-hero-media");
  const heroImage = $("home-hero-image");
  heroImage.onload = () => { heroMedia.hidden = false; $("home-hero").classList.add("has-hero-image"); };
  heroImage.onerror = () => { heroMedia.hidden = true; $("home-hero").classList.remove("has-hero-image"); heroImage.removeAttribute("src"); };
  if (heroUrl) { heroMedia.hidden = false; heroImage.src = heroUrl; }
  else { heroImage.removeAttribute("src"); heroMedia.hidden = true; $("home-hero").classList.remove("has-hero-image"); }
  renderComposerShortcuts(state.homeData?.quick_actions || []);
  $("composer-input").placeholder = composer.placeholder || "Ask a question...";
  applyDesignTokens(design);
  renderGuestNavigation(design);
  const headerSection = (design.pages || []).flatMap((page) => page.sections || []).find((section) => section.type === "header");
  document.body.classList.toggle("header-hidden", design.header?.enabled === false || headerSection?.properties?.enabled === false);
  renderConfiguredModules(profile.guest_modules || []);
  const maintenance = $("maintenance-banner");
  const application = profile.application || {};
  maintenance.hidden = !application.maintenance_enabled;
  maintenance.textContent = application.maintenance_message || "Concierge maintenance is in progress. Some requests may take longer than usual.";
  renderWelcomeState();
}

function renderComposerForPage(page, target, design) {
  const region = $("composer-region");
  const stack = region.querySelector(".composer-stack");
  const status = $("composer-status");
  const note = $("composer-note");
  const block = (page.sections || []).find((section) => section.type === "concierge_composer");
  const rootEnabled = design.composer?.enabled !== false;
  const props = block?.properties || {};
  const hasBuilderSections = Array.isArray(page.sections) && page.sections.length > 0;
  const enabled = rootEnabled && (block ? block.enabled !== false && props.enabled !== false : !hasBuilderSections);
  region.dataset.position = "sticky_bottom";
  const placeholder = props.placeholder || design.composer?.placeholder || "Ask your concierge...";
  $("composer-input").placeholder = placeholder;
  $("composer-input").hidden = !enabled;
  $("send-button").hidden = !enabled;
  $("composer-actions-toggle").hidden = !enabled || design.composer?.attachments !== true;
  $("composer-voice-button").hidden = !enabled || design.composer?.voice !== true;
  stack.hidden = !enabled;
  status.hidden = !enabled || status.textContent.trim() === "";
  note.hidden = !enabled;
  region.hidden = !enabled;
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
  root.style.setProperty("--background", theme.background || "#faf8f4");
  const backgroundImageUrl = safeGuestUrl(theme.backgroundImageUrl, { allowDataImage: true });
  const cssBackgroundImage = backgroundImageUrl
    ? `url("${backgroundImageUrl.replaceAll("\\", "%5C").replaceAll('"', "%22").replaceAll(")", "%29")}")`
    : "none";
  root.style.setProperty("--background-image", cssBackgroundImage);
  root.style.setProperty("--background-overlay", (theme.backgroundOverlay || 0) / 100);
  root.style.setProperty("--surface", theme.surface || "#ffffff");
  root.style.setProperty("--surface-elevated", composer.background || theme.composerBackground || "#ffffff");
  root.style.setProperty("--text-primary", theme.textPrimary || "#1c1c1c");
  root.style.setProperty("--text-secondary", theme.textSecondary || "#6e6a64");
  root.style.setProperty("--accent", theme.accent || "#b38a4a");
  root.style.setProperty("--button-color", theme.buttonColor || theme.accent || "#b38a4a");
  root.style.setProperty("--accent-text", theme.accentText || "#1c1c1c");
  root.style.setProperty("--border", theme.border || "#e8e3da");
  root.style.setProperty("--user-message-bg", theme.userMessageBackground || "#f0ede7");
  root.style.setProperty("--user-message-text", theme.userMessageText || "#1c1c1c");
  root.style.setProperty("--assistant-text", theme.assistantText || theme.textPrimary || "#1c1c1c");
  root.style.setProperty("--column-width", (layout.contentWidth || 840) + "px");
  root.style.setProperty("--composer-max", (layout.composerWidth || 720) + "px");
  root.style.setProperty("--message-width", (layout.messageWidth || 680) + "px");
  root.style.setProperty("--message-spacing", (messages.messageSpacing || layout.messageSpacing || 24) + "px");
  root.style.setProperty("--message-radius", (messages.radius || theme.radius || 18) + "px");
  root.style.setProperty("--composer-radius", (composer.radius || 24) + "px");
  root.style.setProperty("--base-font-size", (typography.baseFontSize || 15) + "px");
  root.style.setProperty("--heading-weight", typography.headingWeight || 600);
  root.style.setProperty("--body-weight", typography.bodyWeight || 400);
  root.style.setProperty("--letter-spacing", (typography.letterSpacing || 0) + "em");
  root.style.setProperty("--font-family", fontStack(typography.fontFamily || theme.font || "Geist"));
  root.style.setProperty("--guest-radius", `${theme.radius ?? 14}px`);
  root.style.setProperty("--guest-card-radius", `${design.card?.radius ?? theme.radius ?? 14}px`);
  root.style.setProperty("--guest-shadow", design.card?.shadow === "none" ? "none" : design.card?.shadow === "strong" ? "0 14px 38px rgba(25, 25, 25, .14)" : "0 7px 24px rgba(25, 25, 25, .07)");
  root.style.setProperty("--guest-density", theme.density === "compact" ? ".78" : "1");

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
  document.body.appendChild($("hotel-menu"));
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
    jsonFetch("/api/guest/service-catalog").catch(() => ({ services: [] })),
    jsonFetch("/api/guest/recommendations").catch(() => ({ recommendations: [] })),
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
  const currentPath = window.location.pathname.replace(/\/$/, "") || "/";
  const directPage = (profile.design?.pages || []).find((page) => page.slug === currentPath && page.enabled !== false);
  if (directPage && directPage.id !== "home") setActiveView(directPage.id, false);
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
        headers: { "X-Concierge-Session": previousSessionId },
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
    const memory = await jsonFetch("/api/guest/personalization");
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
