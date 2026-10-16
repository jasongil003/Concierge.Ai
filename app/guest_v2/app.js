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
  const mapViewStates = new Map();
  let property = null;
  let sessionId = null;
  let clientId = null;
  let messages = [];
  let inputPending = false;
  let sessionExpired = false;
  let activeController = null;
  let followLatestConversation = true;
  let adjustingConversationScroll = false;
  let conversationReadingAnchor = null;
  let conversationResizeObserver = null;
  let guestNotifications = [];
  let guestNotificationPreferences = {};
  let guestPrivacyConsents = {};

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
    return Object.fromEntries([...new URLSearchParams(window.location.search).entries()]
      .filter(([key]) => key !== "start_node_id" && key !== "start_sig"));
  }

  function wayfindingStartContext() {
    const params = new URLSearchParams(window.location.search);
    const nodeId = params.get("start_node_id") || "";
    const signature = params.get("start_sig") || "";
    if (!nodeId && !signature) return null;
    if (!/^[A-Za-z0-9_-]{1,80}$/.test(nodeId) || !/^[0-9a-f]{64}$/.test(signature)) {
      return { invalid: true };
    }
    return { nodeId, signature };
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
      && ["restaurant", "facility", "service", "place", "room", "menu_item"].includes(card.type)
      && validText(card.id, 80) && validText(card.title, 120) && card.title.trim()
      && validText(card.subtitle || "", 120) && validText(card.description || "", 500)
      && validText(card.detail || "", 300)
      && validText(card.resource_id || "", 80) && validText(card.image_url || "", 500)
      && validText(card.image_label || "", 80)
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
          && (block.node_ids === undefined || (Array.isArray(block.node_ids) && block.node_ids.length <= 40
            && block.node_ids.every((id) => validText(id, 80) && id.trim())))
          && steps.every((step) => validText(step?.label, 120) && step.label.trim()
            && validText(step.instruction || "", 240)
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
          const validMapMarker = (marker) => validText(marker?.id, 80) && marker.id
            && validText(marker?.label, 120) && marker.label
            && Number.isFinite(marker?.x_percent) && marker.x_percent >= 0 && marker.x_percent <= 100
            && Number.isFinite(marker?.y_percent) && marker.y_percent >= 0 && marker.y_percent <= 100
            && validSourceIds(marker.source_ids);
          const markersValid = block.markers === undefined ? !hasFloorPlan
            : Array.isArray(block.markers) && mapMarkers.length <= 80
            && mapMarkers.every(validMapMarker);
          const floorViews = Array.isArray(block.floors) ? block.floors : [];
          const floorsValid = floorViews.length <= 24 && floorViews.every((floor) => floor
            && validText(floor.floor_id, 80) && floor.floor_id
            && validText(floor.label, 120) && floor.label
            && typeof floor.map_image_url === "string" && floor.map_image_url.startsWith("/")
            && !floor.map_image_url.startsWith("//") && Boolean(safeApprovedHttpsUrl(floor.map_image_url))
            && Number.isInteger(floor.image_width) && floor.image_width > 0 && floor.image_width <= 25000
            && Number.isInteger(floor.image_height) && floor.image_height > 0 && floor.image_height <= 25000
            && typeof (floor.synthetic_demo ?? false) === "boolean"
            && Array.isArray(floor.markers) && floor.markers.length <= 80 && floor.markers.every(validMapMarker)
            && validSourceIds(floor.source_ids));
          const locations = Array.isArray(block.locations) ? block.locations : [];
          const locationsValid = locations.length <= 80 && locations.every((location) => location
            && validText(location.marker_id, 80) && location.marker_id
            && validText(location.title, 120) && location.title
            && validText(location.description || "", 500) && validText(location.floor_label || "", 120)
            && validText(location.location || "", 240) && validText(location.hours || "", 160)
            && Array.isArray(location.policies || []) && (location.policies || []).length <= 8
            && (location.policies || []).every((policy) => validText(policy, 240) && policy.trim())
            && validText(location.image_url || "", 500) && (!location.image_url || Boolean(safeApprovedHttpsUrl(location.image_url)))
            && validText(location.image_label || "", 80) && validSourceIds(location.source_ids));
          const routeNodeIds = Array.isArray(block.route_node_ids) ? block.route_node_ids : [];
          const startingNodeId = block.starting_node_id || "";
          return validText(block.title, 120) && validText(block.label || "", 120)
            && validText(block.map_alt || "", 500) && (hasCoordinates || hasFloorPlan)
            && validSourceIds(block.source_ids)
            && validText(block.floor_id || "", 80) && validText(block.floor_label || "", 120)
            && validText(block.focused_marker_id || "", 80)
            && validText(startingNodeId, 80)
            && (!startingNodeId || floorViews.some((floor) => floor.markers.some((marker) => marker.id === startingNodeId)))
            && typeof (block.synthetic_demo ?? false) === "boolean"
            && typeof (block.directions_enabled ?? false) === "boolean"
            && floorsValid && locationsValid
            && routeNodeIds.length <= 40 && routeNodeIds.every((id) => validText(id, 80) && id.trim())
            && (!block.map_image_url || hasFloorPlan) && markersValid
            ? block : { id: block.id, type: "unknown" };
        }
      case "facility_directory": {
        const locations = Array.isArray(block.locations) ? block.locations : [];
        const maps = Array.isArray(block.map_links) ? block.map_links : [];
        const validLocation = (item) => item
          && validText(item.id, 100) && item.id
          && validText(item.title, 160) && item.title
          && validText(item.category || "", 100)
          && validText(item.building || "", 160)
          && validText(item.floor || "", 80)
          && validText(item.location || "", 300)
          && validText(item.description || "", 500)
          && validText(item.listed_hours || "", 160)
          && validText(item.source_url || "", 2000)
          && (!item.source_url || safeApprovedHttpsUrl(item.source_url))
          && validSourceIds(item.source_ids || []);
        const validMap = (item) => item
          && validText(item.id, 100) && item.id
          && validText(item.title, 160) && item.title
          && validText(item.scope || "", 160)
          && validText(item.format || "", 20)
          && validText(item.url, 2000) && Boolean(safeApprovedHttpsUrl(item.url))
          && validText(item.license_status || "", 120)
          && validSourceIds(item.source_ids || []);
        const locationIds = locations.map((item) => item?.id);
        const mapIds = maps.map((item) => item?.id);
        return validText(block.title, 120) && validText(block.description || "", 500)
          && locations.length <= 80 && locations.every(validLocation)
          && new Set(locationIds).size === locationIds.length
          && maps.length <= 12 && maps.every(validMap)
          && new Set(mapIds).size === mapIds.length
          && (locations.length > 0 || maps.length > 0)
          && validSourceIds(block.source_ids || [])
          ? block : { id: block.id, type: "unknown" };
      }
      case "loading_state": return validText(block.message || "", 160) ? block : { id: block.id, type: "unknown" };
      case "error_state": return validText(block.message, 500)
        ? { ...block, canStartNewChat: block.canStartNewChat === true }
        : { id: block.id, type: "unknown" };
      default: return { id: block.id, type: "unknown" };
    }
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  const notificationPreferenceDefaults = {
    operational: true,
    assistance: true,
    experience: false,
    promotional: false,
  };
  const privacyConsentCategories = [
    "location_services", "proactive_notifications", "promotional_messages", "external_data_processing",
  ];
  const notificationStatuses = new Set(["queued", "sent", "delivered", "read", "failed", "expired"]);
  const notificationStatusLabels = {
    queued: "Queued", sent: "Sent", delivered: "Delivered", read: "Read", failed: "Failed", expired: "Expired",
  };

  function safeGuestCopy(value, limit) {
    return (typeof value === "string" || typeof value === "number" ? String(value) : "").slice(0, limit);
  }

  function setGuestToolsStatus(message) {
    $("guest-tools-status").textContent = message;
  }

  function normalizeGuestNotification(row) {
    if (!row || typeof row !== "object" || typeof row.notification_id !== "string" || !row.notification_id.trim()) return null;
    return {
      notification_id: row.notification_id.slice(0, 240),
      title: safeGuestCopy(row.title, 160),
      body: safeGuestCopy(row.body, 2000),
      status: notificationStatuses.has(row.status) ? row.status : "queued",
    };
  }

  function renderGuestInbox() {
    const list = $("guest-inbox-list");
    const empty = $("guest-inbox-empty");
    list.replaceChildren();
    empty.hidden = guestNotifications.length !== 0;
    for (const notification of guestNotifications) {
      const item = element("li", "guest-inbox-item");
      const heading = element("div", "guest-inbox-item-header");
      const title = element("h4", "", notification.title || "Stay update");
      const status = element("span", "guest-inbox-status", notificationStatusLabels[notification.status]);
      heading.append(title, status);
      item.appendChild(heading);
      item.appendChild(element("p", "", notification.body));
      if (notification.status === "delivered") {
        const readButton = element("button", "", "Mark as read");
        readButton.type = "button";
        readButton.addEventListener("click", () => markGuestNotificationRead(notification, readButton));
        item.appendChild(readButton);
      }
      list.appendChild(item);
    }
  }

  function renderGuestPreferences(preferences, canManage = false) {
    guestNotificationPreferences = { ...notificationPreferenceDefaults };
    if (preferences && typeof preferences === "object" && !Array.isArray(preferences)) {
      for (const category of Object.keys(notificationPreferenceDefaults)) {
        if (typeof preferences[category] === "boolean") guestNotificationPreferences[category] = preferences[category];
      }
    }
    for (const input of document.querySelectorAll("[data-notification-category]")) {
      input.checked = guestNotificationPreferences[input.dataset.notificationCategory] === true;
      input.disabled = !canManage;
    }
  }

  function renderPrivacyConsents(consents) {
    guestPrivacyConsents = Object.fromEntries(privacyConsentCategories.map((category) => [category, false]));
    if (consents && typeof consents === "object" && !Array.isArray(consents)) {
      for (const category of privacyConsentCategories) {
        if (typeof consents[category] === "boolean") guestPrivacyConsents[category] = consents[category];
      }
    }
    for (const input of document.querySelectorAll("[data-consent-category]")) {
      input.checked = guestPrivacyConsents[input.dataset.consentCategory] === true;
      input.disabled = false;
    }
  }

  async function loadGuestTools() {
    if (!sessionId || sessionExpired) {
      setGuestToolsStatus("Start a new private chat to manage this session's inbox and privacy choices.");
      return;
    }
    setGuestToolsStatus("Loading inbox and privacy choices…");
    $("refresh-guest-inbox").disabled = true;
    try {
      const [inbox, privacy] = await Promise.all([
        api("/api/guest/notifications"),
        api("/api/guest/privacy"),
      ]);
      guestNotifications = Array.isArray(inbox.notifications)
        ? inbox.notifications.slice(0, 100).map(normalizeGuestNotification).filter(Boolean)
        : [];
      renderGuestInbox();
      renderGuestPreferences(inbox.preferences, inbox.can_manage === true);
      renderPrivacyConsents(privacy.consents);
      setGuestToolsStatus("");

      // An in-app delivered status records this guest client acknowledging that
      // it received and rendered a dispatched item. Merely fetching queued data
      // does not change its status.
      for (const notification of guestNotifications.filter((item) => item.status === "sent")) {
        try {
          await requestBody(`/api/guest/notifications/${encodeURIComponent(notification.notification_id)}/ack`, { action: "delivered" });
          notification.status = "delivered";
          renderGuestInbox();
        } catch { /* Keep the item marked sent until the client can acknowledge receipt. */ }
      }
    } catch {
      setGuestToolsStatus("Inbox or privacy choices could not be loaded. Select Refresh to try again.");
      guestNotifications = [];
      renderGuestInbox();
    } finally {
      $("refresh-guest-inbox").disabled = false;
    }
  }

  async function markGuestNotificationRead(notification, button) {
    button.disabled = true;
    try {
      await requestBody(
        `/api/guest/notifications/${encodeURIComponent(notification.notification_id)}/ack`,
        { action: "read" },
      );
      notification.status = "read";
      renderGuestInbox();
      setGuestToolsStatus("Notification marked as read by this guest client.");
    } catch {
      button.disabled = false;
      setGuestToolsStatus("That notification could not be marked as read. Please try again.");
    }
  }

  function setupGuestTools() {
    const dialog = $("guest-tools-dialog");
    const openButton = $("open-guest-tools");
    const closeButton = $("close-guest-tools");
    const closeDialog = () => {
      if (dialog.open) dialog.close();
      openButton.setAttribute("aria-expanded", "false");
    };
    openButton.addEventListener("click", () => {
      if (!dialog.open) dialog.showModal();
      openButton.setAttribute("aria-expanded", "true");
      void loadGuestTools();
    });
    closeButton.addEventListener("click", closeDialog);
    dialog.addEventListener("close", () => openButton.setAttribute("aria-expanded", "false"));
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) closeDialog();
    });
    $("refresh-guest-inbox").addEventListener("click", loadGuestTools);

    for (const input of document.querySelectorAll("[data-notification-category]")) {
      input.addEventListener("change", async () => {
        const category = input.dataset.notificationCategory;
        const enabled = input.checked;
        input.disabled = true;
        try {
          await api("/api/guest/notifications/preferences", {
            method: "PUT", body: JSON.stringify({ category, enabled }),
          });
          guestNotificationPreferences[category] = enabled;
          setGuestToolsStatus("Notification preference saved.");
        } catch {
          input.checked = !enabled;
          setGuestToolsStatus("That notification preference could not be saved. Please try again.");
        } finally {
          input.disabled = false;
        }
      });
    }

    $("save-privacy-choices").addEventListener("click", async () => {
      const button = $("save-privacy-choices");
      const consents = Object.fromEntries(privacyConsentCategories.map((category) => [
        category, document.querySelector(`[data-consent-category="${category}"]`).checked,
      ]));
      button.disabled = true;
      try {
        const result = await api("/api/guest/privacy", {
          method: "PUT",
          body: JSON.stringify({ session_id: sessionId, consents }),
        });
        renderPrivacyConsents(result.consents || consents);
        setGuestToolsStatus("Privacy choices saved.");
      } catch {
        setGuestToolsStatus("Privacy choices could not be saved. Please try again.");
      } finally {
        button.disabled = false;
      }
    });
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
      // Reserve the card's 16:10 image box before the lazy remote image loads.
      image.width = 160;
      image.height = 100;
      image.src = imageUrl;
      image.alt = "";
      image.loading = "lazy";
      image.decoding = "async";
      image.referrerPolicy = "no-referrer";
      image.addEventListener("error", () => image.remove(), { once: true });
      article.appendChild(image);
      if (card.image_label) article.appendChild(element("p", "entity-card-image-caption", card.image_label));
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
                const menuImageUrl = safeApprovedHttpsUrl(item.image_url);
                if (menuImageUrl) {
                  const image = document.createElement("img");
                  image.className = "menu-item-image";
                  image.src = menuImageUrl;
                  image.alt = String(item.name || "Menu item").slice(0, 160);
                  image.loading = "lazy";
                  image.decoding = "async";
                  image.referrerPolicy = "no-referrer";
                  entry.appendChild(image);
                }
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
      const item = attachSourceIds(element("li", "", step.instruction || step.label), step.source_ids);
      list.appendChild(item);
    }
    panel.appendChild(list);
    parent.appendChild(panel);
  }

  function renderMapView(parent, block) {
    const panel = attachSourceIds(element("section", "map-panel"), block.source_ids);
    const floorViews = Array.isArray(block.floors) && block.floors.length
      ? block.floors
      : [{
        floor_id: block.floor_id || "current-floor",
        label: block.floor_label || block.title,
        map_image_url: block.map_image_url,
        image_width: block.image_width,
        image_height: block.image_height,
        markers: block.markers || [],
        synthetic_demo: block.synthetic_demo === true,
        source_ids: block.source_ids || [],
      }];
    const resolvedInitialFloor = floorViews.find((floor) => floor.floor_id === block.floor_id)
      || (floorViews.length === 1 && !block.floor_id ? floorViews[0] : null);
    const initialFloorId = resolvedInitialFloor?.floor_id || "";
    const preferredStartNodeId = block.starting_node_id || "";
    const initialMarkerId = !preferredStartNodeId
      && resolvedInitialFloor?.markers?.some((marker) => marker.id === block.focused_marker_id)
      ? block.focused_marker_id : "";
    const mapKey = String(block.id || "");
    const rememberedState = mapViewStates.get(mapKey);
    let selectedFloorId = floorViews.some((floor) => floor.floor_id === rememberedState?.floorId)
      ? rememberedState.floorId : initialFloorId;
    const rememberedFloor = floorViews.find((floor) => floor.floor_id === selectedFloorId);
    let selectedMarkerId = rememberedState?.floorId === selectedFloorId
      && rememberedFloor?.markers?.some((marker) => marker.id === rememberedState.markerId)
      ? rememberedState.markerId
      : (selectedFloorId === initialFloorId ? initialMarkerId : "");
    let zoom = Number.isFinite(rememberedState?.zoom) ? Math.max(1, Math.min(3, rememberedState.zoom)) : 1;
    const heading = element("h3", "", block.title);
    panel.appendChild(heading);

    const toolbar = element("div", "floor-map-toolbar");
    if (floorViews.length > 1) {
      const floorField = element("label", "floor-map-floor-field");
      floorField.appendChild(element("span", "", "Floor"));
      const floorSelect = document.createElement("select");
      floorSelect.setAttribute("aria-label", "Choose a floor");
      if (!selectedFloorId) {
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "Choose a floor";
        floorSelect.appendChild(placeholder);
      }
      for (const floor of floorViews) {
        const option = document.createElement("option");
        option.value = floor.floor_id;
        option.textContent = floor.label;
        floorSelect.appendChild(option);
      }
      floorSelect.value = selectedFloorId;
      floorSelect.addEventListener("change", () => {
        selectedFloorId = floorSelect.value;
        selectedMarkerId = selectedFloorId === initialFloorId ? initialMarkerId : "";
        zoom = 1;
        drawFloor();
      });
      floorField.appendChild(floorSelect);
      toolbar.appendChild(floorField);
    }
    const zoomControls = element("div", "floor-map-zoom-controls");
    const zoomOut = element("button", "", "−");
    zoomOut.type = "button";
    zoomOut.setAttribute("aria-label", "Zoom out");
    const zoomLabel = element("span", "floor-map-zoom-label", "100%");
    const zoomIn = element("button", "", "+");
    zoomIn.type = "button";
    zoomIn.setAttribute("aria-label", "Zoom in");
    const zoomReset = element("button", "floor-map-reset", "Reset");
    zoomReset.type = "button";
    zoomReset.setAttribute("aria-label", "Reset map view");
    zoomControls.append(zoomOut, zoomLabel, zoomIn, zoomReset);
    toolbar.appendChild(zoomControls);
    panel.appendChild(toolbar);

    const viewport = element("div", "floor-map-viewport");
    viewport.tabIndex = 0;
    viewport.setAttribute("role", "group");
    viewport.setAttribute("aria-label", block.map_alt || "Interactive hotel floor map");
    const figure = element("figure", "floor-map-figure");
    figure.appendChild(viewport);
    panel.appendChild(figure);
    const demoNote = element("p", "floor-map-demo-note", "");
    demoNote.setAttribute("role", "note");
    panel.appendChild(demoNote);
    const selectedAnnouncement = element("p", "floor-map-selection", "");
    selectedAnnouncement.setAttribute("aria-live", "polite");
    selectedAnnouncement.setAttribute("aria-atomic", "true");
    panel.appendChild(selectedAnnouncement);

    const places = element("div", "floor-map-location-list");
    places.setAttribute("role", "group");
    places.setAttribute("aria-label", "Places on this floor");
    panel.appendChild(places);
    const floorAlternative = element("p", "floor-map-alternative", "");
    panel.appendChild(floorAlternative);
    const details = element("section", "floor-map-facility-detail");
    details.setAttribute("aria-live", "polite");
    details.setAttribute("aria-atomic", "true");
    panel.appendChild(details);

    let startSelect = null;
    let directionsForm = null;
    if (block.directions_enabled) {
      directionsForm = element("form", "floor-map-directions");
      directionsForm.appendChild(element("h4", "", "Get directions"));
      directionsForm.appendChild(element("p", "", "Choose a starting location and a destination on the map. Routes between floors use a published lift, stair, or ramp connection."));
      const startLabel = element("label", "floor-map-floor-field");
      startLabel.appendChild(element("span", "", "Starting location · any mapped floor"));
      startSelect = document.createElement("select");
      startSelect.setAttribute("aria-label", "Starting location");
      const emptyOption = document.createElement("option");
      emptyOption.value = "";
      emptyOption.textContent = "Choose a place";
      startSelect.appendChild(emptyOption);
      startLabel.appendChild(startSelect);
      const accessibleLabel = element("label", "floor-map-accessible-choice");
      const accessibleInput = document.createElement("input");
      accessibleInput.type = "checkbox";
      accessibleInput.setAttribute("aria-label", "Wheelchair accessible route");
      accessibleLabel.append(accessibleInput, element("span", "", "Wheelchair accessible route"));
      const routeButton = element("button", "floor-map-directions-submit", "Check for a route");
      routeButton.type = "submit";
      directionsForm.append(startLabel, accessibleLabel, routeButton);
      directionsForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const floor = floorViews.find((item) => item.floor_id === selectedFloorId);
        const startFloor = floorViews.find((item) => item.markers?.some((marker) => marker.id === startSelect.value));
        const start = startFloor?.markers?.find((marker) => marker.id === startSelect.value);
        const destination = floor?.markers?.find((marker) => marker.id === selectedMarkerId);
        if (!start || !destination || start.id === destination.id) {
          startSelect.focus();
          return;
        }
        const routePrefix = accessibleInput.checked ? "Accessible route" : "Directions";
        sendMessage(`${routePrefix} from ${start.label} on ${startFloor.label} to ${destination.label}`);
      });
      panel.appendChild(directionsForm);
    }

    function currentFloor() {
      return floorViews.find((floor) => floor.floor_id === selectedFloorId) || {
        floor_id: "",
        label: "Map location unavailable",
        markers: [],
        synthetic_demo: false,
      };
    }

    function rememberMapView() {
      if (mapKey) mapViewStates.set(mapKey, { floorId: selectedFloorId, markerId: selectedMarkerId, zoom });
    }

    function updateZoom() {
      zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
      zoomOut.disabled = zoom <= 1;
      zoomIn.disabled = zoom >= 3;
      const artboard = viewport.querySelector(".floor-map-artboard");
      if (artboard) {
        artboard.style.width = `${zoom * 100}%`;
        artboard.style.height = `${zoom * 100}%`;
      }
      rememberMapView();
    }
    zoomOut.addEventListener("click", () => { zoom = Math.max(1, Math.round((zoom - 0.25) * 100) / 100); updateZoom(); });
    zoomIn.addEventListener("click", () => { zoom = Math.min(3, Math.round((zoom + 0.25) * 100) / 100); updateZoom(); });
    zoomReset.addEventListener("click", () => {
      zoom = 1;
      selectedFloorId = initialFloorId;
      selectedMarkerId = initialMarkerId;
      rememberMapView();
      const floorSelect = toolbar.querySelector('select[aria-label="Choose a floor"]');
      if (floorSelect) floorSelect.value = selectedFloorId;
      drawFloor();
      viewport.scrollTo({ top: 0, left: 0, behavior: "smooth" });
    });
    viewport.addEventListener("keydown", (event) => {
      if (event.key === "+" || event.key === "=") { zoom = Math.min(3, zoom + 0.25); updateZoom(); }
      if (event.key === "-") { zoom = Math.max(1, zoom - 0.25); updateZoom(); }
    });

    function iconFor(label) {
      const name = label.toLowerCase();
      if (name.includes("pool") || name.includes("swim")) return "≈";
      if (name.includes("fitness") || name.includes("gym")) return "✳";
      if (name.includes("kids") || name.includes("child")) return "☆";
      if (name.includes("elevator")) return "↕";
      return "•";
    }

    function updateDetails(marker, floor) {
      const location = (block.locations || []).find((item) => item.marker_id === marker.id);
      details.replaceChildren();
      const content = location || {
        title: marker.label,
        description: "This location is marked on the selected floor.",
        floor_label: floor.label,
        location: floor.label,
        hours: "",
        policies: [],
        image_url: "",
        image_label: "",
        source_ids: marker.source_ids,
      };
      attachSourceIds(details, content.source_ids);
      details.appendChild(element("h4", "", content.title));
      const imageUrl = safeApprovedHttpsUrl(content.image_url);
      if (imageUrl) {
        const image = document.createElement("img");
        image.className = "floor-map-facility-image";
        image.src = imageUrl;
        image.alt = content.title;
        image.loading = "lazy";
        image.decoding = "async";
        image.referrerPolicy = "no-referrer";
        image.addEventListener("error", () => image.remove(), { once: true });
        details.appendChild(image);
        if (content.image_label) details.appendChild(element("p", "entity-card-image-caption", content.image_label));
      }
      if (content.description) details.appendChild(element("p", "", content.description));
      if (content.floor_label) details.appendChild(element("p", "floor-map-detail-line", `Floor: ${content.floor_label}`));
      if (content.location && content.location.toLowerCase() !== String(content.floor_label || "").toLowerCase()) {
        details.appendChild(element("p", "floor-map-detail-line", `Location: ${content.location}`));
      }
      if (content.hours) details.appendChild(element("p", "floor-map-detail-line", `Hours: ${content.hours}`));
      if (content.policies?.length) {
        const list = element("ul", "card-policies");
        list.setAttribute("aria-label", "Guest policies");
        for (const policy of content.policies) list.appendChild(element("li", "", policy));
        details.appendChild(list);
      }
      if (block.directions_enabled && selectedFloorId && selectedMarkerId) {
        const directionsButton = element("button", "floor-map-directions-link", "Get directions");
        directionsButton.type = "button";
        directionsButton.addEventListener("click", () => {
          directionsForm?.scrollIntoView({ behavior: "smooth", block: "nearest" });
          startSelect?.focus();
        });
        details.appendChild(directionsButton);
      }
    }

    function drawFloor() {
      const floor = currentFloor();
      const markers = Array.isArray(floor.markers) ? floor.markers : [];
      floorAlternative.textContent = markers.length
        ? `Places on this floor: ${markers.map((marker) => marker.label).join(", ")}.`
        : "No guest-visible places are available on this floor.";
      if (!markers.some((marker) => marker.id === selectedMarkerId)) selectedMarkerId = "";
      heading.textContent = selectedFloorId ? `Hotel map · ${floor.label}` : "Hotel map";
      demoNote.hidden = !floor.synthetic_demo;
      demoNote.textContent = floor.synthetic_demo
        ? "Demo map — illustrative layout"
        : "";
      viewport.className = `floor-map-viewport${floor.synthetic_demo ? " floor-map-synthetic" : ""}`;
      viewport.replaceChildren();
      places.replaceChildren();
      const canvas = element("div", "floor-map-artboard");
      if (!floor.synthetic_demo) canvas.style.aspectRatio = `${floor.image_width} / ${floor.image_height}`;

      const syntheticPositions = new Map();
      let corridorY = 52;
      if (floor.synthetic_demo && markers.length) {
        const xs = markers.map((marker) => Number(marker.x_percent) || 0);
        const ys = markers.map((marker) => Number(marker.y_percent) || 0);
        const minX = Math.min(...xs), maxX = Math.max(...xs);
        const minY = Math.min(...ys), maxY = Math.max(...ys);
        const xSpan = Math.max(maxX - minX, 1);
        const ySpan = maxY - minY;
        const contentRatio = (xSpan + 34) / (Math.max(ySpan, 18) + 30);
        viewport.style.setProperty("--synthetic-map-ratio", String(Math.max(1.3, Math.min(2.05, contentRatio))));
        corridorY = ySpan > 12 ? Math.max(48, Math.min(58, minY + ySpan * 0.58)) : 56;
        for (const marker of markers) {
          const x = 16 + ((Number(marker.x_percent) - minX) / xSpan) * 68;
          const y = ySpan > 12
            ? 28 + ((Number(marker.y_percent) - minY) / ySpan) * 42
            : 34;
          syntheticPositions.set(marker.id, { x, y });
        }
      } else {
        viewport.style.removeProperty("--synthetic-map-ratio");
      }

      if (floor.synthetic_demo) {
        const drawing = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        drawing.setAttribute("class", "floor-plan-decoration");
        drawing.setAttribute("viewBox", "0 0 100 100");
        drawing.setAttribute("preserveAspectRatio", "none");
        drawing.setAttribute("aria-hidden", "true");
        const perimeter = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        perimeter.setAttribute("x", "4"); perimeter.setAttribute("y", "7");
        perimeter.setAttribute("width", "92"); perimeter.setAttribute("height", "86");
        perimeter.setAttribute("rx", "2"); perimeter.setAttribute("class", "floor-plan-perimeter");
        const corridor = document.createElementNS("http://www.w3.org/2000/svg", "path");
        const corridors = [`M 8 ${corridorY} H 92`];
        for (const marker of markers) {
          const position = syntheticPositions.get(marker.id) || { x: marker.x_percent, y: marker.y_percent };
          const x = Math.max(5, Math.min(95, position.x));
          const y = Math.max(8, Math.min(92, position.y));
          corridors.push(y < corridorY ? `M ${x} ${y + 11} V ${corridorY}` : `M ${x} ${corridorY} V ${y - 11}`);
        }
        corridor.setAttribute("d", corridors.join(" "));
        corridor.setAttribute("class", "floor-plan-corridor");
        drawing.append(perimeter, corridor);
        canvas.appendChild(drawing);
      } else {
        const image = document.createElement("img");
        image.className = "floor-map-image";
        image.src = safeApprovedHttpsUrl(floor.map_image_url);
        image.alt = floor.synthetic_demo ? "Synthetic demo floor plan" : (block.map_alt || floor.label);
        image.loading = "lazy";
        image.decoding = "async";
        image.referrerPolicy = "no-referrer";
        image.addEventListener("error", () => {
          image.hidden = true;
          viewport.classList.add("floor-map-unavailable");
          viewport.setAttribute("aria-label", `${floor.label} map image is unavailable. Use the place list below.`);
        }, { once: true });
        canvas.appendChild(image);
      }

      const routeMarkers = (block.route_node_ids || []).map((id) => markers.find((marker) => marker.id === id)).filter(Boolean);
      if (routeMarkers.length >= 2) {
        const routeSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        routeSvg.setAttribute("class", "floor-map-route-overlay");
        routeSvg.setAttribute("viewBox", "0 0 100 100");
        routeSvg.setAttribute("preserveAspectRatio", "none");
        routeSvg.setAttribute("aria-hidden", "true");
        const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
        line.setAttribute("points", routeMarkers.map((marker) => {
          const position = floor.synthetic_demo
            ? (syntheticPositions.get(marker.id) || marker)
            : marker;
          return `${position.x ?? position.x_percent},${position.y ?? position.y_percent}`;
        }).join(" "));
        line.setAttribute("class", "floor-map-route-line");
        routeSvg.appendChild(line);
        canvas.appendChild(routeSvg);
      }

      const markerLayer = element("div", "floor-map-markers");
      markers.forEach((marker, index) => {
        const button = element("button", floor.synthetic_demo ? "floor-map-room" : "floor-map-marker", "");
        attachSourceIds(button, marker.source_ids);
        button.type = "button";
        const position = floor.synthetic_demo
          ? (syntheticPositions.get(marker.id) || marker)
          : marker;
        button.style.left = `${position.x ?? marker.x_percent}%`;
        button.style.top = `${position.y ?? marker.y_percent}%`;
        button.setAttribute("aria-label", `Show location: ${marker.label}, ${floor.label}`);
        button.setAttribute("aria-pressed", String(marker.id === selectedMarkerId));
        if (floor.synthetic_demo) {
          const symbol = element("span", "floor-map-room-symbol", iconFor(marker.label));
          symbol.setAttribute("aria-hidden", "true");
          button.appendChild(symbol);
          button.appendChild(element("span", "floor-map-room-label", marker.label));
        } else {
          button.textContent = String(index + 1);
        }
        button.addEventListener("click", () => {
          selectedMarkerId = marker.id;
          drawFloor();
        });
        markerLayer.appendChild(button);
        const placeButton = element("button", "floor-map-place-option", marker.label);
        placeButton.type = "button";
        placeButton.setAttribute("aria-pressed", String(marker.id === selectedMarkerId));
        placeButton.addEventListener("click", () => { selectedMarkerId = marker.id; drawFloor(); });
        places.appendChild(placeButton);
      });
      canvas.appendChild(markerLayer);
      viewport.appendChild(canvas);
      if (startSelect) {
        const currentStart = startSelect.value || preferredStartNodeId;
        startSelect.replaceChildren();
        const placeholder = document.createElement("option");
        placeholder.value = ""; placeholder.textContent = "Choose a place"; startSelect.appendChild(placeholder);
        for (const marker of floorViews.flatMap((item) => item.markers || [])) {
          if (marker.id === selectedMarkerId && marker.id !== preferredStartNodeId) continue;
          const option = document.createElement("option");
          const markerFloor = floorViews.find((item) => item.markers?.some((entry) => entry.id === marker.id));
          option.value = marker.id;
          option.textContent = markerFloor ? `${marker.label} · ${markerFloor.label}` : marker.label;
          startSelect.appendChild(option);
        }
        startSelect.value = floorViews.some((item) => item.markers?.some((marker) => marker.id === currentStart && marker.id !== selectedMarkerId)) ? currentStart : "";
      }
      const selected = markers.find((marker) => marker.id === selectedMarkerId);
      if (selected) {
        selectedAnnouncement.textContent = selected.label;
        updateDetails(selected, floor);
      } else {
        const message = selectedFloorId
          ? "Choose a place on this floor to see its details."
          : "I couldn't match this location to a floor. Choose a floor to browse its places.";
        selectedAnnouncement.textContent = message;
        details.replaceChildren(element("p", "", message));
      }
      rememberMapView();
      updateZoom();
    }

    drawFloor();
    parent.appendChild(panel);
  }

  function renderFacilityDirectory(parent, block) {
    const panel = attachSourceIds(element("section", "facility-directory"), block.source_ids);
    const directoryLabel = (value) => String(value || "").replace(/_+/g, " ").replace(/\s+/g, " ").trim();
    const directoryDescription = (value) => {
      const description = String(value || "").trim();
      if (/official-directory-listed|reverify before live deployment|listed in the official directory/i.test(description)) {
        return "";
      }
      return description;
    };
    panel.appendChild(element("h3", "", block.title));
    if (block.description) panel.appendChild(element("p", "facility-directory-intro", block.description));

    const filters = element("div", "facility-directory-filters");
    const searchLabel = element("label", "facility-directory-search");
    searchLabel.appendChild(element("span", "", "Search locations"));
    const search = document.createElement("input");
    search.type = "search";
    search.maxLength = 120;
    search.autocomplete = "off";
    search.placeholder = "Name, building, floor, or category";
    search.setAttribute("aria-label", "Search locations by name, building, floor, or category");
    searchLabel.appendChild(search);
    filters.appendChild(searchLabel);

    const uniqueValues = (values) => [...new Set(values.filter(Boolean).map((value) => String(value).trim()).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b));
    function addFilter(labelText, ariaLabel, values) {
      const label = element("label", "facility-directory-filter");
      label.appendChild(element("span", "", labelText));
      const select = document.createElement("select");
      select.setAttribute("aria-label", ariaLabel);
      const all = document.createElement("option");
      all.value = "";
      all.textContent = `All ${labelText.toLowerCase()}s`;
      select.appendChild(all);
      for (const value of uniqueValues(values)) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      }
      label.appendChild(select);
      filters.appendChild(label);
      return select;
    }
    const buildingFilter = addFilter("Building", "Filter by building", block.locations.map((item) => item.building));
    const floorFilter = addFilter("Floor", "Filter by floor", block.locations.map((item) => item.floor));
    panel.appendChild(filters);

    const resultCount = element("p", "facility-directory-count", "");
    resultCount.setAttribute("role", "status");
    resultCount.setAttribute("aria-live", "polite");
    panel.appendChild(resultCount);
    const results = element("div", "facility-directory-results");
    results.setAttribute("role", "list");
    results.setAttribute("aria-label", "Facility and attraction locations");
    panel.appendChild(results);

    function renderResults() {
      const terms = search.value.trim().toLocaleLowerCase();
      const matches = block.locations.filter((item) => {
        if (buildingFilter.value && item.building !== buildingFilter.value) return false;
        if (floorFilter.value && item.floor !== floorFilter.value) return false;
        const searchable = [item.title, directoryLabel(item.category), item.building, item.floor, item.location, directoryDescription(item.description)]
          .join(" ").toLocaleLowerCase();
        return !terms || searchable.includes(terms);
      });
      results.replaceChildren();
      resultCount.textContent = `${matches.length} ${matches.length === 1 ? "location" : "locations"}`;
      if (!matches.length) {
        results.appendChild(element("p", "facility-directory-empty", "No locations match those filters."));
        return;
      }
      for (const item of matches) {
        const card = attachSourceIds(element("article", "facility-directory-card"), item.source_ids);
        card.setAttribute("role", "listitem");
        const visual = element("span", "facility-directory-placeholder", "⌖");
        visual.setAttribute("role", "img");
        visual.setAttribute("aria-label", "No cleared photo available");
        card.appendChild(visual);
        const top = element("div", "facility-directory-card-heading");
        top.appendChild(element("h4", "", item.title));
        const category = directoryLabel(item.category);
        if (category) top.appendChild(element("span", "facility-directory-category", category));
        card.appendChild(top);
        const context = [item.building, item.floor ? `Floor ${item.floor}` : ""].filter(Boolean).join(" · ");
        if (context) card.appendChild(element("p", "facility-directory-context", context));
        if (item.location) card.appendChild(element("p", "", item.location));
        const description = directoryDescription(item.description);
        if (description) card.appendChild(element("p", "facility-directory-description", description));
        if (item.listed_hours) card.appendChild(element("p", "facility-directory-hours", `Listed hours: ${item.listed_hours}`));
        const officialUrl = safeApprovedHttpsUrl(item.source_url);
        if (officialUrl) {
          const link = element("a", "facility-directory-source", "Official details");
          link.href = officialUrl;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.setAttribute("aria-label", `Official details for ${item.title} (opens in a new tab)`);
          card.appendChild(link);
        }
        results.appendChild(card);
      }
    }
    search.addEventListener("input", renderResults);
    buildingFilter.addEventListener("change", renderResults);
    floorFilter.addEventListener("change", renderResults);
    renderResults();

    if (block.map_links.length) {
      const maps = element("section", "facility-directory-maps");
      maps.appendChild(element("h4", "", "Official maps and directories"));
      for (const item of block.map_links) {
        const card = element("article", "facility-directory-map-card");
        card.appendChild(element("strong", "", item.title));
        if (item.scope) card.appendChild(element("span", "facility-directory-context", item.scope));
        if (item.license_status) {
          const licenseStatus = item.license_status.replace(/[_-]+/g, " ").trim();
          const statusText = licenseStatus.toLocaleLowerCase() === "not cleared"
            ? "Preview not available; open the official source."
            : `Map status: ${licenseStatus}`;
          card.appendChild(element("span", "facility-directory-license", statusText));
        }
        const kind = item.format === "pdf" ? "map" : "directory";
        const link = element("a", "facility-directory-source", `Open official ${kind}`);
        link.href = safeApprovedHttpsUrl(item.url);
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.setAttribute("aria-label", `Open official ${kind}: ${item.title} (opens in a new tab)`);
        card.appendChild(link);
        maps.appendChild(attachSourceIds(card, item.source_ids));
      }
      panel.appendChild(maps);
    }
    panel.appendChild(element("p", "facility-directory-note", "This directory shows published building and floor details. It does not provide indoor routes."));
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
        renderMapView(wrapper, block);
        break;
      }
      case "facility_directory": {
        renderFacilityDirectory(wrapper, block);
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
        if (block.canStartNewChat) {
          const button = element("button", "secondary-action", "Start a new chat");
          button.type = "button";
          button.addEventListener("click", startNewConversation);
          panel.appendChild(button);
        }
        wrapper.appendChild(panel);
        break;
      }
      default: wrapper.appendChild(element("p", "message-text", "This answer included an item that this interface cannot display."));
    }
    parent.appendChild(wrapper);
  }

  function findConversationAnchor() {
    const viewport = $("conversation-workspace");
    const viewportRect = viewport.getBoundingClientRect();
    const anchor = [...$("message-list").children].find((row) => row.getBoundingClientRect().bottom > viewportRect.top + 12);
    return {
      anchorId: anchor?.dataset.messageId || null,
      anchorTop: anchor ? anchor.getBoundingClientRect().top - viewportRect.top : 0,
    };
  }

  function setConversationScrollTop(viewport, value) {
    adjustingConversationScroll = true;
    viewport.scrollTop = value;
    window.requestAnimationFrame(() => { adjustingConversationScroll = false; });
  }

  function alignLatestMessage(viewport, messageId) {
    const row = [...$("message-list").children].find((item) => item.dataset.messageId === messageId);
    if (!row) return;
    const viewportTop = viewport.getBoundingClientRect().top;
    const paddingTop = Number.parseFloat(getComputedStyle(viewport).scrollPaddingTop) || 0;
    const delta = row.getBoundingClientRect().top - viewportTop - paddingTop;
    if (Math.abs(delta) > 1) setConversationScrollTop(viewport, viewport.scrollTop + delta);
    conversationReadingAnchor = findConversationAnchor();
  }

  function preserveConversationAnchor(viewport, anchorId, anchorTop) {
    if (!anchorId) return;
    const anchor = [...$("message-list").children].find((row) => row.dataset.messageId === anchorId);
    if (!anchor) return;
    const viewportTop = viewport.getBoundingClientRect().top;
    const delta = anchor.getBoundingClientRect().top - viewportTop - anchorTop;
    if (Math.abs(delta) > 1) setConversationScrollTop(viewport, viewport.scrollTop + delta);
    conversationReadingAnchor = findConversationAnchor();
  }

  function restoreConversationPosition(position, forceLatest = false, latestMessageId = "") {
    window.requestAnimationFrame(() => {
      const { viewport, shouldFollowLatest, anchorId, anchorTop } = position;
      if (forceLatest || shouldFollowLatest) {
        alignLatestMessage(viewport, latestMessageId);
        return;
      }
      preserveConversationAnchor(viewport, anchorId, anchorTop);
    });
  }

  function renderMessages({ forceLatest = false } = {}) {
    const viewport = $("conversation-workspace");
    const nearBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 96;
    const priorAnchor = conversationReadingAnchor || findConversationAnchor();
    const position = {
      viewport,
      shouldFollowLatest: followLatestConversation || nearBottom,
      anchorId: priorAnchor.anchorId,
      anchorTop: priorAnchor.anchorTop,
    };
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
    if (hasMessages) restoreConversationPosition(position, forceLatest, messages.at(-1)?.id || "");
    else conversationReadingAnchor = null;
    if (conversationResizeObserver) {
      conversationResizeObserver.disconnect();
      conversationResizeObserver.observe(list);
      for (const row of list.children) conversationResizeObserver.observe(row);
    }
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
      const referenceId = String(result.request.request_id || "").slice(0, 120);
      const message = messages.find((item) => item.blocks?.some((candidate) => candidate.type === "request_review" && candidate.confirmation_token === token));
      if (message) message.blocks = [{
        id: newId(), type: "verified_confirmation",
        title: result.status === "existing" ? "Your request is already with the hotel team" : "Your request has been sent",
        detail: [requestType, detail, referenceId ? `Reference: ${referenceId}` : ""].filter(Boolean).join(" · "),
        source_ids: Array.isArray(result.source_ids) ? result.source_ids : [],
      }];
      persistMessages();
      renderMessages();
    } catch (error) {
      if (error.status === 409 || error.status === 401) invalidActions.add(token);
      if (error.status === 401) sessionExpired = true;
      const message = messages.find((item) => item.blocks?.some((candidate) => candidate.type === "request_review" && candidate.confirmation_token === token));
      if (message) {
        message.blocks.push({ id: newId(), type: "error_state", canStartNewChat: error.status === 401, message: error.status === 401
          ? "Your concierge session has expired. This request was not sent. Start a new chat to continue."
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
    const originalText = String(rawMessage || "");
    const message = originalText.trim();
    if (!message || inputPending || !sessionId || sessionExpired) return;
    const previousAssistant = messages.at(-1);
    const previousGuest = messages.at(-2);
    const previousText = previousGuest?.blocks?.filter((block) => block.type === "text").map((block) => block.content).join("\n");
    const retrying = previousGuest?.role === "guest" && previousAssistant?.role === "assistant"
      && previousText === message && previousGuest.turnId
      && previousAssistant.blocks?.some((block) => block.type === "error_state");
    const history = (retrying ? messages.slice(0, -2) : messages).flatMap((item) => {
      const role = item.role === "guest" ? "guest" : "assistant";
      const text = (item.blocks || []).filter((block) => block?.type === "text" && typeof block.content === "string")
        .map((block) => block.content.trim()).filter(Boolean).join("\n");
      return text ? [{ role, content: text.slice(0, 2000) }] : [];
    }).slice(-10);
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
    // A submitted turn should follow the reply only when the guest was already
    // reading the latest messages. Capture this before the new rows change the
    // scroll height; scroll events from the subsequent render arrive too late.
    const viewport = $("conversation-workspace");
    followLatestConversation = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 96;
    conversationReadingAnchor = followLatestConversation ? null : findConversationAnchor();
    inputPending = true;
    const input = $("composer-input");
    if (input.value === originalText) input.value = "";
    updateComposer();
    $("conversation-status").hidden = false;
    $("conversation-status-copy").textContent = "The concierge is checking that for you.";
    $("cancel-response").hidden = false;
    renderMessages({ forceLatest: followLatestConversation });
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
    } catch (error) {
      const input = $("composer-input");
      if (!input.value) input.value = originalText;
      if (error.status === 401) sessionExpired = true;
      assistantMessage.blocks = [{
        id: newId(), type: "error_state", canStartNewChat: error.status === 401,
        message: error.status === 401
          ? "Your concierge session has expired. Your message was not sent. Start a new chat to continue."
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
    $("send-button").disabled = inputPending || !input.value.trim() || !sessionId || sessionExpired;
  }

  async function startSession() {
    const savedSession = sessionStorage.getItem(storageKeys.session);
    const savedProperty = sessionStorage.getItem(storageKeys.property);
    if (savedSession && savedProperty === property.property_id) {
      try {
        const resumed = await requestBody("/api/session/resume", { client_id: clientId, session_id: savedSession });
        sessionId = resumed.session_id;
        sessionExpired = false;
        await restoreMessages();
        return;
      } catch (error) {
        if (error.status !== 401) throw error;
        sessionId = savedSession;
        sessionExpired = true;
        sessionStorage.removeItem(storageKeys.session);
        sessionStorage.removeItem(storageKeys.property);
        sessionStorage.removeItem(storageKeys.messages(savedSession));
        messages = [{
          id: newId(), role: "assistant", blocks: [{ id: newId(), type: "error_state", canStartNewChat: true,
            message: "Your concierge session has expired. Start a new chat to continue." }],
        }];
        return;
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
    sessionExpired = false;
    sessionStorage.setItem(storageKeys.session, sessionId);
    sessionStorage.setItem(storageKeys.property, property.property_id);
    messages = [];
  }

  async function showWayfindingStart() {
    const context = wayfindingStartContext();
    if (!context) return;
    if (context.nodeId && messages.some((message) =>
      (message.blocks || []).some((block) => block.type === "map_view" && block.starting_node_id === context.nodeId))) return;
    if (context.invalid && messages.some((message) =>
      (message.blocks || []).some((block) => block.id === "wayfinding-invalid"))) return;

    let blocks;
    if (context.invalid) {
      blocks = [{
        id: "wayfinding-invalid",
        type: "text",
        content: "This wayfinding code is incomplete. Please ask the hotel team for directions.",
      }];
    } else {
      try {
        const query = new URLSearchParams({
          property_id: property.property_id,
          start_node_id: context.nodeId,
          start_sig: context.signature,
        });
        const result = await api(`/api/guest/wayfinding/start?${query.toString()}`);
        const map = validateBlock(result.map);
        if (map.type !== "map_view" || map.starting_node_id !== context.nodeId) throw new Error("Unavailable wayfinding entry.");
        const label = validText(result.starting_node?.label, 120) ? result.starting_node.label : "the marked location";
        const floor = validText(result.map.floor_label, 120) ? ` on ${result.map.floor_label}` : "";
        blocks = [
          { id: newId(), type: "text", content: `Your starting point is ${label}${floor}. Choose a destination on the map to request directions.` },
          map,
        ];
      } catch {
        blocks = [{ id: newId(), type: "text", content: "This wayfinding code is no longer available. Please ask the hotel team for directions." }];
      }
    }
    messages.push({ id: newId(), role: "assistant", blocks });
    persistMessages();
  }

  async function startNewConversation() {
    if (inputPending || !property) return;
    const oldSession = sessionId;
    $("new-conversation").disabled = true;
    try {
      // Keep the current credentials usable until the replacement exists.
      const created = await requestBody("/api/session/start", {
        client_id: clientId,
        property_id: property.property_id,
        gateway_context: gatewayContext(),
      });
      let oldSessionEnded = true;
      if (oldSession && !sessionExpired) {
        try {
          await requestBody("/api/session/end", { client_id: clientId, session_id: oldSession });
        } catch (error) {
          if (error.status !== 401) oldSessionEnded = false;
        }
      }
      sessionId = created.session_id;
      sessionExpired = false;
      sessionStorage.setItem(storageKeys.session, sessionId);
      sessionStorage.setItem(storageKeys.property, property.property_id);
      messages = [];
      mapViewStates.clear();
      guestNotifications = [];
      guestNotificationPreferences = {};
      guestPrivacyConsents = {};
      await showWayfindingStart();
      if ($("guest-tools-dialog").open) $("guest-tools-dialog").close();
      $("open-guest-tools").setAttribute("aria-expanded", "false");
      $("composer-input").value = "";
      $("conversation-workspace").scrollTop = 0;
      renderMessages();
      updateComposer();
      $("composer-input").focus({ preventScroll: true });
      if (!oldSessionEnded) {
        $("conversation-status").hidden = false;
        $("conversation-status-copy").textContent = "Your new conversation is ready, but the previous session could not be closed. Contact the Front Desk if you need it revoked now.";
      }
    } catch {
      $("conversation-status").hidden = false;
      $("conversation-status-copy").textContent = "A new private conversation couldn't be started. Your current conversation remains available.";
    } finally {
      $("new-conversation").disabled = false;
    }
  }

  function setupComposer() {
    setupGuestTools();
    const input = $("composer-input");
    const conversationViewport = $("conversation-workspace");
    conversationViewport.addEventListener("scroll", () => {
      if (adjustingConversationScroll) return;
      followLatestConversation = conversationViewport.scrollHeight
        - conversationViewport.scrollTop - conversationViewport.clientHeight < 96;
      conversationReadingAnchor = findConversationAnchor();
    }, { passive: true });
    if ("ResizeObserver" in window) {
      conversationResizeObserver = new ResizeObserver(() => {
        if (adjustingConversationScroll || !messages.length) return;
        window.requestAnimationFrame(() => {
          if (followLatestConversation) alignLatestMessage(conversationViewport, messages.at(-1)?.id || "");
          else if (conversationReadingAnchor) {
            preserveConversationAnchor(conversationViewport, conversationReadingAnchor.anchorId, conversationReadingAnchor.anchorTop);
          }
        });
      });
    }
    let composing = false;
    input.addEventListener("compositionstart", () => { composing = true; });
    input.addEventListener("compositionend", () => { composing = false; });
    input.addEventListener("input", updateComposer);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && !composing && !event.isComposing && event.keyCode !== 229) {
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
      await showWayfindingStart();
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
