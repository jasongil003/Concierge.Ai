const state = {
  sessionId: null,
  hotel: null,
};

const $ = (id) => document.getElementById(id);

function addMessage(role, text) {
  const el = document.createElement("div");
  el.className = "message " + role;
  el.textContent = text;
  $("messages").appendChild(el);
  $("messages").scrollTop = $("messages").scrollHeight;
}

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Request failed");
  return data;
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

async function start() {
  state.hotel = await jsonFetch("/api/hotel");
  $("hotel-name").textContent = state.hotel.name;
  $("concierge-name").textContent = state.hotel.concierge_name;

  for (const action of state.hotel.quick_actions || []) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = action.label;
    button.addEventListener("click", () => sendMessage(action.prompt));
    $("quick-actions").appendChild(button);
  }

  const existingClient = localStorage.getItem("concierge-client-id");
  const clientId = existingClient || createClientId();
  localStorage.setItem("concierge-client-id", clientId);

  const session = await jsonFetch("/api/session/start", {
    method: "POST",
    body: JSON.stringify({
      client_id: clientId,
      gateway_context: gatewayContext(),
    }),
  });
  state.sessionId = session.session_id;
  addMessage("assistant", state.hotel.welcome);
}

async function authenticate() {
  const room = $("room").value.trim();
  const lastName = $("last-name").value.trim();
  $("auth-message").textContent = "Checking...";

  try {
    const result = await jsonFetch("/api/authenticate", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        room,
        last_name: lastName,
      }),
    });

    if (result.status === "handoff_required" && result.handoff) {
      $("auth-message").textContent = "Handing authentication back to the gateway...";
      submitGatewayHandoff(result.handoff);
      return;
    }

    if (result.status === "authenticated") {
      $("wifi-status").textContent = "Connected";
      $("auth-message").textContent = result.message;
      addMessage("assistant", "You're connected in prototype mode. How can I help with your stay?");
      return;
    }

    $("auth-message").textContent = result.message;
  } catch (error) {
    $("auth-message").textContent = error.message;
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

async function sendMessage(rawMessage) {
  const message = rawMessage.trim();
  if (!message || !state.sessionId) return;

  addMessage("user", message);
  $("chat-input").value = "";

  try {
    const result = await jsonFetch("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        message,
      }),
    });
    addMessage("assistant", result.answer);
  } catch (error) {
    addMessage("assistant", error.message);
  }
}

$("connect-button").addEventListener("click", authenticate);
$("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage($("chat-input").value);
});

start().catch((error) => {
  addMessage("assistant", "Unable to start the concierge: " + error.message);
});
