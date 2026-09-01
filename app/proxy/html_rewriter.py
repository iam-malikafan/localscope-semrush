from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
from app.proxy.url_mapper import (
    map_upstream_url_to_local,
)
from app.policies.access_rules import (
    HIDDEN_LINK_PATTERNS,
    HEADER_MESSAGE,
    HIDDEN_SELECTORS,
)


def rewrite_html(
    html: str,
    upstream_url: str,
    target_base_url: str,
) -> str:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

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
            #
            # Examples:
            #
            # /assets/app.js
            # ./app.js
            # ../app.js
            # https://github.com/page
            # https://github.githubassets.com/app.js
            # //cdn.example.com/app.js
            #
            # all become absolute real URLs here.
            absolute_url = urljoin(
                upstream_url,
                value,
            )

            # Then let ONE central mapper
            # decide whether it belongs to:
            #
            # /proxy/...
            #
            # or
            #
            # /proxy-external/...
            mapped_url = map_upstream_url_to_local(
                absolute_url=absolute_url,
                target_base_url=target_base_url,
            )

            tag[attribute] = mapped_url

            if tag.has_attr("integrity"):
                del tag["integrity"]

    # -------------------------
    # srcset
    # -------------------------

    for tag in soup.find_all(["img", "source"]):

        srcset = tag.get("srcset")

        if not srcset:
            continue

        rewritten_items = []

        for item in srcset.split(","):

            parts = item.strip().split()

            if not parts:
                continue

            url = parts[0]

            descriptor = " ".join(parts[1:])

            if url.startswith("data:") or url.startswith("blob:"):

                rewritten_items.append(item.strip())

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
                mapped_url += f" {descriptor}"

            rewritten_items.append(mapped_url)

        tag["srcset"] = ", ".join(rewritten_items)

    # -------------------------
    # CSP meta tags
    # -------------------------

    # The upstream site's CSP normally
    # expects its original domains.
    #
    # LocalScope rewrites resources to
    # localhost, so the original CSP can
    # block those rewritten resources.
    #
    # We remove CSP meta tags in the
    # proxy-compatible mode.
    for meta in soup.find_all(
        "meta",
        attrs={
            "http-equiv": lambda value: value
            and value.lower() == "content-security-policy"
        },
    ):
        meta.decompose()

    # -------------------------
    # LocalScope runtime proxy
    # -------------------------

    if not soup.find(
        "script",
        attrs={"data-localscope-runtime": "true"},
    ):

        runtime_script = soup.new_tag(
            "script",
            src="/__localscope/static/js/runtime_proxy.js",
        )

        runtime_script["data-localscope-runtime"] = "true"

        runtime_script["data-upstream-url"] = upstream_url

        # Must be injected before the
        # website's own scripts whenever
        # possible.
        if soup.head:

            soup.head.insert(0, runtime_script)

        else:

            soup.insert(0, runtime_script)

        # -------------------------
    # LocalScope runtime proxy
    # -------------------------

    if not soup.find(
        "script",
        attrs={"data-localscope-runtime": "true"},
    ):

        runtime_script = soup.new_tag(
            "script",
            src="/__localscope/static/js/runtime_proxy.js",
        )

        runtime_script["data-localscope-runtime"] = "true"
        runtime_script["data-upstream-url"] = upstream_url

        if soup.head:
            soup.head.insert(0, runtime_script)
        else:
            soup.insert(0, runtime_script)

    # -------------------------
    # LocalScope access UI
    # -------------------------

    hidden_patterns_json = json.dumps(HIDDEN_LINK_PATTERNS)

    header_message_json = json.dumps(HEADER_MESSAGE)

    hidden_selectors_json = json.dumps(HIDDEN_SELECTORS)

    access_script_code = f"""
        (() => {{

            const blockedPatterns =
                {hidden_patterns_json};

            const hiddenSelectors =
                {hidden_selectors_json};

            const headerMessage =
                {header_message_json};


            function applyLocalScopeUI() {{

                // Hide links by URL pattern.
                document
                    .querySelectorAll("a[href]")
                    .forEach((element) => {{

                        const href =
                            element.getAttribute("href") || "";

                        const blocked =
                            blockedPatterns.some(
                                (pattern) =>
                                    href.includes(pattern)
                            );

                        if (blocked) {{
                            element.style.display = "none";
                        }}
                    }});


                // Hide elements by explicit selector.
                hiddenSelectors.forEach(
                    (selector) => {{

                        try {{

                            document
                                .querySelectorAll(selector)
                                .forEach((element) => {{
                                    element.style.display =
                                        "none";
                                }});

                        }} catch (error) {{

                            console.warn(
                                "Invalid LocalScope selector:",
                                selector
                            );
                        }}
                    }}
                );


                // Banner.
                if (
                    headerMessage
                    &&
                    !document.getElementById(
                        "localscope-banner"
                    )
                ) {{

                    const banner =
                        document.createElement("div");

                    banner.id =
                        "localscope-banner";

                    banner.textContent =
                        headerMessage;

                    banner.style.cssText = `
                        position: relative;
                        z-index: 2147483647;
                        width: 100%;
                        box-sizing: border-box;
                        padding: 8px 16px;
                        background: #111827;
                        color: white;
                        text-align: center;
                        font-family: Arial, sans-serif;
                        font-size: 13px;
                    `;

                    document.body.prepend(
                        banner
                    );
                }}
            }}


            if (
                document.readyState === "loading"
            ) {{

                document.addEventListener(
                    "DOMContentLoaded",
                    applyLocalScopeUI
                );

            }} else {{

                applyLocalScopeUI();
            }}


            const observer =
                new MutationObserver(
                    applyLocalScopeUI
                );

            observer.observe(
                document.documentElement,
                {{
                    childList: true,
                    subtree: true
                }}
            );

        }})();
        """

    access_script = soup.new_tag("script")

    access_script["data-localscope-access-ui"] = "true"

    access_script.string = access_script_code

    if soup.body:
        soup.body.append(access_script)
    else:
        soup.append(access_script)

    return str(soup)
