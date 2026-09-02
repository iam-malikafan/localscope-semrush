import httpx


HEALTH_CHECK_URL = (
    "https://www.semrush.com/projects/api/me"
)


async def check_account_health(
    client: httpx.AsyncClient,
    cookie: str,
) -> tuple[str, int | None]:

    try:

        response = await client.get(
            HEALTH_CHECK_URL,
            headers={
                "cookie": cookie,
                "accept": "application/json",
                "referer": "https://www.semrush.com/",
            },
        )

    except httpx.RequestError:

        return (
            "error",
            None,
        )


    if response.status_code == 200:

        return (
            "healthy",
            200,
        )


    if response.status_code in (
        401,
        403,
    ):

        return (
            "expired",
            response.status_code,
        )


    return (
        "error",
        response.status_code,
    )

async def check_proxy_health(
    proxy_url: str,
) -> tuple[str, int | None, str | None]:
    """Check whether the configured proxy can reach Semrush."""

    try:
        async with httpx.AsyncClient(
            proxy=proxy_url,
            follow_redirects=False,
            timeout=15.0,
        ) as client:
            response = await client.get(
                "https://www.semrush.com/",
                headers={"accept": "text/html,application/xhtml+xml"},
            )

    except httpx.ProxyError as error:
        return "error", None, f"Proxy connection failed: {error}"
    except httpx.RequestError as error:
        return "error", None, f"Proxy request failed: {error}"

    if response.status_code == 407:
        return "error", response.status_code, "Proxy authentication failed."

    if response.status_code >= 500:
        return "error", response.status_code, f"Semrush returned HTTP {response.status_code}."

    return "healthy", response.status_code, None
