const form = document.querySelector("#upload-form");
const input = document.querySelector("#pdf-input");
const button = document.querySelector("#upload-button");
const fileSubtitle = document.querySelector("#file-subtitle");
const message = document.querySelector("#message");
const dashboardUser = document.querySelector("#dashboard-user");
const uploadLabel = document.querySelector("#upload-label");
const previousToggle = document.querySelector("#previous-toggle");
const previousPanel = document.querySelector("#previous-panel");
const previousList = document.querySelector("#previous-list");
const authModal = document.querySelector("#auth-modal");
const openAuth = document.querySelector("#open-auth");
const openSignup = document.querySelector("#open-signup");
const closeAuth = document.querySelector("#close-auth");
const authTitle = document.querySelector("#auth-title");
const loginSubmit = document.querySelector("#login-submit");
const loginEmail = document.querySelector("#login-email");
const loginPassword = document.querySelector("#login-password");
const loginMessage = document.querySelector("#login-message");
const logoutButton = document.querySelector("#logout-button");
const img = document.createElement('img');

img.src = 'static/home.png';
img.alt = 'FinSight Logo';
img.style.width = '200px';

let authMode = "login";
let previousRefreshInFlight = false;

async function readJsonResponse(response) {
  const contentType = response.headers.get("content-type") || "non-JSON";
  const text = await response.text();
  if (!text) return {};

  try {
    return JSON.parse(text);
  } catch (error) {
    const path = new URL(response.url).pathname;
    throw new Error(`Expected JSON but got ${contentType} from ${path} (HTTP ${response.status}).`);
  }
}

function getAccessToken() {
  return localStorage.getItem("access_token") || "";
}

function isLoggedIn() {
  return Boolean(getAccessToken());
}

function displayNameFromEmail(email) {
  const name = String(email || "user").split("@")[0].trim();
  return name || "user";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function authHeaders() {
  return { Authorization: `Bearer ${getAccessToken()}` };
}

function clearAuth() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("user_email");
}

function setMessage(text, isError = false) {
  if (!message) return;
  message.textContent = text;
  message.classList.toggle("error", isError);
}

function setAuthState() {
  const loggedIn = isLoggedIn();
  const userEmail = localStorage.getItem("user_email") || "";
  if (dashboardUser) {
    dashboardUser.textContent = loggedIn ? displayNameFromEmail(userEmail) : "user";
  }
  if (input) {
    input.disabled = !loggedIn;
  }
  if (uploadLabel) {
    uploadLabel.classList.toggle("locked", !loggedIn);
  }
  if (previousToggle) {
    previousToggle.classList.toggle("locked", !loggedIn);
  }
  if (openAuth) {
    openAuth.classList.toggle("hidden", loggedIn);
  }
  if (openSignup) {
    openSignup.classList.toggle("hidden", loggedIn);
  }
  if (logoutButton) {
    logoutButton.classList.toggle("hidden", !loggedIn);
  }

  if (!loggedIn) {
    if (previousPanel) {
      previousPanel.classList.add("hidden");
    }
    if (previousList) {
      previousList.innerHTML = "";
    }
    if (fileSubtitle) {
      fileSubtitle.textContent = "";
    }
    setMessage("Login or sign up before uploading PDFs.", false);
  } else {
    setMessage("", false);
  }
}

function isLandingPage() {
  const path = window.location.pathname;
  return path === "/" || path.endsWith("/index.html");
}

function openAuthModal(mode) {
  if (!authModal || !authTitle || !loginSubmit || !loginPassword || !loginMessage) return;
  authMode = mode;
  authTitle.textContent = mode === "signup" ? "Sign Up" : "Login";
  loginSubmit.textContent = mode === "signup" ? "Sign Up" : "Login";
  loginPassword.autocomplete = mode === "signup" ? "new-password" : "current-password";
  loginMessage.textContent = "";
  authModal.classList.remove("hidden");
  if (loginEmail) {
    window.setTimeout(() => loginEmail.focus(), 0);
  }
}

function requireLogin() {
  if (isLoggedIn()) return true;
  openAuthModal("login");
  return false;
}

function renderPreviousDocuments(documents) {
  if (!documents.length) {
    previousList.innerHTML = '<p class="previous-empty">No PDFs yet.</p>';
    return;
  }

  previousList.innerHTML = documents
    .map((document) => {
      const highlightedLink = document.highlighted_pdf_url
        ? `
            <a href="${document.highlighted_pdf_url}" target="_blank" rel="noreferrer">Anomaly PDF</a>
            <a href="/static/review.html?document_id=${encodeURIComponent(document.document_id)}">Human Check</a>
          `
        : `<span>Processing</span>`;
      return `
        <article class="previous-item">
          <div>
            <strong>${escapeHtml(document.filename)}</strong>
            <span>${escapeHtml(document.status)} | ${Number(document.anomaly_count || 0)} anomalies</span>
          </div>
          <div class="previous-actions">
            <a href="${document.source_pdf_url}" target="_blank" rel="noreferrer">Source</a>
            ${highlightedLink}
          </div>
        </article>
      `;
    })
    .join("");
}

async function loadPreviousDocuments() {
  if (!requireLogin()) return;
  if (previousRefreshInFlight) return;
  previousRefreshInFlight = true;
  if (previousPanel) {
    previousPanel.classList.remove("hidden");
  }
  if (previousList) {
    previousList.innerHTML = '<p class="previous-empty">Loading...</p>';
  }

  try {
    const response = await fetch("/api/v1/documents", {
      headers: authHeaders(),
    });
    const payload = await readJsonResponse(response);

    if (response.status === 401 || response.status === 403) {
      clearAuth();
      setAuthState();
      openAuthModal("login");
      throw new Error("Login expired. Please log in again.");
    }

    if (!response.ok) {
      throw new Error(payload?.error?.message || "Could not load previous PDFs.");
    }

    renderPreviousDocuments(payload.documents || []);
  } finally {
    previousRefreshInFlight = false;
  }
}

if (input && form && button && uploadLabel) {
  input.addEventListener("change", () => {
    if (!requireLogin()) {
      input.value = "";
      return;
    }

    const file = input.files?.[0];
    if (!file) return;
    if (fileSubtitle) {
      fileSubtitle.textContent = `${file.name} | ${Math.max(1, Math.round(file.size / 1024))} KB selected`;
    }
    setMessage("", false);
    form.requestSubmit();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!requireLogin()) return;

    const file = input.files?.[0];
    if (!file) {
      setMessage("Select a PDF first.", true);
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    button.disabled = true;
    uploadLabel.classList.add("busy");
    setMessage("Uploading PDF and starting the pipeline...", false);

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 20000);

    try {
      const response = await fetch("/api/v1/documents/upload", {
        method: "POST",
        headers: authHeaders(),
        body: formData,
        signal: controller.signal,
      });

      const payload = await readJsonResponse(response);

      if (response.status === 401 || response.status === 403) {
        clearAuth();
        setAuthState();
        openAuthModal("login");
        throw new Error("Login expired. Please log in again.");
      }

      if (!response.ok) {
        throw new Error(payload?.error?.message || "Upload failed");
      }

      sessionStorage.setItem("dashboard_refresh_needed", "1");
      window.location.href = `/static/review.html?document_id=${encodeURIComponent(payload.document_id)}`;
    } catch (error) {
      if (error.name === "AbortError") {
        setMessage("The backend did not respond within 20 seconds.", true);
      } else {
        setMessage(error.message, true);
      }
    } finally {
      window.clearTimeout(timeoutId);
      button.disabled = false;
      uploadLabel.classList.remove("busy");
      form.reset();
    }
  });
}

if (previousToggle) {
  previousToggle.addEventListener("click", async () => {
    try {
      await loadPreviousDocuments();
    } catch (error) {
      setMessage(error.message, true);
    }
  });
}

if (openAuth) {
  openAuth.addEventListener("click", () => openAuthModal("login"));
}

if (openSignup) {
  openSignup.addEventListener("click", () => openAuthModal("signup"));
}

if (closeAuth && authModal) {
  closeAuth.addEventListener("click", () => {
    authModal.classList.add("hidden");
  });
}

if (loginSubmit && loginEmail && loginPassword && loginMessage && authModal) {
  loginSubmit.addEventListener("click", async () => {
    const email = loginEmail.value.trim();
    const password = loginPassword.value;
    loginMessage.textContent = "";
    loginSubmit.disabled = true;

    try {
      const response = await fetch(`/api/v1/auth/${authMode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await readJsonResponse(response);

      if (!response.ok) {
        throw new Error(data?.error?.message || data?.detail || "Authentication failed");
      }

      if (!data.token?.access_token) {
        throw new Error("Authentication did not return a token.");
      }

      localStorage.setItem("access_token", data.token.access_token);
      localStorage.setItem("refresh_token", data.token.refresh_token);
      localStorage.setItem("user_email", data.token.email);

      authModal.classList.add("hidden");
      setAuthState();
      // After successful login/signup, go to the dashboard.
      window.location.href = "/dashboard";
    } catch (error) {
      loginMessage.textContent = error.message;
    } finally {
      loginSubmit.disabled = false;
    }
  });
}

if (logoutButton) {
  logoutButton.addEventListener("click", () => {
    clearAuth();
    setAuthState();
    if (isLandingPage()) {
      openAuthModal("login");
      return;
    }
    window.location.href = "/";
  });
}

setAuthState();
if (isLoggedIn()) {
  if (isLandingPage()) {
    window.location.href = "/dashboard";
  } else {
    loadPreviousDocuments().catch((error) => setMessage(error.message, true));
  }
} else if (!isLandingPage()) {
  openAuthModal("login");
}

window.addEventListener("pageshow", () => {
  if (!isLoggedIn()) return;
  loadPreviousDocuments().catch((error) => setMessage(error.message, true));
});

window.addEventListener("focus", () => {
  if (!isLoggedIn()) return;
  loadPreviousDocuments().catch((error) => setMessage(error.message, true));
});

if (new URLSearchParams(window.location.search).get("refresh") || sessionStorage.getItem("dashboard_refresh_needed")) {
  sessionStorage.removeItem("dashboard_refresh_needed");
  loadPreviousDocuments().catch((error) => setMessage(error.message, true));
}
