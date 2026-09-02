/* =========================================================
   LocalScope Admin
   ========================================================= */

/* =========================================================
   API Configuration
   ========================================================= */

const API = {
  accounts: "/localscope/api/accounts",


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

const accountSubmitButton = document.getElementById(
  "account-submit-button",
);

const accountNameInput = document.getElementById("account-name");

const accountCookieInput = document.getElementById("account-cookie");

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

let editingAccountId = null;

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
    const response = await fetch(API.accounts, {
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    accounts = await response.json();

    renderAccounts();

    updateOverviewStats();
  } catch (error) {
    console.error("Failed to load accounts:", error);

    accountsList.innerHTML = `
            <div class="empty-state">
                Unable to load accounts.
            </div>
        `;
  }
}

function renderAccounts() {
  if (!accounts.length) {
    accountsList.innerHTML = `
            <div class="empty-state">
                No Semrush accounts have been added yet.
            </div>
        `;

    return;
  }

  accountsList.innerHTML = accounts
    .map((account) => {
      const initial = escapeHtml(
        account.name?.trim()?.charAt(0)?.toUpperCase() || "A",
      );

      const name = escapeHtml(account.name);

      const userCount = getAccountUserCount(account.id);

      return `

                <div
                    class="account-row"
                    data-account-id="${account.id}"
                >

                    <div class="account-main">

                        <div class="account-avatar">
                            ${initial}
                        </div>

                        <div class="account-name">

                            <strong>
                                ${name}
                            </strong>

                            <small>
                                ID: ${escapeHtml(account.id.slice(0, 8))}
                            </small>

                        </div>

                    </div>


                    <div class="account-state">

                        <span
                            class="
                                account-status
                                ${account.enabled ? "enabled" : "disabled"}
                            "
                        >
                            ${account.enabled ? "Enabled" : "Disabled"}
                        </span>


                        <span
                            class="
                                health-status
                                health-${account.health || "unknown"}
                            "
                        >
                            ${formatHealth(account.health)}
                        </span>

                        <small class="proxy-summary">
                            Proxy: ${account.has_proxy ? `${escapeHtml(account.proxy_host)}:${escapeHtml(account.proxy_port)}` : "Not configured"}
                            · ${formatHealth(account.proxy_health)}
                        </small>

                    </div>


                    <div class="account-users">

                        ${userCount}
                        ${userCount === 1 ? "user" : "users"}

                    </div>


                    <div class="account-actions">

                        <button
                            class="account-action-button"
                            data-proxy-health="${account.id}"
                            ${account.has_proxy ? "" : "disabled"}
                        >
                            Check Proxy
                        </button>

                        <button
                            class="account-action-button"
                            data-account-toggle="${account.id}"
                            data-enabled="${account.enabled}"
                        >
                            ${account.enabled ? "Disable" : "Enable"}
                        </button>

                        <button
                            class="account-action-button"
                            data-account-edit="${account.id}"
                        >
                            Edit
                        </button>

                        <button
                            class="danger-button"
                            data-account-delete="${account.id}"
                        >
                            Delete
                        </button>

                    </div>

                </div>
            `;
    })
    .join("");

  bindAccountButtons();
}

function formatHealth(
  health
) {

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

/*
 * We don't yet expose assignment counts
 * through an API, so this currently returns
 * zero.
 *
 * We'll connect this to real assignment data
 * in the next small backend step.
 */

function getAccountUserCount(accountId) {
  const account = accounts.find((item) => item.id === accountId);

  return account?.assigned_users || 0;
}

function bindAccountButtons() {
  document.querySelectorAll("[data-account-toggle]").forEach((button) => {
    button.addEventListener("click", async () => {
      const accountId = button.dataset.accountToggle;

      const enabled = button.dataset.enabled === "true";

      await toggleAccount(accountId, enabled);
    });
  });

  document.querySelectorAll("[data-proxy-health]").forEach((button) => {
    button.addEventListener("click", async () => {
      await checkProxyHealth(button.dataset.proxyHealth, button);
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

async function checkProxyHealth(accountId, button) {
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Checking...";

  try {
    const response = await fetch(`${API.accounts}/${accountId}/proxy-health`, {
      method: "POST",
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || "Proxy health check failed.");
    }

    if (result.proxy_health === "healthy") {
      showToast(
        `Proxy is healthy (Semrush HTTP ${result.proxy_status_code}).`,
        "success",
      );
    } else {
      showToast(result.message || "Proxy check failed.", "error");
    }

    await loadAccounts();
  } catch (error) {
    console.error("Proxy health check failed:", error);
    showToast(error.message || "Could not check proxy.", "error");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}


async function toggleAccount(accountId, currentlyEnabled) {
  const action = currentlyEnabled ? "disable" : "enable";

  try {
    const response = await fetch(`${API.accounts}/${accountId}/${action}`, {
      method: "POST",
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    showToast(
      currentlyEnabled ? "Account disabled." : "Account enabled.",
      "success",
    );

    await loadAccounts();
  } catch (error) {
    console.error("Account update failed:", error);

    showToast("Could not update account.", "error");
  }
}

async function deleteAccount(accountId) {
  const account = accounts.find((item) => item.id === accountId);

  const confirmed = window.confirm(
    `Delete "${account?.name || "this account"}"?`,
  );

  if (!confirmed) {
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
   Add Account Modal
   ========================================================= */

function openAccountModal() {
  editingAccountId = null;

  accountModalTitle.textContent = "Add Semrush Account";
  accountModalDescription.textContent =
    "Paste the authenticated Cookie request header.";
  accountSubmitButton.textContent = "Save Account";

  accountForm.reset();

  accountModal.classList.remove("hidden");

  setTimeout(() => {
    accountNameInput.focus();
  }, 40);
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
    "Update the account details. Leave Cookie and proxy credentials blank to keep the existing values.";
  accountSubmitButton.textContent = "Save Changes";

  accountForm.reset();

  accountNameInput.value = account.name || "";

  proxySchemeInput.value = account.proxy_scheme || "http";
  proxyHostInput.value = account.proxy_host || "";
  proxyPortInput.value = account.proxy_port || "";

  accountModal.classList.remove("hidden");

  setTimeout(() => {
    accountNameInput.focus();
  }, 40);
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

  const name = accountNameInput.value.trim();
  const cookie = accountCookieInput.value.trim();

  const proxyScheme = proxySchemeInput.value;
  const proxyHost = proxyHostInput.value.trim();
  const proxyPort = proxyPortInput.value.trim();
  const proxyUsername = proxyUsernameInput.value.trim();
  const proxyPassword = proxyPasswordInput.value;

  if (!name) {
    showToast("Account name is required.", "error");
    return;
  }

  if (!editingAccountId && !cookie) {
    showToast("Cookie is required.", "error");
    return;
  }

  if (!proxyHost || !proxyPort) {
    showToast("Proxy host and port are required.", "error");
    return;
  }

  if (
    (proxyUsername && !proxyPassword) ||
    (!proxyUsername && proxyPassword)
  ) {
    showToast(
      "Both proxy username and password are required.",
      "error",
    );
    return;
  }

  try {
    const isEditing = Boolean(editingAccountId);

    const url = isEditing
      ? `${API.accounts}/${editingAccountId}`
      : API.accounts;

    const method = isEditing ? "PUT" : "POST";

    const body = {
      name,
      proxy_scheme: proxyScheme,
      proxy_host: proxyHost,
      proxy_port: proxyPort,
      proxy_username: proxyUsername,
      proxy_password: proxyPassword,
    };

    if (cookie) {
      body.cookie = cookie;
    }

    const response = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(
        result.error ||
          (isEditing
            ? "Could not update account."
            : "Could not add account."),
      );
    }

    closeAccountModal();

    showToast(
      isEditing
        ? "Account updated successfully."
        : "Account added successfully.",
      "success",
    );

    await loadAccounts();
  } catch (error) {
    console.error(
      isEditing ? "Edit account failed:" : "Add account failed:",
      error,
    );

    showToast(
      error.message ||
        (isEditing
          ? "Could not update account."
          : "Could not add account."),
      "error",
    );
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
  if (event.key === "Escape" && !accountModal.classList.contains("hidden")) {
    closeAccountModal();
  }
});

/* =========================================================
   Initial Load
   ========================================================= */

async function initialize() {
  await Promise.allSettled([loadAccounts()]);

  updateOverviewStats();
}

initialize();
