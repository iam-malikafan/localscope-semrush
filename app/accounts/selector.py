def get_account_by_id(
    accounts,
    account_id: str,
):
    for account in accounts:
        if account.id == account_id:
            return account

    return None


def select_account_for_session(
    app,
    session_id: str,
):
    accounts = app.state.accounts

    assignments = (
        app.state.account_assignments
    )

    existing_account_id = assignments.get(
        session_id
    )

    if existing_account_id:

        account = get_account_by_id(
            accounts,
            existing_account_id,
        )

        # Keep using it only while it is
        # enabled and not expired.
        if (
            account
            and account.enabled
            and account.health != "expired"
        ):
            return account

        # Deleted, disabled, or expired.
        assignments.pop(
            session_id,
            None,
        )


    available_accounts = [
        account
        for account in accounts
        if (
            account.enabled
            and account.health != "expired"
        )
    ]

    if not available_accounts:
        return None


    index = (
        app.state.next_account_index
        % len(available_accounts)
    )

    account = available_accounts[index]

    app.state.next_account_index = (
        index + 1
    )

    assignments[session_id] = (
        account.id
    )

    return account