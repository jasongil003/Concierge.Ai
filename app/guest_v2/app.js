(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const storageKeys = {
    client: "concierge-client-id",
    session: "concierge-v2-session-id",
    property: "concierge-v2-property-id",
    messages: (sessionId) => `concierge-v2-messages-${sessionId}`,
  };
  const pendingActions = new Set();
  const invalidActions = new Set();
  let property = null;
  let sessionId = null;
  let clientId = null;
  let messages = [];
  let inputPending = false;
  let activeController = null;

  function newId() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    return `m-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  }

  function setError(message) {
    $("app-shell").hidden = true;
    $("startup-error").hidden = false;
    $("startup-error-copy").textContent = message;
  }

  function readError(detail) {
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((item) => item.msg || item.message || "").filter(Boolean).join(" ");
    return detail?.msg || detail?.message || "Request failed. Please try again.";
  }

  async function api(url, options = {}) {
    const { headers = {}, ...fetchOptions } = options;
    const sessionHeader = sessionId ? { "X-Concierge-Session": sessionId } : {};
    let response;
    try {
      response = await fetch(url, {
        ...fetchOptions,
        headers: { "Content-Type": "application/json", ...sessionHeader, ...headers },
      });
    } catch {
      const error = new Error("The network connection was interrupted. Check your connection and try again.");
      error.networkFailure = true;
      throw error;
    }
    let data = {};
    try { data = await response.json(); } catch { /* Use the bounded message below. */ }
    if (!response.ok) {
      const error = new Error(readError(data.detail));
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function requestBody(url, data) {
    return api(url, { method: "POST", body: JSON.stringify(data) });
  }

  async function streamGuestChat(payload, onDelta, onComponent) {
    const controller = new AbortController();
    activeController = controller;
    let timedOut = false;
    const timeout = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, 120000);
    let reader;
    let buffer = "";
    let current = { event: "message", id: "", data: [] };
    let lastSequence = 0;
    let streamedTextLength = 0;
    let responsePayload = null;

    function dispatchEvent() {
      if (!current.data.length) { current = { event: "message", id: "", data: [] }; return; }
      let sequence = 0;
      const idMatch = current.id.match(/^[A-Za-z0-9_-]+:(\d+)$/);
      if (!idMatch) throw new Error("The concierge returned an invalid stream event ID.");
      sequence = Number(idMatch[1]);
      if (!Number.isSafeInteger(sequence) || sequence <= lastSequence) {
        current = { event: "message", id: "", data: [] };
        return;
      }
      if (sequence !== lastSequence + 1) throw new Error("A response stream event was missing. Please retry.");
      lastSequence = sequence;
      let data;
      try { data = JSON.parse(current.data.join("\n")); }
      catch { throw new Error("The concierge returned an invalid stream event."); }
      switch (current.event) {
        case "turn.started":
          if (data.schema_version !== "1.0" || data.conversation_id !== payload.session_id || data.turn_id !== payload.turn_id) {
            throw new Error("The response belongs to a different conversation.");
          }
          break;
        case "text.delta":
          if (!validText(data.text, 24000)) throw new Error("The concierge returned an oversized text event.");
          streamedTextLength += data.text.length;
          if (streamedTextLength > 24000) throw new Error("The concierge response exceeded the safe display limit.");
          onDelta(data.text);
          break;
        case "component.ready":
        case "action.pending": {
          const block = validateBlock(data.block);
          if (block.type === "unknown") throw new Error("The concierge returned a component this screen cannot safely display.");
          onComponent(block);
          break;
        }
        case "text.completed":
          if (data.streamed === false && validText(data.text, 6000) && data.text) onDelta(data.text);
          break;
        case "turn.completed":
          responsePayload = data.response;
          break;
        case "turn.failed": {
          const error = new Error(validText(data.message, 300) ? data.message : "The response was interrupted. Please retry.");
          error.retryable = data.retryable === true;
          error.status = 502;
          throw error;
        }
        default: throw new Error("The concierge returned an unsupported stream event.");
      }
      current = { event: "message", id: "", data: [] };
    }

    function parseLine(line) {
      if (!line) { dispatchEvent(); return; }
      if (line.startsWith(":")) return;
      const separator = line.indexOf(":");
      const field = separator < 0 ? line : line.slice(0, separator);
      const value = separator < 0 ? "" : line.slice(separator + 1).replace(/^ /, "");
      if (field === "event") current.event = value;
      else if (field === "id") current.id = value;
      else if (field === "data") current.data.push(value);
    }

    try {
      let response;
      try {
        response = await fetch("/api/guest/intelligent-chat/stream", {
          method: "POST",
          credentials: "same-origin",
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            ...(sessionId ? { "X-Concierge-Session": sessionId } : {}),
          },
          body: JSON.stringify(payload),
        });
      } catch (error) {
        if (controller.signal.aborted) throw error;
        const networkError = new Error("The network connection was interrupted. Check your connection and try again.");
        networkError.networkFailure = true;
        throw networkError;
      }
      if (!response.ok) {
        let detail = "Request failed. Please try again.";
        try { detail = readError((await response.json()).detail); } catch { /* Keep a bounded fallback. */ }
        const error = new Error(detail);
        error.status = response.status;
        throw error;
      }
      if (!response.headers.get("content-type")?.includes("text/event-stream") || !response.body) {
        throw new Error("The concierge did not return a response stream.");
      }
      reader = response.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() || "";
        for (const line of lines) parseLine(line);
      }
      buffer += decoder.decode();
      if (buffer) parseLine(buffer);
      parseLine("");
      if (!responsePayload || responsePayload.schema_version !== "1.0"
        || responsePayload.conversation_id !== payload.session_id
        || responsePayload.turn_id !== payload.turn_id
        || !Array.isArray(responsePayload.blocks) || responsePayload.blocks.length < 1 || responsePayload.blocks.length > 20) {
        throw new Error("The concierge returned a response this screen cannot safely display.");
      }
      return { ...responsePayload, blocks: responsePayload.blocks.map(validateBlock) };
    } catch (error) {
      if (controller.signal.aborted) {
        const stopped = new Error(timedOut
          ? "The response took too long. Your message is saved; you can retry it."
          : "Response stopped. You can retry your message.");
        stopped.cancelled = !timedOut;
        stopped.networkFailure = timedOut;
        throw stopped;
      }
      throw error;
    } finally {
      window.clearTimeout(timeout);
      if (reader) { try { await reader.cancel(); } catch { /* The stream may already be closed. */ } }
      if (activeController === controller) activeController = null;
    }
  }

  function gatewayContext() {
    return Object.fromEntries(new URLSearchParams(window.location.search).entries());
  }

  function createClientId() {
    const saved = localStorage.getItem(storageKeys.client);
    if (saved) return saved;
    const value = newId();
    localStorage.setItem(storageKeys.client, value);
    return value;
  }

  function safeHex(value, fallback) {
    const text = String(value || "");
    return /^#[0-9a-f]{6}$/i.test(text) ? text : fallback;
  }

  function contrastFor(hex) {
    const value = hex.slice(1);
    const rgb = [0, 2, 4].map((index) => parseInt(value.slice(index, index + 2), 16) / 255);
    const luminance = rgb.map((part) => part <= 0.03928 ? part / 12.92 : ((part + 0.055) / 1.055) ** 2.4)
      .reduce((sum, part, index) => sum + part * [0.2126, 0.7152, 0.0722][index], 0);
    return luminance > 0.48 ? "#25231f" : "#fffdf8";
  }

  function safeSameOriginImage(value) {
    const raw = String(value || "").trim();
    if (!raw || raw.startsWith("//") || /[\\\u0000-\u001f]/.test(raw)) return "";
    try {
      const url = new URL(raw, window.location.href);
      return url.origin === window.location.origin && ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch { return ""; }
  }

  function safeApprovedHttpsUrl(value) {
    const raw = String(value || "").trim();
    if (!raw || raw.startsWith("//") || /[\\\u0000-\u001f]/.test(raw)) return "";
    try {
      const url = new URL(raw, window.location.href);
      if (url.username || url.password) return "";
      if (url.origin === window.location.origin && ["http:", "https:"].includes(url.protocol)) return url.href;
      return url.protocol === "https:" ? url.href : "";
    } catch { return ""; }
  }

  function applyBranding(profile) {
    const name = String(profile.name || "Your hotel").slice(0, 120);
    const concierge = String(profile.concierge_name || "Guest concierge").slice(0, 80);
    $("hotel-name").textContent = name;
    $("concierge-name").textContent = concierge;
    document.title = `${name} · ${concierge}`;
    const accent = safeHex(profile.theme?.primary_color, "#9a7744");
    document.documentElement.style.setProperty("--accent", accent);
    document.documentElement.style.setProperty("--accent-ink", contrastFor(accent));
    const mark = $("brand-mark");
    mark.textContent = [...name][0] || "C";
    const logo = safeSameOriginImage(profile.logo_url);
    if (logo) {
      const image = document.createElement("img");
      image.alt = "";
      image.decoding = "async";
      image.src = logo;
      image.addEventListener("error", () => { mark.replaceChildren(document.createTextNode([...name][0] || "C")); }, { once: true });
      mark.replaceChildren(image);
    }
    if (Array.isArray(profile.languages) && profile.languages[0]) {
      document.documentElement.lang = String(profile.languages[0]).slice(0, 20);
    }
  }

  function greetingFor(timezone) {
    let hour = new Date().getHours();
    try {
      const parts = new Intl.DateTimeFormat("en", { hour: "numeric", hour12: false, timeZone: timezone || "UTC" }).formatToParts(new Date());
      hour = Number(parts.find((part) => part.type === "hour")?.value ?? hour);
    } catch { /* Device time is a safe local fallback. */ }
    return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  }

  function validatedConfig(data) {
    const prompts = Array.isArray(data?.suggested_prompts)
      ? data.suggested_prompts.filter((item) => typeof item === "string" && item.trim() && item.length <= 160).slice(0, 6)
      : [];
    return {
      welcome: typeof data?.welcome_message === "string" ? data.welcome_message.slice(0, 300) : "Ask a question or tell me what you need.",
      prompts: prompts.length ? prompts : [
        "Show me dining options",
        "What hotel facilities are available?",
        "What can I explore nearby?",
        "Can I have some extra towels please?",
      ],
    };
  }

  function renderWelcome(config) {
    $("welcome-greeting").textContent = greetingFor(property?.timezone);
    $("welcome-description").textContent = config.welcome || "Ask a question or tell me what you need.";
    const list = $("welcome-suggestions");
    list.replaceChildren();
    for (const prompt of config.prompts) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "suggestion-chip";
      button.textContent = prompt;
      button.addEventListener("click", () => sendMessage(prompt));
      list.appendChild(button);
    }
  }

  function clearLegacyTranscriptStorage() {
    for (const key of Object.keys(sessionStorage)) {
      if (key.startsWith("concierge-v2-messages-")) sessionStorage.removeItem(key);
    }
  }

  async function restoreMessages() {
    try {
      const history = await api("/api/guest/intelligent-history");
      if (history.schema_version !== "1.0" || history.conversation_id !== sessionId || !Array.isArray(history.turns)) {
        throw new Error("Invalid server conversation history.");
      }
      messages = [];
      for (const turn of history.turns.slice(-40)) {
        if (!turn || typeof turn.turn_id !== "string" || !validText(turn.message, 2000)
          || turn.response?.schema_version !== "1.0" || turn.response?.conversation_id !== sessionId
          || turn.response?.turn_id !== turn.turn_id || !Array.isArray(turn.response.blocks)) continue;
        messages.push({ id: `guest-${turn.turn_id}`, turnId: turn.turn_id, role: "guest", blocks: [{ id: newId(), type: "text", content: turn.message }] });
        messages.push({ id: `assistant-${turn.turn_id}`, role: "assistant", blocks: turn.response.blocks.map(validateBlock) });
      }
    } catch { messages = []; }
  }

  function persistMessages() {
    if (!sessionId) return;
    messages = messages.slice(-80).map((message) => ({
      ...message,
      blocks: (message.blocks || []).map(validateBlock),
    }));
  }

  function validText(value, maximum = 6000) {
    return typeof value === "string" && value.length <= maximum;
  }

  function validSourceIds(value) {
    const ids = Array.isArray(value) ? value : [];
    return ids.length <= 16 && ids.every((id) => validText(id, 256) && id.startsWith("guest:"));
  }

  function attachSourceIds(node, value) {
    if (Array.isArray(value) && value.length) node.dataset.sourceIds = value.join(" ");
    return node;
  }

  function validateEntityCard(card) {
    return card && typeof card === "object"
      && ["restaurant", "facility", "service", "place"].includes(card.type)
      && validText(card.id, 80) && validText(card.title, 120) && card.title.trim()
      && validText(card.subtitle || "", 120) && validText(card.description || "", 500)
      && validText(card.detail || "", 300)
      && validText(card.resource_id || "", 80) && validText(card.image_url || "", 500)
      && (!card.image_url || safeApprovedHttpsUrl(card.image_url))
      && validText(card.location || "", 240) && validText(card.opening_hours || "", 160)
      && Array.isArray(card.policies || []) && (card.policies || []).length <= 8
      && (card.policies || []).every((policy) => validText(policy, 240) && policy.trim())
      && typeof (card.menu_available ?? false) === "boolean"
      && validText(card.reservation_url || "", 1000)
      && (!card.reservation_url || safeApprovedHttpsUrl(card.reservation_url))
      && validText(card.maps_url || "", 1000)
      && (!card.maps_url || safeApprovedHttpsUrl(card.maps_url))
      && (card.open_now == null || typeof card.open_now === "boolean")
      && validSourceIds(card.source_ids);
  }

  function validSelectionOption(option) {
    return option && typeof option === "object"
      && validText(option.label, 100) && option.label.trim()
      && validText(option.value, 120) && option.value.trim();
  }

  function validSelectionField(field) {
    if (!field || typeof field !== "object"
      || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(field.id || "")
      || !validText(field.label, 100) || !field.label.trim()
      || !["date", "time", "quantity", "party_size", "service_option"].includes(field.input_type)
      || typeof (field.required ?? true) !== "boolean") return false;
    const options = Array.isArray(field.options) ? field.options : [];
    if (options.length > 8 || !options.every(validSelectionOption)) return false;
    if (field.input_type === "service_option") {
      return options.length > 0 && field.minimum == null && field.maximum == null
        && new Set(options.map((option) => option.value)).size === options.length;
    }
    return options.length === 0
      && ((field.minimum == null) || (Number.isSafeInteger(field.minimum) && field.minimum >= 0 && field.minimum <= 100000))
      && ((field.maximum == null) || (Number.isSafeInteger(field.maximum) && field.maximum >= 0 && field.maximum <= 100000))
      && !(field.minimum != null && field.maximum != null && field.minimum > field.maximum)
      && (!["date", "time"].includes(field.input_type) || (field.minimum == null && field.maximum == null));
  }

  function validSelectionForm(block) {
    if (!validText(block.title, 120) || !block.title.trim()) return false;
    const fields = Array.isArray(block.fields) ? block.fields : [];
    const options = Array.isArray(block.options) ? block.options : [];
    const typedFieldsValid = fields.length >= 1 && fields.length <= 6
      && fields.every(validSelectionField)
      && new Set(fields.map((field) => field.id)).size === fields.length;
    const legacyOptionsValid = options.length >= 1 && options.length <= 8 && options.every(validSelectionOption);
    if (Boolean(fields.length) === Boolean(options.length)) return false;
    return (fields.length ? typedFieldsValid : legacyOptionsValid)
      && validText(block.submit_label || "Review selections", 40)
      && validText(block.continue_label || "Share with concierge", 40)
      && validText(block.cancel_label || "Cancel selections", 40);
  }

  function validateBlock(block) {
    if (!block || typeof block !== "object" || !validText(block.id, 80)) {
      return { id: newId(), type: "unknown" };
    }
    switch (block.type) {
      case "text": return validText(block.content) && validSourceIds(block.source_ids)
        ? block : { id: block.id, type: "unknown" };
      case "grounded_claim":
        return validText(block.content, 1200) && block.content.trim()
          && Array.isArray(block.source_ids) && block.source_ids.length > 0 && validSourceIds(block.source_ids)
          ? block : { id: block.id, type: "unknown" };
      case "suggestion_chips":
        return Array.isArray(block.items) && block.items.length <= 6 && block.items.every((item) => validText(item?.label, 80) && item.label && validText(item.prompt, 300) && item.prompt)
          ? block : { id: block.id, type: "unknown" };
      case "entity_card": return validateEntityCard(block.card) ? block : { id: block.id, type: "unknown" };
      case "card_collection":
        return validText(block.title, 100) && Array.isArray(block.cards) && block.cards.length <= 8 && block.cards.every(validateEntityCard)
          ? block : { id: block.id, type: "unknown" };
      case "details_panel":
        return validText(block.title, 100) && Array.isArray(block.fields) && block.fields.length <= 12
          && validSourceIds(block.source_ids)
          && block.fields.every((item) => validText(item?.label, 60) && item.label && validText(item?.value, 300) && validSourceIds(item.source_ids))
          ? block : { id: block.id, type: "unknown" };
      case "selection_form":
        return validSelectionForm(block) ? block : { id: block.id, type: "unknown" };
      case "request_review":
        return validText(block.title, 120) && validText(block.department || "", 120)
          && validText(block.description, 1000) && validText(block.confirmation_token, 3000)
          && validSourceIds(block.source_ids)
          && validText(block.confirm_label || "Confirm request", 40)
          ? block : { id: block.id, type: "unknown" };
      case "verified_confirmation":
        return validText(block.title, 120) && validText(block.detail || "", 500) && validSourceIds(block.source_ids)
          ? block : { id: block.id, type: "unknown" };
      case "request_status": {
        const validStatuses = ["new", "assigned", "accepted", "in_progress", "delivered", "completed", "cancelled"];
        const items = Array.isArray(block.items) ? block.items : [];
        return validText(block.title, 120) && block.title.trim()
          && items.length >= 1 && items.length <= 10
          && items.every((item) => item && validText(item.name, 100) && item.name.trim()
            && validText(item.description || "", 240) && validText(item.department || "", 100)
            && validStatuses.includes(item.status)
            && Number.isSafeInteger(item.updated_at) && item.updated_at >= 0)
          ? block : { id: block.id, type: "unknown" };
      }
      case "directions": {
        const steps = Array.isArray(block.steps) ? block.steps : [];
        return validText(block.title, 120) && block.title.trim()
          && steps.length >= 2 && steps.length <= 40
          && steps.every((step) => validText(step?.label, 120) && step.label.trim()
            && Array.isArray(step.source_ids) && step.source_ids.length >= 1 && validSourceIds(step.source_ids))
          ? block : { id: block.id, type: "unknown" };
      }
      case "map_view":
        {
          const hasCoordinates = Number.isFinite(block.latitude) && block.latitude >= -90 && block.latitude <= 90
            && Number.isFinite(block.longitude) && block.longitude >= -180 && block.longitude <= 180;
          const hasFloorPlan = typeof block.map_image_url === "string" && block.map_image_url.startsWith("/")
            && !block.map_image_url.startsWith("//") && Boolean(safeApprovedHttpsUrl(block.map_image_url))
            && Number.isInteger(block.image_width) && block.image_width > 0 && block.image_width <= 25000
            && Number.isInteger(block.image_height) && block.image_height > 0 && block.image_height <= 25000;
          const mapMarkers = Array.isArray(block.markers) ? block.markers : [];
          const markersValid = block.markers === undefined ? !hasFloorPlan
            : Array.isArray(block.markers) && mapMarkers.length <= 80
            && mapMarkers.every((marker) => validText(marker?.id, 80) && marker.id
              && validText(marker?.label, 120) && marker.label
              && Number.isFinite(marker?.x_percent) && marker.x_percent >= 0 && marker.x_percent <= 100
              && Number.isFinite(marker?.y_percent) && marker.y_percent >= 0 && marker.y_percent <= 100
              && validSourceIds(marker.source_ids));
          return validText(block.title, 120) && validText(block.label || "", 120)
            && validText(block.map_alt || "", 500) && (hasCoordinates || hasFloorPlan)
            && validSourceIds(block.source_ids)
            && (!block.map_image_url || hasFloorPlan) && markersValid
            ? block : { id: block.id, type: "unknown" };
        }
      case "loading_state": return validText(block.message || "", 160) ? block : { id: block.id, type: "unknown" };
      case "error_state": return validText(block.message, 500) ? block : { id: block.id, type: "unknown" };
      default: return { id: block.id, type: "unknown" };
    }
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  function appendSuggestionButtons(parent, items) {
    const row = element("div", "suggestions-after");
    for (const item of items) {
      const button = element("button", "suggestion-chip", item.label);
      button.type = "button";
      button.addEventListener("click", () => sendMessage(item.prompt));
      row.appendChild(button);
    }
    parent.appendChild(row);
  }

  function appendEntityCard(parent, card) {
    const article = attachSourceIds(element("article", "entity-card entity-card-" + card.type), card.source_ids);
    const imageUrl = safeApprovedHttpsUrl(card.image_url);
    if (imageUrl) {
      const image = document.createElement("img");
      image.className = "entity-card-image";
      image.src = imageUrl;
      image.alt = "";
      image.loading = "lazy";
      image.decoding = "async";
      image.referrerPolicy = "no-referrer";
      image.addEventListener("error", () => image.remove(), { once: true });
      article.appendChild(image);
    }
    article.appendChild(element("h3", "", card.title));
    if (card.subtitle) article.appendChild(element("p", "card-subtitle", card.subtitle));
    if (card.description) article.appendChild(element("p", "card-description", card.description));
    if (card.location) article.appendChild(element("p", "card-location", `Location: ${card.location}`));
    if (card.opening_hours) article.appendChild(element("p", "card-hours", `Hours: ${card.opening_hours}`));
    if (card.detail) article.appendChild(element("p", "card-detail", card.detail));
    if (Array.isArray(card.policies) && card.policies.length) {
      const list = element("ul", "card-policies");
      list.setAttribute("aria-label", "Guest policies");
      for (const policy of card.policies.slice(0, 8)) list.appendChild(element("li", "", policy));
      article.appendChild(list);
    }
    if (card.type === "restaurant" && card.menu_available && card.resource_id) {
      const menuButton = element("button", "menu-toggle", "View published menu");
      const menuRegion = element("div", "menu-details");
      menuRegion.hidden = true;
      menuRegion.setAttribute("aria-live", "polite");
      menuButton.type = "button";
      menuButton.setAttribute("aria-expanded", "false");
      menuButton.addEventListener("click", async () => {
        if (!menuRegion.dataset.loaded) {
          menuButton.disabled = true;
          menuButton.textContent = "Loading menu…";
          try {
            const result = await api(`/api/guest/restaurants/${encodeURIComponent(card.resource_id)}/menus`);
            menuRegion.replaceChildren();
            for (const menu of (Array.isArray(result.menus) ? result.menus : []).slice(0, 8)) {
              menuRegion.appendChild(attachSourceIds(element("h4", "", [menu.name, menu.meal_period].filter(Boolean).join(" · ")), menu.source_ids));
              for (const item of (Array.isArray(menu.items) ? menu.items : []).slice(0, 40)) {
                const entry = attachSourceIds(element("div", "menu-item"), item.source_ids);
                entry.appendChild(element("strong", "", String(item.name || "Menu item").slice(0, 160)));
                if (item.price) entry.appendChild(element("span", "menu-price", String(item.price).slice(0, 40)));
                if (item.description) entry.appendChild(element("p", "", String(item.description).slice(0, 500)));
                const dietary = [
                  ...(Array.isArray(item.dietary_tags) ? item.dietary_tags : []),
                  ...(Array.isArray(item.allergens) ? item.allergens.map((value) => `Allergen: ${value}`) : []),
                ].slice(0, 12);
                if (dietary.length) entry.appendChild(element("p", "menu-tags", dietary.join(" · ")));
                menuRegion.appendChild(entry);
              }
            }
            if (!menuRegion.childElementCount) menuRegion.appendChild(element("p", "", "No published menu items are available right now."));
            menuRegion.dataset.loaded = "true";
          } catch {
            menuRegion.replaceChildren(element("p", "", "The published menu couldn't be loaded. Please try again."));
          } finally {
            menuButton.disabled = false;
            menuButton.textContent = "View published menu";
          }
        }
        menuRegion.hidden = !menuRegion.hidden;
        menuButton.setAttribute("aria-expanded", String(!menuRegion.hidden));
      });
      article.append(menuButton, menuRegion);
    }
    const reservationUrl = safeApprovedHttpsUrl(card.reservation_url);
    if (card.type === "restaurant" && reservationUrl) {
      const link = element("a", "reservation-link", "Reservation options");
      link.href = reservationUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.referrerPolicy = "no-referrer";
      article.appendChild(link);
    }
    if (card.type === "place" && card.open_now != null) {
      article.appendChild(element("p", "card-detail", card.open_now ? "Listed as open now" : "Not listed as open now"));
    }
    if (card.type === "place" && card.maps_url) {
      const directions = element("a", "reservation-link", "Directions");
      directions.href = safeApprovedHttpsUrl(card.maps_url);
      directions.target = "_blank";
      directions.rel = "noopener noreferrer";
      directions.referrerPolicy = "no-referrer";
      article.appendChild(directions);
    }
    if (card.type === "service") {
      const request = element("button", "reservation-link", "Request with concierge");
      request.type = "button";
      request.addEventListener("click", () => sendMessage("Can you provide " + card.title + "?"));
      article.appendChild(request);
    }
    parent.appendChild(article);
  }

  function renderRequestReview(parent, block) {
    const card = attachSourceIds(element("section", "request-review"), block.source_ids);
    card.appendChild(element("h3", "", block.title));
    if (block.department) card.appendChild(element("p", "review-department", block.department));
    card.appendChild(element("p", "", block.description));
    const confirm = element("button", "primary-action", block.confirm_label || "Confirm request");
    confirm.type = "button";
    confirm.disabled = pendingActions.has(block.confirmation_token) || invalidActions.has(block.confirmation_token);
    confirm.addEventListener("click", () => confirmGuestAction(block, confirm));
    card.appendChild(confirm);
    parent.appendChild(card);
  }

  function renderRequestStatus(parent, block) {
    const panel = element("section", "request-status-panel");
    panel.setAttribute("aria-label", block.title);
    panel.appendChild(element("h3", "", block.title));
    const list = element("div", "request-status-list");
    const statusLabels = {
      new: "Received", assigned: "Assigned", accepted: "Accepted", in_progress: "In progress",
      delivered: "Delivered", completed: "Completed", cancelled: "Cancelled",
    };
    for (const item of block.items) {
      const card = element("article", "request-status-card");
      const heading = element("div", "request-status-heading");
      heading.appendChild(element("h4", "", item.name));
      const status = element("span", `request-status-pill status-${item.status}`, statusLabels[item.status]);
      status.setAttribute("aria-label", `Status: ${statusLabels[item.status]}`);
      heading.appendChild(status);
      card.appendChild(heading);
      if (item.description) card.appendChild(element("p", "", item.description));
      const details = [item.department, item.updated_at ? `Updated ${new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.updated_at * 1000))}` : ""]
        .filter(Boolean).join(" · ");
      if (details) card.appendChild(element("span", "request-status-detail", details));
      list.appendChild(card);
    }
    panel.appendChild(list);
    parent.appendChild(panel);
  }

  function renderDirections(parent, block) {
    const panel = element("section", "directions-panel");
    panel.setAttribute("aria-label", block.title);
    panel.appendChild(element("h3", "", block.title));
    const list = element("ol", "directions-list");
    for (const step of block.steps) {
      const item = attachSourceIds(element("li", "", step.label), step.source_ids);
      list.appendChild(item);
    }
    panel.appendChild(list);
    parent.appendChild(panel);
  }

  function renderSelectionForm(parent, block) {
    const panel = element("section", "selection-panel");
    const heading = element("h3", "", block.title);
    const guidance = element("p", "selection-guidance", "Review your details before sharing them with the concierge. This does not create a booking or service request.");
    panel.append(heading, guidance);
    const fields = block.fields?.length ? block.fields : [{
      id: "selection", label: "Your selection", input_type: "service_option", required: true, options: block.options,
    }];

    function renderEntry(values = {}, focusFirst = false) {
      const form = document.createElement("form");
      form.className = "selection-form";
      const controlById = new Map();
      for (const field of fields) {
        const group = element("div", "selection-field");
        const label = document.createElement("label");
        const controlId = `selection-${newId()}`;
        label.htmlFor = controlId;
        label.textContent = field.label;
        let control;
        if (field.input_type === "service_option") {
          control = document.createElement("select");
          const placeholder = document.createElement("option");
          placeholder.value = "";
          placeholder.textContent = "Choose an option";
          control.appendChild(placeholder);
          for (const option of field.options) {
            const choice = document.createElement("option");
            choice.value = option.value;
            choice.textContent = option.label;
            control.appendChild(choice);
          }
        } else {
          control = document.createElement("input");
          control.type = field.input_type === "quantity" || field.input_type === "party_size" ? "number" : field.input_type;
          if (control.type === "number") {
            control.step = "1";
            control.min = String(field.minimum ?? 1);
            if (field.maximum != null) control.max = String(field.maximum);
            control.inputMode = "numeric";
          }
        }
        control.id = controlId;
        control.name = field.id;
        control.required = field.required !== false;
        control.autocomplete = "off";
        control.value = values[field.id] ?? "";
        control.addEventListener("input", () => control.setCustomValidity(""));
        control.addEventListener("change", () => control.setCustomValidity(""));
        group.append(label, control);
        form.appendChild(group);
        controlById.set(field.id, control);
      }
      const review = element("button", "btn btn-primary", block.submit_label || "Review selections");
      review.type = "submit";
      form.appendChild(review);
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        if (!form.reportValidity()) return;
        const selected = {};
        for (const field of fields) {
          const control = controlById.get(field.id);
          const value = control.value;
          if (field.required === false && value === "") continue;
          if (["quantity", "party_size"].includes(field.input_type)) {
            const numeric = Number(value);
            const minimum = field.minimum ?? 1;
            if (!Number.isSafeInteger(numeric) || numeric < minimum || (field.maximum != null && numeric > field.maximum)) {
              control.setCustomValidity(`Enter a whole number from ${minimum}${field.maximum != null ? ` to ${field.maximum}` : " or more"}.`);
              control.reportValidity();
              return;
            }
            control.setCustomValidity("");
          }
          selected[field.id] = value;
        }
        renderReview(selected);
      });
      panel.replaceChildren(heading, guidance, form);
      const firstControl = controlById.values().next().value;
      if (firstControl && focusFirst) firstControl.focus({ preventScroll: true });
    }

    function renderReview(selected) {
      const summary = element("dl", "selection-summary");
      const lines = [];
      for (const field of fields) {
        if (!(field.id in selected)) continue;
        const raw = selected[field.id];
        const option = field.options?.find((item) => item.value === raw);
        const shown = option ? option.label : raw;
        summary.append(element("dt", "", field.label), element("dd", "", shown));
        lines.push(`${field.label}: ${shown}`);
      }
      const review = element("div", "selection-review");
      review.setAttribute("aria-live", "polite");
      review.append(element("h4", "", "Review your selections"), summary);
      const actions = element("div", "selection-actions");
      const edit = element("button", "btn btn-secondary", "Edit selections");
      edit.type = "button";
      edit.addEventListener("click", () => renderEntry(selected, true));
      const cancel = element("button", "btn btn-secondary", block.cancel_label || "Cancel selections");
      cancel.type = "button";
      cancel.addEventListener("click", () => panel.replaceChildren(
        heading,
        element("p", "selection-guidance", "Selections cleared. Nothing was sent."),
      ));
      const share = element("button", "btn btn-primary", block.continue_label || "Share with concierge");
      share.type = "button";
      let submitted = false;
      share.addEventListener("click", () => {
        if (submitted) return;
        submitted = true;
        share.disabled = true;
        edit.disabled = true;
        cancel.disabled = true;
        sendMessage(`Please share these preferences with the concierge. This is not a booking or service request.\n${lines.join("\n")}`);
      });
      actions.append(edit, cancel, share);
      review.appendChild(actions);
      panel.replaceChildren(heading, guidance, review);
    }

    parent.appendChild(panel);
    renderEntry();
  }

  function renderBlock(parent, rawBlock) {
    const block = validateBlock(rawBlock);
    const wrapper = element("div", "message-block");
    switch (block.type) {
      case "text": wrapper.appendChild(element("p", "message-text", block.content)); break;
      case "grounded_claim":
        wrapper.appendChild(attachSourceIds(element("p", "message-text grounded-claim", block.content), block.source_ids));
        break;
      case "suggestion_chips": appendSuggestionButtons(wrapper, block.items); break;
      case "entity_card": appendEntityCard(wrapper, block.card); break;
      case "card_collection": {
        wrapper.appendChild(element("h3", "block-heading", block.title));
        const grid = element("div", "card-grid");
        for (const card of block.cards) appendEntityCard(grid, card);
        wrapper.appendChild(grid);
        break;
      }
      case "details_panel": {
        const panel = attachSourceIds(element("section", "detail-panel"), block.source_ids);
        panel.appendChild(element("h3", "", block.title));
        const list = element("dl", "detail-list");
        for (const item of block.fields) {
          const row = element("div", "");
          attachSourceIds(row, item.source_ids);
          row.append(element("dt", "", item.label), element("dd", "", item.value));
          list.appendChild(row);
        }
        panel.appendChild(list);
        wrapper.appendChild(panel);
        break;
      }
      case "selection_form": {
        renderSelectionForm(wrapper, block);
        break;
      }
      case "request_review": renderRequestReview(wrapper, block); break;
      case "request_status": renderRequestStatus(wrapper, block); break;
      case "directions": renderDirections(wrapper, block); break;
      case "verified_confirmation": {
        const panel = attachSourceIds(element("section", "verified-confirmation"), block.source_ids);
        panel.appendChild(element("span", "confirmation-mark", "✓"));
        panel.appendChild(element("h3", "", block.title));
        if (block.detail) panel.appendChild(element("p", "", block.detail));
        wrapper.appendChild(panel);
        break;
      }
      case "map_view": {
        const panel = attachSourceIds(element("section", "map-panel"), block.source_ids);
        panel.appendChild(element("h3", "", block.title));
        if (block.map_image_url && block.image_width && block.image_height) {
          const figure = element("figure", "floor-map-figure");
          const mapFrame = element("div", "floor-map-frame");
          mapFrame.style.aspectRatio = `${block.image_width} / ${block.image_height}`;
          const image = document.createElement("img");
          image.className = "floor-map-image";
          image.src = safeApprovedHttpsUrl(block.map_image_url);
          image.alt = block.map_alt || block.title;
          image.loading = "lazy";
          image.decoding = "async";
          image.referrerPolicy = "no-referrer";
          const markers = element("div", "floor-map-markers");
          const selectedLocation = element("p", "floor-map-selection", "Select a marker to identify its location.");
          selectedLocation.setAttribute("aria-live", "polite");
          for (const marker of (Array.isArray(block.markers) ? block.markers : [])) {
            const button = element("button", "floor-map-marker", marker.label);
            attachSourceIds(button, marker.source_ids);
            button.type = "button";
            button.style.left = `${marker.x_percent}%`;
            button.style.top = `${marker.y_percent}%`;
            button.setAttribute("aria-label", `Show location: ${marker.label}`);
            button.setAttribute("aria-pressed", "false");
            button.addEventListener("click", () => {
              markers.querySelectorAll(".floor-map-marker").forEach((item) => item.setAttribute("aria-pressed", "false"));
              button.setAttribute("aria-pressed", "true");
              selectedLocation.textContent = marker.label;
            });
            markers.appendChild(button);
          }
          image.addEventListener("error", () => {
            image.hidden = true;
            markers.hidden = true;
            mapFrame.classList.add("floor-map-unavailable");
          }, { once: true });
          mapFrame.append(image, markers);
          figure.appendChild(mapFrame);
          panel.append(figure, selectedLocation);
          if (block.markers.length) {
            const textAlternative = element("p", "floor-map-alternative", `Locations on this floor: ${block.markers.map((marker) => marker.label).join(", ")}.`);
            panel.appendChild(textAlternative);
          }
        } else {
          panel.appendChild(element("p", "", block.label || `${block.latitude.toFixed(5)}, ${block.longitude.toFixed(5)}`));
        }
        wrapper.appendChild(panel);
        break;
      }
      case "loading_state": {
        const line = element("div", "loading-line");
        const dots = element("span", "loading-dots");
        for (let i = 0; i < 3; i += 1) dots.appendChild(element("i", ""));
        line.append(dots, element("span", "", block.message || "Checking that for you…"));
        wrapper.appendChild(line);
        break;
      }
      case "error_state": {
        const panel = element("section", "error-panel");
        panel.appendChild(element("p", "", block.message));
        wrapper.appendChild(panel);
        break;
      }
      default: wrapper.appendChild(element("p", "message-text", "This answer included an item that this interface cannot display."));
    }
    parent.appendChild(wrapper);
  }

  function renderMessages() {
    const list = $("message-list");
    list.replaceChildren();
    for (const message of messages) {
      const isGuest = message.role === "guest";
      const row = element("article", `message-row ${isGuest ? "guest" : "assistant"}`);
      row.dataset.messageId = String(message.id).slice(0, 80);
      const body = element("div", "message-body");
      body.appendChild(element("span", "message-label", isGuest ? "You" : $("concierge-name").textContent));
      for (const block of message.blocks || []) renderBlock(body, block);
      row.appendChild(body);
      list.appendChild(row);
    }
    const hasMessages = messages.length > 0;
    $("welcome").hidden = hasMessages;
    $("conversation").hidden = !hasMessages;
    if (hasMessages) window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  }

  function historyForApi() {
    return messages.flatMap((message) => {
      const role = message.role === "guest" ? "guest" : "assistant";
      const text = (message.blocks || [])
        .filter((block) => block?.type === "text" && typeof block.content === "string")
        .map((block) => block.content.trim()).filter(Boolean).join("\n");
      return text ? [{ role, content: text.slice(0, 2000) }] : [];
    }).slice(-10);
  }

  async function confirmGuestAction(block, button) {
    const token = block.confirmation_token;
    if (!token || pendingActions.has(token) || invalidActions.has(token)) return;
    pendingActions.add(token);
    button.disabled = true;
    button.textContent = "Sending…";
    try {
      const result = await requestBody("/api/guest/actions/confirm", { session_id: sessionId, proposal_token: token });
      if (!["created", "existing"].includes(result.status) || !result.request) {
        throw new Error("The hotel did not confirm the service request.");
      }
      const requestType = String(result.request.request_type || block.title || "Service request").slice(0, 120);
      const detail = String(result.request.description || block.description || "").slice(0, 500);
      const message = messages.find((item) => item.blocks?.some((candidate) => candidate.type === "request_review" && candidate.confirmation_token === token));
      if (message) message.blocks = [{
        id: newId(), type: "verified_confirmation",
        title: result.status === "existing" ? "Your request is already with the hotel team" : "Your request has been sent",
        detail: [requestType, detail].filter(Boolean).join(" · "),
        source_ids: Array.isArray(result.source_ids) ? result.source_ids : [],
      }];
      persistMessages();
      renderMessages();
    } catch (error) {
      if (error.status === 409 || error.status === 401) invalidActions.add(token);
      const message = messages.find((item) => item.blocks?.some((candidate) => candidate.type === "request_review" && candidate.confirmation_token === token));
      if (message) {
        message.blocks.push({ id: newId(), type: "error_state", message: error.status === 401
          ? "Your concierge session has expired. Start a new chat before sending this request."
          : error.status === 409
            ? "This confirmation expired or the service changed. Please submit the request again."
            : "I couldn't verify whether the request was received. Retry this confirmation safely or contact the Front Desk." });
      }
      persistMessages();
      renderMessages();
    } finally {
      pendingActions.delete(token);
      renderMessages();
    }
  }

  async function sendMessage(rawMessage) {
    const message = String(rawMessage || "").trim();
    if (!message || inputPending || !sessionId) return;
    const history = historyForApi();
    const previousAssistant = messages.at(-1);
    const previousGuest = messages.at(-2);
    const previousText = previousGuest?.blocks?.filter((block) => block.type === "text").map((block) => block.content).join("\n");
    const retrying = previousGuest?.role === "guest" && previousAssistant?.role === "assistant"
      && previousText === message && previousGuest.turnId
      && previousAssistant.blocks?.some((block) => block.type === "error_state");
    const guestMessage = retrying ? previousGuest : {
      id: newId(), turnId: `${Date.now().toString(36)}-${newId()}`, role: "guest",
      blocks: [{ id: newId(), type: "text", content: message }],
    };
    if (retrying) messages.pop();
    else messages.push(guestMessage);
    const assistantMessage = {
      id: newId(), role: "assistant",
      blocks: [{ id: newId(), type: "loading_state", message: "Checking that for you…" }],
    };
    messages.push(assistantMessage);
    inputPending = true;
    updateComposer();
    $("conversation-status").hidden = false;
    $("conversation-status-copy").textContent = "The concierge is checking that for you.";
    $("cancel-response").hidden = false;
    renderMessages();
    try {
      const result = await streamGuestChat({
        session_id: sessionId,
        turn_id: guestMessage.turnId,
        message,
        mode: "auto",
        conversation_history: history,
      }, (delta) => {
        let textBlock = assistantMessage.blocks.find((block) => block.type === "text");
        if (!textBlock) {
          textBlock = { id: newId(), type: "text", content: "" };
          assistantMessage.blocks = [textBlock];
        }
        textBlock.content += delta;
        renderMessages();
      }, (block) => {
        if (!assistantMessage.blocks.some((candidate) => candidate.id === block.id)) {
          assistantMessage.blocks.push(block);
          renderMessages();
        }
      });
      assistantMessage.blocks = result.blocks.map(validateBlock);
      const input = $("composer-input");
      if (input.value.trim() === message) input.value = "";
      updateComposer();
    } catch (error) {
      assistantMessage.blocks = [{
        id: newId(), type: "error_state",
        message: error.status === 401
          ? "Your concierge session has expired. Start a new chat to continue."
          : error.status === 404
            ? "This interface is no longer enabled for this property. Reload to return to the current guest experience."
            : error.status === 409
              ? error.message
            : error.networkFailure
              ? "The connection was interrupted. Your message is still visible; reconnect and try sending it again if needed."
              : error.message || "I couldn't complete that reply. Please try again.",
      }];
    } finally {
      inputPending = false;
      $("conversation-status").hidden = true;
      $("cancel-response").hidden = true;
      persistMessages();
      renderMessages();
      updateComposer();
    }
  }

  function updateComposer() {
    const input = $("composer-input");
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 148)}px`;
    $("send-button").disabled = inputPending || !input.value.trim() || !sessionId;
  }

  async function startSession(forceNew = false) {
    const savedSession = sessionStorage.getItem(storageKeys.session);
    const savedProperty = sessionStorage.getItem(storageKeys.property);
    if (!forceNew && savedSession && savedProperty === property.property_id) {
      try {
        const resumed = await requestBody("/api/session/resume", { client_id: clientId, session_id: savedSession });
        sessionId = resumed.session_id;
        await restoreMessages();
        return;
      } catch {
        sessionStorage.removeItem(storageKeys.session);
        sessionStorage.removeItem(storageKeys.property);
      }
    } else if (savedSession) {
      sessionStorage.removeItem(storageKeys.messages(savedSession));
      sessionStorage.removeItem(storageKeys.session);
      sessionStorage.removeItem(storageKeys.property);
    }
    const created = await requestBody("/api/session/start", {
      client_id: clientId,
      property_id: property.property_id,
      gateway_context: gatewayContext(),
    });
    sessionId = created.session_id;
    sessionStorage.setItem(storageKeys.session, sessionId);
    sessionStorage.setItem(storageKeys.property, property.property_id);
    messages = [];
  }

  async function startNewConversation() {
    if (inputPending || !property) return;
    const oldSession = sessionId;
    $("new-conversation").disabled = true;
    try {
      if (oldSession) {
        await requestBody("/api/session/end", { client_id: clientId, session_id: oldSession });
        sessionStorage.removeItem(storageKeys.messages(oldSession));
      }
      sessionStorage.removeItem(storageKeys.session);
      sessionStorage.removeItem(storageKeys.property);
      sessionId = null;
      messages = [];
      renderMessages();
      updateComposer();
      await startSession(true);
      $("composer-input").value = "";
      updateComposer();
      $("composer-input").focus({ preventScroll: true });
    } catch {
      $("conversation-status").hidden = false;
      $("conversation-status-copy").textContent = "A new private conversation couldn't be started. Your current conversation remains available.";
    } finally {
      $("new-conversation").disabled = false;
    }
  }

  function setupComposer() {
    const input = $("composer-input");
    input.addEventListener("input", updateComposer);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
        event.preventDefault();
        $("composer-form").requestSubmit();
      }
    });
    $("composer-form").addEventListener("submit", (event) => {
      event.preventDefault();
      if (input.value.trim()) sendMessage(input.value);
    });
    $("new-conversation").addEventListener("click", startNewConversation);
    $("cancel-response").addEventListener("click", () => activeController?.abort());
    $("reload-page").addEventListener("click", () => window.location.reload());
    updateComposer();
  }

  async function start() {
    setupComposer();
    clearLegacyTranscriptStorage();
    try {
      property = await api("/api/hotel");
      applyBranding(property);
      const config = validatedConfig(await api("/api/guest/intelligent-config"));
      renderWelcome(config);
      clientId = createClientId();
      await startSession();
      renderMessages();
      updateComposer();
      if (messages.length === 0) $("composer-input").focus({ preventScroll: true });
    } catch (error) {
      setError(error.status === 404
        ? "This property or guest experience is not available at this address. Please contact the hotel team."
        : "Please check your connection and reload. Your hotel information and private session have not been changed.");
    }
  }

  document.addEventListener("DOMContentLoaded", start, { once: true });
})();
