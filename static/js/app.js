/* =========================================================
   LocalScope Admin
   ========================================================= */

const API = {
  accounts: "/localscope/api/accounts",
  proxies: "/localscope/api/proxies",
};

/* =========================================================
   Elements
   ========================================================= */

const navItems = document.querySelectorAll(".nav-item");
const pages = document.querySelectorAll(".admin-page");
const pageTitle = document.getElementById("page-title");
const pageDescription = document.getElementById("page-description");

const accountsList = document.getElementById("accounts-list");
const accountModal = document.getElementById("account-modal");
const accountForm = document.getElementById("account-form");
const accountModalTitle = document.getElementById("account-modal-title");
const accountModalDescription = document.getElementById(
  "account-modal-description",
);
const accountSubmitButton = document.getElementById("account-submit-button");
const accountNameInput = document.getElementById("account-name");
const accountCookieInput = document.getElementById("account-cookie");

const proxiesList = document.getElementById("proxies-list");
const proxyModal = document.getElementById("proxy-modal");
const proxyForm = document.getElementById("proxy-form");
const proxyModalTitle = document.getElementById("proxy-modal-title");
const proxySubmitButton = document.getElementById("proxy-submit-button");
const proxyEditHelp = document.getElementById("proxy-edit-help");
const proxyLabelInput = document.getElementById("proxy-label");
const proxySchemeInput = document.getElementById("proxy-scheme");
const proxyHostInput = document.getElementById("proxy-host");
const proxyPortInput = document.getElementById("proxy-port");
const proxyUsernameInput = document.getElementById("proxy-username");
const proxyPasswordInput = document.getElementById("proxy-password");

const toast = document.getElementById("toast");
const toastMessage = document.getElementById("toast-message");

/* =========================================================
   State
   ========================================================= */

let accounts = [];
let proxies = [];

let editingAccountId = null;
let editingProxyId = null;

let toastTimeout = null;

/* =========================================================
   Page Information
   ========================================================= */

const pageInformation = {
  overview: {
    title: "Overview",
    description: "Monitor and control your LocalScope proxy.",
  },
  accounts: {
    title: "Accounts",
    description: "Manage Semrush accounts available to LocalScope users.",
  },
  proxies: {
    title: "Proxies",
    description:
      "Enabled, healthy proxies are shared by all accounts (round-robin).",
  },
};

/* =========================================================
   Navigation
   ========================================================= */

function openPage(pageName) {
  navItems.forEach((item) => {
    item.classList.toggle("active", item.dataset.page === pageName);
  });

  pages.forEach((page) => {
    page.classList.toggle("active", page.id === `page-${pageName}`);
  });

  const information = pageInformation[pageName];

  if (information) {
    pageTitle.textContent = information.title;
    pageDescription.textContent = information.description;
  }

  if (pageName === "accounts") {
    loadAccounts();
  }

  if (pageName === "proxies") {
    loadProxies();
  }
}

navItems.forEach((item) => {
  item.addEventListener("click", () => {
    openPage(item.dataset.page);
  });
});

document.querySelectorAll("[data-open-page]").forEach((button) => {
  button.addEventListener("click", () => {
    const page = button.dataset.openPage;

    openPage(page);

    if (page === "accounts") {
      setTimeout(openAccountModal, 100);
    }
  });
});

/* =========================================================
   Accounts
   ========================================================= */

async function loadAccounts() {
  try {
    const response = await fetch(API.accounts, { cache: "no-store" });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    accounts = await response.json();

    renderAccounts();
    updateOverviewStats();
  } catch (error) {
    console.error("Failed to load accounts:", error);

    accountsList.innerHTML = `
      <div class="empty-state">Unable to load accounts.</div>
    `;
  }
}

function renderAccounts() {
  if (!accounts.length) {
    accountsList.innerHTML = `
      <div class="empty-state">No Semrush accounts have been added yet.</div>
    `;
    return;
  }

  accountsList.innerHTML = accounts
    .map((account) => {
      const initial = escapeHtml(
        account.name?.trim()?.charAt(0)?.toUpperCase() || "A",
      );
      const name = escapeHtml(account.name);
      const userCount = account.assigned_users || 0;
      const assignedProxy = account.assigned_proxy
        ? escapeHtml(account.assigned_proxy)
        : "Unassigned";

      return `
        <div class="account-row" data-account-id="${account.id}">
          <div class="account-main">
            <div class="account-avatar">${initial}</div>
            <div class="account-name">
              <strong>${name}</strong>
              <small>ID: ${escapeHtml(account.id.slice(0, 8))}</small>
            </div>
          </div>

          <div class="account-state">
            <span class="account-status ${account.enabled ? "enabled" : "disabled"}">
              ${account.enabled ? "Enabled" : "Disabled"}
            </span>

            <span class="health-status health-${account.health || "unknown"}">
              ${formatHealth(account.health)}
            </span>

            <small class="proxy-summary">Proxy: ${assignedProxy}</small>
          </div>

          <div class="account-users">
            ${userCount} ${userCount === 1 ? "user" : "users"}
          </div>

          <div class="account-actions">
            <button class="account-action-button"
              data-account-toggle="${account.id}"
              data-enabled="${account.enabled}">
              ${account.enabled ? "Disable" : "Enable"}
            </button>

            <button class="account-action-button"
              data-account-edit="${account.id}">
              Edit
            </button>

            <button class="danger-button"
              data-account-delete="${account.id}">
              Delete
            </button>
          </div>
        </div>
      `;
    })
    .join("");

  bindAccountButtons();
}

function formatHealth(health) {
  switch (health) {
    case "healthy":
      return "Healthy";
    case "expired":
      return "Expired";
    case "error":
      return "Error";
    default:
      return "Unknown";
  }
}

function bindAccountButtons() {
  document.querySelectorAll("[data-account-toggle]").forEach((button) => {
    button.addEventListener("click", async () => {
      await toggleAccount(
        button.dataset.accountToggle,
        button.dataset.enabled === "true",
      );
    });
  });

  document.querySelectorAll("[data-account-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      await deleteAccount(button.dataset.accountDelete);
    });
  });

  document.querySelectorAll("[data-account-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      openEditAccount(button.dataset.accountEdit);
    });
  });
}

async function toggleAccount(accountId, currentlyEnabled) {
  const action = currentlyEnabled ? "disable" : "enable";

  try {
    const response = await fetch(`${API.accounts}/${accountId}/${action}`, {
      method: "POST",
    });

    const result = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }

    showToast(
      currentlyEnabled ? "Account disabled." : "Account enabled.",
      "success",
    );

    await loadAccounts();
  } catch (error) {
    console.error("Account update failed:", error);
    showToast(error.message || "Could not update account.", "error");
  }
}

async function deleteAccount(accountId) {
  const account = accounts.find((item) => item.id === accountId);

  if (!window.confirm(`Delete "${account?.name || "this account"}"?`)) {
    return;
  }

  try {
    const response = await fetch(`${API.accounts}/${accountId}`, {
      method: "DELETE",
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    showToast("Account deleted.", "success");
    await loadAccounts();
  } catch (error) {
    console.error("Delete account failed:", error);
    showToast("Could not delete account.", "error");
  }
}

/* =========================================================
   Account Modal
   ========================================================= */

function openAccountModal() {
  editingAccountId = null;

  accountModalTitle.textContent = "Add Semrush Account";
  accountModalDescription.textContent =
    "Paste the authenticated Cookie request header.";
  accountSubmitButton.textContent = "Save Account";

  accountForm.reset();
  accountModal.classList.remove("hidden");

  setTimeout(() => accountNameInput.focus(), 40);
}

function openEditAccount(accountId) {
  const account = accounts.find((item) => item.id === accountId);

  if (!account) {
    showToast("Account not found.", "error");
    return;
  }

  editingAccountId = accountId;

  accountModalTitle.textContent = "Edit Semrush Account";
  accountModalDescription.textContent =
    "Update the account. Leave Cookie blank to keep the existing value.";
  accountSubmitButton.textContent = "Save Changes";

  accountForm.reset();
  accountNameInput.value = account.name || "";

  accountModal.classList.remove("hidden");
  setTimeout(() => accountNameInput.focus(), 40);
}

function closeAccountModal() {
  accountModal.classList.add("hidden");
  accountForm.reset();
  editingAccountId = null;
}

document
  .getElementById("show-add-account")
  .addEventListener("click", openAccountModal);

document
  .getElementById("close-account-modal")
  .addEventListener("click", closeAccountModal);

document
  .getElementById("cancel-add-account")
  .addEventListener("click", closeAccountModal);

accountModal.addEventListener("click", (event) => {
  if (event.target === accountModal) {
    closeAccountModal();
  }
});

accountForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const isEditing = Boolean(editingAccountId);
  const name = accountNameInput.value.trim();
  const cookie = accountCookieInput.value.trim();

  if (!name) {
    showToast("Account name is required.", "error");
    return;
  }

  if (!isEditing && !cookie) {
    showToast("Cookie is required.", "error");
    return;
  }

  try {
    const url = isEditing ? `${API.accounts}/${editingAccountId}` : API.accounts;
    const method = isEditing ? "PUT" : "POST";

    const body = { name };
    if (cookie) {
      body.cookie = cookie;
    }

    const response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const result = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(
        result.error ||
          (isEditing ? "Could not update account." : "Could not add account."),
      );
    }

    closeAccountModal();
    showToast(isEditing ? "Account updated." : "Account added.", "success");
    await loadAccounts();
  } catch (error) {
    console.error("Save account failed:", error);
    showToast(error.message || "Could not save account.", "error");
  }
});

/* =========================================================
   Proxies (global pool)
   ========================================================= */

async function loadProxies() {
  try {
    const response = await fetch(API.proxies, { cache: "no-store" });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    proxies = await response.json();
    renderProxies();
  } catch (error) {
    console.error("Failed to load proxies:", error);

    proxiesList.innerHTML = `
      <div class="empty-state">Unable to load proxies.</div>
    `;
  }
}

function renderProxies() {
  if (!proxies.length) {
    proxiesList.innerHTML = `
      <div class="empty-state">No proxies in the pool yet.</div>
    `;
    return;
  }

  proxiesList.innerHTML = proxies
    .map((proxy) => {
      const label = escapeHtml(proxy.label || `${proxy.host}:${proxy.port}`);
      const endpoint = escapeHtml(
        `${proxy.scheme}://${proxy.host}:${proxy.port}`,
      );
      const count = proxy.assigned_accounts || 0;
      const authTag = proxy.has_auth
        ? `<span class="proxy-tag">Auth</span>`
        : "";

      return `
        <div class="account-row" data-proxy-id="${proxy.id}">
          <div class="account-main">
            <div class="account-avatar">&#8646;</div>
            <div class="account-name">
              <strong>${label}</strong>
              <small>${endpoint} ${authTag}</small>
            </div>
          </div>

          <div class="account-state">
            <span class="account-status ${proxy.enabled ? "enabled" : "disabled"}">
              ${proxy.enabled ? "Enabled" : "Disabled"}
            </span>

            <span class="health-status health-${proxy.health || "unknown"}">
              ${formatHealth(proxy.health)}
            </span>
          </div>

          <div class="account-users">
            ${count} ${count === 1 ? "account" : "accounts"}
          </div>

          <div class="account-actions">
            <button class="account-action-button"
              data-proxy-check="${proxy.id}">
              Check
            </button>

            <button class="account-action-button"
              data-proxy-toggle="${proxy.id}"
              data-enabled="${proxy.enabled}">
              ${proxy.enabled ? "Disable" : "Enable"}
            </button>

            <button class="account-action-button"
              data-proxy-edit="${proxy.id}">
              Edit
            </button>

            <button class="danger-button"
              data-proxy-delete="${proxy.id}">
              Delete
            </button>
          </div>
        </div>
      `;
    })
    .join("");

  bindProxyButtons();
}

function bindProxyButtons() {
  document.querySelectorAll("[data-proxy-toggle]").forEach((button) => {
    button.addEventListener("click", async () => {
      await toggleProxy(
        button.dataset.proxyToggle,
        button.dataset.enabled === "true",
      );
    });
  });

  document.querySelectorAll("[data-proxy-check]").forEach((button) => {
    button.addEventListener("click", async () => {
      await checkProxy(button.dataset.proxyCheck, button);
    });
  });

  document.querySelectorAll("[data-proxy-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      openEditProxy(button.dataset.proxyEdit);
    });
  });

  document.querySelectorAll("[data-proxy-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      await deleteProxy(button.dataset.proxyDelete);
    });
  });
}

async function toggleProxy(proxyId, currentlyEnabled) {
  const action = currentlyEnabled ? "disable" : "enable";

  try {
    const response = await fetch(`${API.proxies}/${proxyId}/${action}`, {
      method: "POST",
    });

    const result = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }

    if (action === "enable" && result.health && result.health !== "healthy") {
      showToast(
        result.message || `Enabled, but proxy check failed (${result.health}).`,
        "error",
      );
    } else {
      showToast(
        currentlyEnabled ? "Proxy disabled." : "Proxy enabled.",
        "success",
      );
    }

    await loadProxies();
  } catch (error) {
    console.error("Proxy update failed:", error);
    showToast(error.message || "Could not update proxy.", "error");
  }
}

async function checkProxy(proxyId, button) {
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Checking...";

  try {
    const response = await fetch(`${API.proxies}/${proxyId}/check`, {
      method: "POST",
    });

    const result = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(result.error || "Proxy check failed.");
    }

    if (result.health === "healthy") {
      showToast(
        `Proxy is healthy (Semrush HTTP ${result.status_code}).`,
        "success",
      );
    } else {
      showToast(result.message || "Proxy check failed.", "error");
    }

    await loadProxies();
  } catch (error) {
    console.error("Proxy check failed:", error);
    showToast(error.message || "Could not check proxy.", "error");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

async function deleteProxy(proxyId) {
  const proxy = proxies.find((item) => item.id === proxyId);

  if (!window.confirm(`Delete proxy "${proxy?.label || "this proxy"}"?`)) {
    return;
  }

  try {
    const response = await fetch(`${API.proxies}/${proxyId}`, {
      method: "DELETE",
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    showToast("Proxy deleted.", "success");
    await loadProxies();
  } catch (error) {
    console.error("Delete proxy failed:", error);
    showToast("Could not delete proxy.", "error");
  }
}

/* =========================================================
   Proxy Modal
   ========================================================= */

function openAddProxy() {
  editingProxyId = null;

  proxyModalTitle.textContent = "Add Proxy";
  proxySubmitButton.textContent = "Add Proxy";
  proxyEditHelp.textContent = "";

  proxyForm.reset();
  proxyModal.classList.remove("hidden");

  setTimeout(() => proxyHostInput.focus(), 40);
}

function openEditProxy(proxyId) {
  const proxy = proxies.find((item) => item.id === proxyId);

  if (!proxy) {
    showToast("Proxy not found.", "error");
    return;
  }

  editingProxyId = proxyId;

  proxyModalTitle.textContent = "Edit Proxy";
  proxySubmitButton.textContent = "Save Changes";

  proxyForm.reset();
  proxyLabelInput.value = proxy.label || "";
  proxyEditHelp.textContent = `Current: ${proxy.scheme}://${proxy.host}:${proxy.port}. Leave proxy fields blank to keep it; fill them to replace it.`;

  proxyModal.classList.remove("hidden");
  setTimeout(() => proxyLabelInput.focus(), 40);
}

function closeProxyModal() {
  proxyModal.classList.add("hidden");
  proxyForm.reset();
  editingProxyId = null;
}

document
  .getElementById("show-add-proxy")
  .addEventListener("click", openAddProxy);

document
  .getElementById("close-proxy-modal")
  .addEventListener("click", closeProxyModal);

document
  .getElementById("cancel-proxy")
  .addEventListener("click", closeProxyModal);

proxyModal.addEventListener("click", (event) => {
  if (event.target === proxyModal) {
    closeProxyModal();
  }
});

proxyForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const isEditing = Boolean(editingProxyId);

  const label = proxyLabelInput.value.trim();
  const host = proxyHostInput.value.trim();
  const port = proxyPortInput.value.trim();
  const username = proxyUsernameInput.value.trim();
  const password = proxyPasswordInput.value;

  const body = { label };

  const wantsProxyChange = Boolean(host || port);

  // When adding, the proxy endpoint is mandatory.
  if (!isEditing || wantsProxyChange) {
    if (!host || !port) {
      showToast("Proxy host and port are required.", "error");
      return;
    }

    if ((username && !password) || (!username && password)) {
      showToast("Both proxy username and password are required.", "error");
      return;
    }

    body.proxy_scheme = proxySchemeInput.value;
    body.proxy_host = host;
    body.proxy_port = port;
    body.proxy_username = username;
    body.proxy_password = password;
  }

  try {
    const url = isEditing ? `${API.proxies}/${editingProxyId}` : API.proxies;
    const method = isEditing ? "PUT" : "POST";

    const response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const result = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(
        result.error ||
          (isEditing ? "Could not update proxy." : "Could not add proxy."),
      );
    }

    closeProxyModal();
    showToast(isEditing ? "Proxy updated." : "Proxy added.", "success");
    await loadProxies();
  } catch (error) {
    console.error("Save proxy failed:", error);
    showToast(error.message || "Could not save proxy.", "error");
  }
});

/* =========================================================
   Overview
   ========================================================= */

function updateOverviewStats() {
  const enabledAccounts = accounts.filter((account) => account.enabled);

  document.getElementById("stat-total-accounts").textContent = accounts.length;
  document.getElementById("stat-enabled-accounts").textContent =
    enabledAccounts.length;

  const sessionCount = accounts.reduce(
    (total, account) => total + (account.assigned_users || 0),
    0,
  );

  document.getElementById("stat-browser-sessions").textContent = sessionCount;
}

/* =========================================================
   Toast
   ========================================================= */

function showToast(message, type = "") {
  clearTimeout(toastTimeout);

  toastMessage.textContent = message;
  toast.className = "toast";

  if (type) {
    toast.classList.add(type);
  }

  toast.classList.remove("hidden");

  toastTimeout = setTimeout(() => {
    toast.classList.add("hidden");
  }, 3000);
}

/* =========================================================
   Security / Escaping
   ========================================================= */

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = String(value ?? "");
  return element.innerHTML;
}

/* =========================================================
   Keyboard
   ========================================================= */

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") {
    return;
  }

  if (!accountModal.classList.contains("hidden")) {
    closeAccountModal();
  }

  if (!proxyModal.classList.contains("hidden")) {
    closeProxyModal();
  }
});

/* =========================================================
   Initial Load
   ========================================================= */

async function initialize() {
  await loadAccounts();
}

initialize();