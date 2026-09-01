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