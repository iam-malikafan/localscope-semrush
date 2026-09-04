from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json

from app.proxy.url_mapper import (
    map_upstream_url_to_local,
)

from app.policies.access_rules import (
    HIDDEN_LINK_PATTERNS,
    HIDDEN_SELECTORS,
)


def rewrite_html(
    html: str,
    upstream_url: str,
    target_base_url: str,
    user: dict | None = None,
) -> str:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    # =========================================================
    # URL rewriting
    # =========================================================

    attributes = [
        ("a", "href"),
        ("link", "href"),
        ("script", "src"),
        ("img", "src"),
        ("form", "action"),
        ("iframe", "src"),
        ("source", "src"),
        ("video", "src"),
        ("video", "poster"),
        ("audio", "src"),
    ]

    for tag_name, attribute in attributes:

        for tag in soup.find_all(tag_name):

            value = tag.get(attribute)

            if not value:
                continue

            # Ignore URLs that should not
            # be proxied.
            if (
                value.startswith("#")
                or value.startswith("data:")
                or value.startswith("javascript:")
                or value.startswith("mailto:")
                or value.startswith("tel:")
                or value.startswith("blob:")
            ):
                continue

            # Resolve every URL first.
            absolute_url = urljoin(
                upstream_url,
                value,
            )

            # Central URL mapper decides whether
            # the URL becomes /proxy/... or
            # /proxy-external/...
            mapped_url = map_upstream_url_to_local(
                absolute_url=absolute_url,
                target_base_url=target_base_url,
            )

            tag[attribute] = mapped_url

            # Original integrity hashes no longer match
            # rewritten resources.
            if tag.has_attr("integrity"):
                del tag["integrity"]

    # =========================================================
    # srcset rewriting
    # =========================================================

    for tag in soup.find_all(
        ["img", "source"]
    ):

        srcset = tag.get("srcset")

        if not srcset:
            continue

        rewritten_items = []

        for item in srcset.split(","):

            parts = item.strip().split()

            if not parts:
                continue

            url = parts[0]

            descriptor = " ".join(
                parts[1:]
            )

            if (
                url.startswith("data:")
                or url.startswith("blob:")
            ):
                rewritten_items.append(
                    item.strip()
                )
                continue

            absolute_url = urljoin(
                upstream_url,
                url,
            )

            mapped_url = map_upstream_url_to_local(
                absolute_url=absolute_url,
                target_base_url=target_base_url,
            )

            if descriptor:
                mapped_url += (
                    f" {descriptor}"
                )

            rewritten_items.append(
                mapped_url
            )

        tag["srcset"] = ", ".join(
            rewritten_items
        )

    # =========================================================
    # CSP meta tags
    # =========================================================

    # The upstream site's CSP normally expects
    # its original domains.
    #
    # LocalScope rewrites resources to local
    # proxy URLs, so the original CSP can block
    # those rewritten resources.
    for meta in soup.find_all(
        "meta",
        attrs={
            "http-equiv": lambda value:
                value
                and value.lower()
                == "content-security-policy"
        },
    ):
        meta.decompose()

    # =========================================================
    # LocalScope runtime proxy
    # =========================================================

    if not soup.find(
        "script",
        attrs={
            "data-localscope-runtime": "true"
        },
    ):

        runtime_script = soup.new_tag(
            "script",
            src="/localscope/static/js/runtime_proxy.js",
        )

        runtime_script[
            "data-localscope-runtime"
        ] = "true"

        runtime_script[
            "data-upstream-url"
        ] = upstream_url

        # Inject before the site's own scripts
        # whenever possible.
        if soup.head:

            soup.head.insert(
                0,
                runtime_script,
            )

        else:

            soup.insert(
                0,
                runtime_script,
            )

    # =========================================================
    # LocalScope access UI configuration
    # =========================================================

    hidden_patterns_json = json.dumps(
        HIDDEN_LINK_PATTERNS
    )

    hidden_selectors_json = json.dumps(
        HIDDEN_SELECTORS
    )

    # User name returned by authcheck.
    user_name = ""

    if user:

        user_name = (
            user.get("name")
            or user.get("username")
            or user.get("email")
            or ""
        )

    user_name_json = json.dumps(
        user_name
    )

    # =========================================================
    # JavaScript access-control UI
    # =========================================================

    access_script_code = f"""
        (() => {{

            const blockedPatterns =
                {hidden_patterns_json};

            const hiddenSelectors =
                {hidden_selectors_json};


            // =================================================
            // Unwanted top-level SEMrush navigation
            // =================================================

            const blockedNavigationLabels = [
                "Start free trial",
                "Enterprise",
                "More",

                "Traffic & Market",
                "Local",
                "Content",
                "Advertising",
                "Ad",
                "AI PR",
                "Social",
                "Reports",
                "Apps"
            ];


            // =================================================
            // Helper: normalize visible text
            // =================================================

            function normalizeText(text) {{

                return (text || "")
                    .replace(/\\\\s+/g, " ")
                    .trim()
                    .toLowerCase();
            }}


            // =================================================
            // Hide an element safely
            // =================================================

            function hideElement(element) {{

                if (!element) {{
                    return;
                }}

                element.style.setProperty(
                    "display",
                    "none",
                    "important"
                );
            }}


            // =================================================
            // Hide unwanted top-level navigation
            // =================================================

            function hideBlockedNavigation() {{

                const blockedLabels =
                    blockedNavigationLabels.map(
                        normalizeText
                    );


                // ---------------------------------------------
                // Links
                // ---------------------------------------------

                document
                    .querySelectorAll("a")
                    .forEach((element) => {{

                        const text =
                            normalizeText(
                                element.textContent
                            );

                        if (
                            !blockedLabels.includes(text)
                        ) {{
                            return;
                        }}


                        /*
                         * Do not blindly remove the whole
                         * navigation tree.
                         *
                         * Hide the actual clickable item.
                         */
                        hideElement(element);
                    }});


                // ---------------------------------------------
                // Buttons
                // ---------------------------------------------

                document
                    .querySelectorAll("button")
                    .forEach((element) => {{

                        const text =
                            normalizeText(
                                element.textContent
                            );

                        if (
                            !blockedLabels.includes(text)
                        ) {{
                            return;
                        }}

                        hideElement(element);
                    }});


                // ---------------------------------------------
                // Elements using role="button"
                // ---------------------------------------------

                document
                    .querySelectorAll(
                        '[role="button"]'
                    )
                    .forEach((element) => {{

                        const text =
                            normalizeText(
                                element.textContent
                            );

                        if (
                            !blockedLabels.includes(text)
                        ) {{
                            return;
                        }}

                        hideElement(element);
                    }});
            }}


            // =================================================
            // Hide links by URL pattern
            // =================================================

            function hideBlockedLinks() {{

                document
                    .querySelectorAll("a[href]")
                    .forEach((element) => {{

                        const href =
                            element.getAttribute(
                                "href"
                            ) || "";

                        const blocked =
                            blockedPatterns.some(
                                (pattern) =>
                                    href.includes(
                                        pattern
                                    )
                            );

                        if (blocked) {{

                            hideElement(
                                element
                            );
                        }}
                    }});
            }}


            // =================================================
            // Hide elements by explicit selector
            // =================================================

            function hideConfiguredSelectors() {{

                hiddenSelectors.forEach(
                    (selector) => {{

                        try {{

                            document
                                .querySelectorAll(
                                    selector
                                )
                                .forEach(
                                    (element) => {{

                                        hideElement(
                                            element
                                        );
                                    }}
                                );

                        }} catch (error) {{

                            console.warn(
                                "Invalid LocalScope selector:",
                                selector
                            );
                        }}
                    }}
                );
            }}


            // =================================================
            // RankyTools header
            // =================================================

            function createRankyToolsHeader() {{

                if (
                    document.getElementById(
                        "rankytools-header"
                    )
                ) {{
                    return;
                }}


                if (!document.body) {{
                    return;
                }}


                const header =
                    document.createElement(
                        "div"
                    );

                header.id =
                    "rankytools-header";


                const userName =
                    {user_name_json};


                const brand =
                    document.createElement(
                        "strong"
                    );

                brand.textContent =
                    "RANKYTOOLS";


                const tool =
                    document.createElement(
                        "span"
                    );

                tool.textContent =
                    "SEMrush";


                const user =
                    document.createElement(
                        "span"
                    );

                user.textContent =
                    userName;


                const left =
                    document.createElement(
                        "div"
                    );

                left.appendChild(
                    brand
                );

                left.appendChild(
                    tool
                );


                const right =
                    document.createElement(
                        "div"
                    );

                right.appendChild(
                    user
                );


                header.appendChild(
                    left
                );

                header.appendChild(
                    right
                );


                header.style.cssText = `
                    position: sticky;
                    top: 0;
                    z-index: 2147483647;
                    width: 100%;
                    box-sizing: border-box;
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    padding: 10px 20px;
                    background: #111827;
                    color: white;
                    font-family: Arial, sans-serif;
                    font-size: 14px;
                `;


                document.body.prepend(
                    header
                );
            }}


            // =================================================
            // Apply LocalScope UI restrictions
            // =================================================

            function applyLocalScopeUI() {{

                createRankyToolsHeader();

                hideBlockedNavigation();

                hideBlockedLinks();

                hideConfiguredSelectors();
            }}


            // =================================================
            // Initial execution
            // =================================================

            if (
                document.readyState
                === "loading"
            ) {{

                document.addEventListener(
                    "DOMContentLoaded",
                    applyLocalScopeUI
                );

            }} else {{

                applyLocalScopeUI();
            }}


            // =================================================
            // Handle dynamically rendered SEMrush UI
            // =================================================

            const observer =
                new MutationObserver(
                    () => {{

                        applyLocalScopeUI();

                    }}
                );


            if (
                document.documentElement
            ) {{

                observer.observe(
                    document.documentElement,
                    {{
                        childList: true,
                        subtree: true
                    }}
                );
            }}

        }})();
    """

    access_script = soup.new_tag(
        "script"
    )

    access_script[
        "data-localscope-access-ui"
    ] = "true"

    access_script.string = (
        access_script_code
    )

    if soup.body:

        soup.body.append(
            access_script
        )

    else:

        soup.append(
            access_script
        )

    return str(soup)