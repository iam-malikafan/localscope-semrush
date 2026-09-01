from urllib.parse import urljoin

from app.proxy.url_mapper import (
    map_upstream_url_to_local,
)


def rewrite_redirect_location(
    location: str | None,
    upstream_url: str,
    target_base_url: str,
) -> str | None:

    if not location:
        return None

    absolute_url = urljoin(
        upstream_url,
        location,
    )

    return map_upstream_url_to_local(
        absolute_url=absolute_url,
        target_base_url=target_base_url,
    )