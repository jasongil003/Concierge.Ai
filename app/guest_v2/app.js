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
      prompts,
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

  function isValidMessageCollection(value) {
    return Array.isArray(value) && value.length <= 80 && value.every((item) =>
      item && typeof item.id === "string" && ["guest", "assistant"].includes(item.role) && Array.isArray(item.blocks));
  }

  function restoreMessages() {
    try {
      const raw = sessionStorage.getItem(storageKeys.messages(sessionId));
      const parsed = raw ? JSON.parse(raw) : [];
      messages = isValidMessageCollection(parsed) ? parsed : [];
      if (messages.length) messages = messages.map((message) => ({ ...message, blocks: message.blocks.map(validateBlock) }));
    } catch { messages = []; }
  }

  function persistMessages() {
    if (!sessionId) return;
    const trimmed = messages.slice(-80).map((message) => ({
      ...message,
      blocks: (message.blocks || []).map((block) => {
        const clean = validateBlock(block);
        // A service proposal is bound to the active session, signed, and short lived.
        // Keeping it in tab-scoped storage permits safe recovery after refresh.
        return clean;
      }),
    }));
    messages = trimmed;
    try { sessionStorage.setItem(storageKeys.messages(sessionId), JSON.stringify(messages)); }
    catch { /* Conversation rendering remains available if browser storage is full. */ }
  }

  function validText(value, maximum = 6000) {
    return typeof value === "string" && value.length <= maximum;
  }

  function validateEntityCard(card) {
    return card && typeof card === "object"
      && ["restaurant", "facility"].includes(card.type)
      && validText(card.id, 80) && validText(card.title, 120) && card.title.trim()
      && validText(card.subtitle || "", 120) && validText(card.description || "", 500)
      && validText(card.detail || "", 300);
  }

  function validateBlock(block) {
    if (!block || typeof block !== "object" || !validText(block.id, 80)) {
      return { id: newId(), type: "unknown" };
    }
    switch (block.type) {
      case "text": return validText(block.content) ? block : { id: block.id, type: "unknown" };
      case "suggestion_chips":
        return Array.isArray(block.items) && block.items.length <= 6 && block.items.every((item) => validText(item?.label, 80) && item.label && validText(item.prompt, 300) && item.prompt)
          ? block : { id: block.id, type: "unknown" };
      case "entity_card": return validateEntityCard(block.card) ? block : { id: block.id, type: "unknown" };
      case "card_collection":
        return validText(block.title, 100) && Array.isArray(block.cards) && block.cards.length <= 8 && block.cards.every(validateEntityCard)
          ? block : { id: block.id, type: "unknown" };
      case "details_panel":
        return validText(block.title, 100) && Array.isArray(block.fields) && block.fields.length <= 12
          && block.fields.every((item) => validText(item?.label, 60) && item.label && validText(item?.value, 300))
          ? block : { id: block.id, type: "unknown" };
      case "selection_form":
        return validText(block.title, 120) && Array.isArray(block.options) && block.options.length <= 8
          && block.options.every((item) => validText(item?.label, 100) && item.label && validText(item?.value, 120) && item.value)
          ? block : { id: block.id, type: "unknown" };
      case "request_review":
        return validText(block.title, 120) && validText(block.department || "", 120)
          && validText(block.description, 1000) && validText(block.confirmation_token, 3000)
          && validText(block.confirm_label || "Confirm request", 40)
          ? block : { id: block.id, type: "unknown" };
      case "verified_confirmation":
        return validText(block.title, 120) && validText(block.detail || "", 500)
          ? block : { id: block.id, type: "unknown" };
      case "map_view":
        return validText(block.title, 120) && Number.isFinite(block.latitude) && block.latitude >= -90 && block.latitude <= 90
          && Number.isFinite(block.longitude) && block.longitude >= -180 && block.longitude <= 180 && validText(block.label || "", 120)
          ? block : { id: block.id, type: "unknown" };
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
    const article = element("article", `entity-card entity-card-${card.type}`);
    article.appendChild(element("h3", "", card.title));
    if (card.subtitle) article.appendChild(element("p", "card-subtitle", card.subtitle));
    if (card.description) article.appendChild(element("p", "card-description", card.description));
    if (card.detail) article.appendChild(element("p", "card-detail", card.detail));
    parent.appendChild(article);
  }

  function renderRequestReview(parent, block) {
    const card = element("section", "request-review");
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

  function renderBlock(parent, rawBlock) {
    const block = validateBlock(rawBlock);
    const wrapper = element("div", "message-block");
    switch (block.type) {
      case "text": wrapper.appendChild(element("p", "message-text", block.content)); break;
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
        const panel = element("section", "detail-panel");
        panel.appendChild(element("h3", "", block.title));
        const list = element("dl", "detail-list");
        for (const item of block.fields) {
          const row = element("div", "");
          row.append(element("dt", "", item.label), element("dd", "", item.value));
          list.appendChild(row);
        }
        panel.appendChild(list);
        wrapper.appendChild(panel);
        break;
      }
      case "selection_form": {
        const panel = element("section", "selection-panel");
        panel.appendChild(element("h3", "", block.title));
        const choices = element("div", "selection-options");
        for (const option of block.options) {
          const button = element("button", "", option.label);
          button.type = "button";
          button.addEventListener("click", () => sendMessage(option.label));
          choices.appendChild(button);
        }
        panel.appendChild(choices);
        wrapper.appendChild(panel);
        break;
      }
      case "request_review": renderRequestReview(wrapper, block); break;
      case "verified_confirmation": {
        const panel = element("section", "verified-confirmation");
        panel.appendChild(element("span", "confirmation-mark", "✓"));
        panel.appendChild(element("h3", "", block.title));
        if (block.detail) panel.appendChild(element("p", "", block.detail));
        wrapper.appendChild(panel);
        break;
      }
      case "map_view": {
        const panel = element("section", "map-panel");
        panel.appendChild(element("h3", "", block.title));
        panel.appendChild(element("p", "", block.label || `${block.latitude.toFixed(5)}, ${block.longitude.toFixed(5)}`));
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

  function isServiceRequest(message) {
    const asksForAction = /\b(i need|i want|send|bring|deliver|request|could i have|can i have|please get|please send|please bring|arrange)\b/i.test(message);
    const asksForFacts = /\b(what|where|when|which|hours?|open|opening|close|closing|located|location)\b/i.test(message);
    return asksForAction && !asksForFacts;
  }

  async function proposeService(message) {
    let proposal;
    try {
      proposal = await requestBody("/api/guest/actions/propose", { session_id: sessionId, message });
    } catch (error) {
      return [{ id: newId(), type: "error_state", message: error.status === 401
        ? "Your concierge session has expired. Start a new chat to continue."
        : "I couldn't verify or send that service request. Nothing has been submitted. Please try again or contact the Front Desk." }];
    }
    if (proposal.status === "proposed" && proposal.confirmation_required === true && proposal.card && typeof proposal.proposal_token === "string") {
      return [{
        id: newId(), type: "request_review", title: String(proposal.card.title || "Service request").slice(0, 120),
        department: String(proposal.card.department || "").slice(0, 120),
        description: String(proposal.card.description || message).slice(0, 1000),
        confirmation_token: proposal.proposal_token, confirm_label: "Confirm request",
      }];
    }
    if (proposal.status === "ambiguous") {
      const names = (proposal.choices || []).map((item) => [item.name, item.department].filter(Boolean).join(" · ")).filter(Boolean).slice(0, 4);
      return [{ id: newId(), type: "text", content: names.length
        ? `I found more than one matching hotel service: ${names.join(", ")}. Please tell me the exact service you'd like.`
        : "I found more than one matching service. Please contact the Front Desk so the team can confirm your request." }];
    }
    if (proposal.status === "unmatched") {
      let services = [];
      try {
        const catalog = await api("/api/guest/service-catalog");
        services = (catalog.services || []).filter((item) => item.enabled !== false && !item.archived).map((item) => String(item.name || "").trim()).filter(Boolean).slice(0, 8);
      } catch { /* The direct alternative remains safe if the catalog is unavailable. */ }
      const content = services.length
        ? `I can't submit that service because it isn't in this hotel's configured request list. I can help request: ${services.join(", ")}.`
        : "I can't submit that service because it isn't in this hotel's configured request list. Please contact the Front Desk and they can advise you.";
      return [{ id: newId(), type: "text", content }];
    }
    return [{ id: newId(), type: "error_state", message: "I couldn't match that request to an available hotel service. Please contact the Front Desk for help." }];
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
    const guestMessage = { id: newId(), role: "guest", blocks: [{ id: newId(), type: "text", content: message }] };
    messages.push(guestMessage);
    const assistantMessage = {
      id: newId(), role: "assistant",
      blocks: [{ id: newId(), type: "loading_state", message: "Checking that for you…" }],
    };
    messages.push(assistantMessage);
    inputPending = true;
    updateComposer();
    $("conversation-status").hidden = false;
    $("conversation-status").textContent = "Your message stays on screen while the concierge checks.";
    renderMessages();
    try {
      if (isServiceRequest(message)) {
        assistantMessage.blocks = await proposeService(message);
      } else {
        const result = await requestBody("/api/guest/intelligent-chat", {
          session_id: sessionId,
          message,
          mode: "auto",
          conversation_history: history,
        });
        if (result.schema_version !== "1.0" || result.conversation_id !== sessionId || typeof result.turn_id !== "string" || !Array.isArray(result.blocks) || result.blocks.length > 20) {
          throw new Error("The concierge returned a response this screen cannot safely display.");
        }
        assistantMessage.blocks = result.blocks.map(validateBlock);
      }
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
            : error.networkFailure
              ? "The connection was interrupted. Your message is still visible; reconnect and try sending it again if needed."
              : error.message || "I couldn't complete that reply. Please try again.",
      }];
      if (!error.networkFailure && error.status && error.status < 500) {
        // Keep the submitted draft for a deliberate retry.
      }
    } finally {
      inputPending = false;
      $("conversation-status").hidden = true;
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
        restoreMessages();
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
    if (oldSession) sessionStorage.removeItem(storageKeys.messages(oldSession));
    sessionStorage.removeItem(storageKeys.session);
    sessionStorage.removeItem(storageKeys.property);
    sessionId = null;
    messages = [];
    renderMessages();
    updateComposer();
    $("new-conversation").disabled = true;
    try {
      await startSession(true);
      $("composer-input").value = "";
      updateComposer();
      $("composer-input").focus({ preventScroll: true });
    } catch {
      setError("A new private conversation couldn't be started. Check your connection and reload to try again.");
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
    $("reload-page").addEventListener("click", () => window.location.reload());
    updateComposer();
  }

  async function start() {
    setupComposer();
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
