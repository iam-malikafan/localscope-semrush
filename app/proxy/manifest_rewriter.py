import json
from urllib.parse import urljoin, urlsplit

from app.proxy.url_mapper import build_external_proxy_url


def rewrite_manifest_url(
    value: str,
    upstream_url: str,
    target_base_url: str,
) -> str:

    absolute_url = urljoin(
        upstream_url,
        value,
    )

    parsed_url = urlsplit(
        absolute_url
    )

    parsed_target = urlsplit(
        target_base_url
    )

    # Same configured target domain
    if (
        parsed_url.scheme == parsed_target.scheme
        and parsed_url.netloc == parsed_target.netloc
    ):
        local_url = f"/proxy{parsed_url.path}"

        if parsed_url.query:
            local_url += f"?{parsed_url.query}"

        if parsed_url.fragment:
            local_url += f"#{parsed_url.fragment}"

        return local_url

    # Resource belongs to another domain
    return build_external_proxy_url(
        absolute_url
    )


def rewrite_manifest(
    body: bytes,
    upstream_url: str,
    target_base_url: str,
) -> bytes:

    try:
        manifest = json.loads(
            body.decode(
                "utf-8",
                errors="replace",
            )
        )

    except json.JSONDecodeError:
        return body


    # Manifest icons
    icons = manifest.get(
        "icons",
        []
    )

    for icon in icons:

        src = icon.get("src")

        if src:
            icon["src"] = rewrite_manifest_url(
                value=src,
                upstream_url=upstream_url,
                target_base_url=target_base_url,
            )


    # Common manifest navigational URLs
    for field in (
        "start_url",
        "scope",
    ):

        value = manifest.get(field)

        if value:
            manifest[field] = rewrite_manifest_url(
                value=value,
                upstream_url=upstream_url,
                target_base_url=target_base_url,
            )


    return json.dumps(
        manifest
    ).encode("utf-8")