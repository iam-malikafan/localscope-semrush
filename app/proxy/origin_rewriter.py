from urllib.parse import (
    urlsplit,
    urlunsplit,
)


def rewrite_origin_headers(
    headers: dict,
    upstream_url: str,
) -> dict:

    result = dict(headers)

    parsed_upstream = urlsplit(
        upstream_url
    )

    upstream_origin = (
        f"{parsed_upstream.scheme}://"
        f"{parsed_upstream.netloc}"
    )


    for name in list(result):

        name_lower = name.lower()


        # -------------------------
        # Origin
        # -------------------------

        if name_lower == "origin":

            result[name] = (
                upstream_origin
            )


        # -------------------------
        # Referer
        # -------------------------

        elif name_lower == "referer":

            original_referer = (
                result[name]
            )

            try:

                parsed_referer = urlsplit(
                    original_referer
                )

                result[name] = urlunsplit(
                    (
                        parsed_upstream.scheme,
                        parsed_upstream.netloc,
                        parsed_referer.path,
                        parsed_referer.query,
                        "",
                    )
                )

            except ValueError:

                result[name] = (
                    upstream_origin
                )


    return result