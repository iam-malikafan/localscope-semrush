# =========================================================
# LocalScope Access Policy
# =========================================================


# Pages the user should never open.
BLOCKED_PAGE_KEYWORDS = {
    "logout",
    "login",
    "signup",

    "account",
    "profile",
    "settings",

    "billing",
    "payment",
    "payments",

    "subscription",
    "subscriptions",

    "pricing",
    "upgrade",

    "password",
    "security",

    "team",
    "teams",

    "member",
    "members",

    "invite",
    "invitations",
}


# Mutating HTTP methods.
MUTATING_METHODS = {
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
}


# Keywords that indicate an account-changing action.
SENSITIVE_ACTION_KEYWORDS = {
    "logout",

    "account",
    "profile",
    "settings",

    "password",
    "email",
    "security",

    "billing",
    "payment",

    "subscription",
    "plan",
    "upgrade",
    "cancel",

    "team",
    "member",
    "invite",

    "delete",
    "remove",
}


# Links that should disappear from the UI.
HIDDEN_LINK_PATTERNS = [
    "/logout",
    "/pricing",
    "/billing",
    "/subscription",
    "/account",
    "/profile",
    "/settings",
    "/security",
    "/team",
]


# Explicit selectors can be added later
# when you find buttons without href links.
HIDDEN_SELECTORS = []


HEADER_MESSAGE = (
    "This account is managed through LocalScope. "
    "Account settings and subscription management are restricted."
)


def normalize_path(
    path: str,
) -> str:

    path = "/" + path.lstrip("/")

    return path.lower()


def path_contains_keyword(
    path: str,
    keywords: set[str],
) -> bool:

    normalized = normalize_path(
        path
    )

    parts = {
        part
        for part
        in normalized.split("/")
        if part
    }

    return any(
        keyword in parts
        for keyword in keywords
    )


def is_blocked_page(
    method: str,
    path: str,
) -> bool:

    # Only use the broad page rule for GET/HEAD.
    if method.upper() not in {
        "GET",
        "HEAD",
    }:
        return False

    return path_contains_keyword(
        path,
        BLOCKED_PAGE_KEYWORDS,
    )


def is_blocked_action(
    method: str,
    path: str,
) -> bool:

    method = method.upper()

    if method not in MUTATING_METHODS:
        return False

    return path_contains_keyword(
        path,
        SENSITIVE_ACTION_KEYWORDS,
    )


def is_access_blocked(
    method: str,
    path: str,
    is_document: bool = False,
) -> bool:

    # Broad page restrictions only apply
    # when the browser is actually navigating
    # to a page.
    if (
        is_document
        and is_blocked_page(
            method,
            path,
        )
    ):
        return True

    # Sensitive modifying actions are blocked
    # regardless of whether they come from
    # fetch/XHR or normal navigation.
    if is_blocked_action(
        method,
        path,
    ):
        return True

    return False