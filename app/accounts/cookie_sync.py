from http.cookies import SimpleCookie


def parse_cookie_header(
    cookie_header: str,
) -> dict[str, str]:

    cookies = SimpleCookie()

    if cookie_header:
        cookies.load(cookie_header)

    return {
        name: morsel.value
        for name, morsel in cookies.items()
    }


def build_cookie_header(
    cookies: dict[str, str],
) -> str:

    return "; ".join(
        f"{name}={value}"
        for name, value in cookies.items()
    )


def update_account_cookie(
    current_cookie: str,
    set_cookie_headers: list[str],
) -> str:

    cookies = parse_cookie_header(
        current_cookie
    )


    for set_cookie_header in set_cookie_headers:

        parsed = SimpleCookie()

        try:
            parsed.load(
                set_cookie_header
            )
        except Exception:
            continue


        for name, morsel in parsed.items():

            # Cookie deletion.
            max_age = morsel["max-age"]

            if max_age == "0":
                cookies.pop(
                    name,
                    None,
                )
                continue


            cookies[name] = morsel.value


    return build_cookie_header(
        cookies
    )