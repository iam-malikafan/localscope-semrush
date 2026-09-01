def update_account_health_from_response(
    account,
    target_url: str,
    status_code: int,
):

    if not account:
        return


    health_paths = (
        "/projects/api/me",
    )


    if not any(
        path in target_url
        for path in health_paths
    ):
        return


    account.last_status_code = (
        status_code
    )


    if 200 <= status_code < 300:

        account.health = "healthy"

    elif status_code in (
        401,
        403,
    ):

        account.health = "expired"

    else:

        account.health = "error"