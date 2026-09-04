# =========================================================
# LocalScope Access Policy
# =========================================================


# =========================================================
# Allowed SEMrush page areas
# =========================================================
#
# These are the only page areas users should be able to
# navigate to through LocalScope.
#
# Supporting JS/CSS/API requests are NOT controlled by this
# allowlist because this policy is only applied to documents.
#

ALLOWED_PAGE_PREFIXES = {
    # Home
    "/home/",

    # SEO
    "/seo/",
    "/siteaudit/",
    "/position-tracking/",
    "/analytics/",
    "/swa/",
    "/topic-research/",
    "/backlink_audit/",
    "/sensor/",
    "/proxy-external/",
    "/on-page-seo-checker/",
    "/organic_traffic_insights/",

    # AI Visibility
    "/ai-seo/",
    "/content/",
}


# =========================================================
# Pages the user should never open
# =========================================================

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


# =========================================================
# Mutating HTTP methods
# =========================================================

MUTATING_METHODS = {
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
}


# =========================================================
# Keywords that indicate an account-changing action
# =========================================================

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


# =========================================================
# Links that should disappear from the UI
# =========================================================

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




# =========================================================
# Helpers
# =========================================================

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


def is_allowed_page(
    path: str,
) -> bool:
    normalized = normalize_path(
        path
    )

    return any(
        normalized == prefix.rstrip("/")
        or normalized.startswith(prefix)
        for prefix in ALLOWED_PAGE_PREFIXES
    )


# =========================================================
# Page blocking
# =========================================================

def is_blocked_page(
    method: str,
    path: str,
) -> bool:

    # Only use page restrictions for GET/HEAD.
    if method.upper() not in {
        "GET",
        "HEAD",
    }:
        return False

    # First: page must belong to an allowed SEMrush area.
    if not is_allowed_page(
        path
    ):
        return True

    # Second: even allowed areas can contain explicitly
    # forbidden pages such as account/settings/billing.
    if path_contains_keyword(
        path,
        BLOCKED_PAGE_KEYWORDS,
    ):
        return True

    return False


# =========================================================
# Action blocking
# =========================================================

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


# =========================================================
# Final access decision
# =========================================================

def is_access_blocked(
    method: str,
    path: str,
    is_document: bool = False,
) -> bool:

    # Page navigation:
    # apply allowlist + blocked page keywords.
    if (
        is_document
        and is_blocked_page(
            method,
            path,
        )
    ):
        return True

    # Sensitive modifying actions are blocked regardless
    # of whether they come from fetch/XHR or navigation.
    if is_blocked_action(
        method,
        path,
    ):
        return True

    return False