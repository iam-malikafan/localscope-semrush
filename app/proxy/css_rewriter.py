import re

from urllib.parse import urljoin

from app.proxy.url_mapper import (
    map_upstream_url_to_local,
)


def rewrite_css(
    css: str,
    upstream_url: str,
    target_base_url: str,
) -> str:

    def rewrite_url(match):

        quote = match.group(1) or ""

        value = match.group(2).strip()


        if (
            not value
            or value.startswith("data:")
            or value.startswith("#")
            or value.startswith("blob:")
        ):
            return match.group(0)


        absolute_url = urljoin(
            upstream_url,
            value,
        )


        mapped_url = map_upstream_url_to_local(
            absolute_url=absolute_url,
            target_base_url=target_base_url,
        )


        return (
            f"url({quote}"
            f"{mapped_url}"
            f"{quote})"
        )


    return re.sub(
        r"url\(\s*(['\"]?)(.*?)\1\s*\)",
        rewrite_url,
        css,
        flags=re.IGNORECASE,
    )