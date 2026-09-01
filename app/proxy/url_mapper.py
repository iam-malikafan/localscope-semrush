from urllib.parse import (
    quote,
    unquote,
    urlsplit,
    urlunsplit,
)


EXTERNAL_PROXY_PREFIX = "/proxy-external"


def build_external_proxy_url(
    absolute_url: str,
) -> str:

    parsed = urlsplit(
        absolute_url
    )

    encoded_netloc = quote(
        parsed.netloc,
        safe="",
    )

    local_url = (
        f"{EXTERNAL_PROXY_PREFIX}/"
        f"{parsed.scheme}/"
        f"{encoded_netloc}"
        f"{parsed.path}"
    )

    if parsed.query:
        local_url += (
            f"?{parsed.query}"
        )

    if parsed.fragment:
        local_url += (
            f"#{parsed.fragment}"
        )

    return local_url


def build_external_target_url(
    scheme: str,
    encoded_netloc: str,
    path: str,
    query_string: str = "",
) -> str:

    netloc = unquote(
        encoded_netloc
    )

    return urlunsplit(
        (
            scheme,
            netloc,
            f"/{path}" if path else "/",
            query_string,
            "",
        )
    )


def map_upstream_url_to_local(
    absolute_url: str,
    target_base_url: str,
) -> str:

    resource = urlsplit(
        absolute_url
    )

    target = urlsplit(
        target_base_url
    )

    if (
        resource.scheme == target.scheme
        and resource.netloc == target.netloc
    ):

        local_url = (
            resource.path or "/"
        )

        if resource.query:
            local_url += (
                f"?{resource.query}"
            )

        if resource.fragment:
            local_url += (
                f"#{resource.fragment}"
            )

        return local_url

    return build_external_proxy_url(
        absolute_url
    )

def decode_external_proxy_url(
    encoded_url: str,
) -> str:

    return unquote(encoded_url)

