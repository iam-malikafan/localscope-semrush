import re


def rewrite_set_cookie(
    cookie: str,
) -> str:

    # Remove upstream Domain attribute.
    #
    # The browser will then treat this as
    # a host-only cookie belonging to
    # 127.0.0.1.
    cookie = re.sub(
        r";\s*Domain=[^;]+",
        "",
        cookie,
        flags=re.IGNORECASE,
    )

    return cookie