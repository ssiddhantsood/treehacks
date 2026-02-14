const API_BASE = "http://localhost:4000";

const healthEl = document.getElementById("health-status");
const echoForm = document.getElementById("echo-form");
const echoResult = document.getElementById("echo-result");

async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/health`);
    const data = await res.json();
    if (data.ok) {
      healthEl.textContent = "Online";
    } else {
      healthEl.textContent = "Unknown";
    }
  } catch (err) {
    healthEl.textContent = "Offline";
  }
}

async function sendEcho(message) {
  const res = await fetch(`${API_BASE}/api/echo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message })
  });
  return res.json();
}

echoForm.addEventListener("submit", async event => {
  event.preventDefault();
  const formData = new FormData(echoForm);
  const message = formData.get("message") || "";
  echoResult.textContent = "Sending...";
  try {
    const data = await sendEcho(message);
    echoResult.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    echoResult.textContent = "Request failed";
  }
});

checkHealth();
