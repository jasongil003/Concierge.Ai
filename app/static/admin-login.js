const form = document.getElementById("login-form");
const message = document.getElementById("login-message");
const password = document.getElementById("password");

document.getElementById("toggle-password").addEventListener("click", (event) => {
  const visible = password.type === "text";
  password.type = visible ? "password" : "text";
  event.currentTarget.textContent = visible ? "Show" : "Hide";
  event.currentTarget.setAttribute("aria-label", visible ? "Show password" : "Hide password");
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  message.textContent = "";
  message.className = "form-message";
  const button = document.getElementById("sign-in");
  button.disabled = true;
  button.textContent = "Signing in...";
  try {
    const response = await fetch("/api/admin/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("username").value.trim(),
        password: password.value,
        remember_me: document.getElementById("remember-me").checked,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Unable to sign in.");
    window.location.assign(data.redirect || "/admin");
  } catch (error) {
    message.textContent = error.message;
    message.className = "form-message error";
  } finally {
    button.disabled = false;
    button.textContent = "Sign In";
  }
});

const recoveryDialog = document.getElementById("recovery-dialog");
document.getElementById("forgot-password").addEventListener("click", () => {
  document.getElementById("recovery-username").value = document.getElementById("username").value;
  recoveryDialog.showModal();
});

document.getElementById("recovery-form").addEventListener("submit", async (event) => {
  if (event.submitter?.value === "cancel") return;
  event.preventDefault();
  const recoveryMessage = document.getElementById("recovery-message");
  try {
    const response = await fetch("/api/admin/auth/password-reset/request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: document.getElementById("recovery-username").value.trim() }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Unable to request a reset.");
    recoveryMessage.textContent = data.message;
  } catch (error) {
    recoveryMessage.textContent = error.message;
    recoveryMessage.className = "form-message error";
  }
});
