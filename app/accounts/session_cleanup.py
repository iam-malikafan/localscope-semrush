from time import time


SESSION_TIMEOUT_SECONDS = 15 * 60


def cleanup_stale_sessions(
    app,
):

    now = time()

    last_seen = (
        app.state.session_last_seen
    )

    assignments = (
        app.state.account_assignments
    )

    stale_sessions = [
        session_id
        for session_id, seen_at
        in last_seen.items()
        if (
            now - seen_at
            > SESSION_TIMEOUT_SECONDS
        )
    ]


    for session_id in stale_sessions:

        last_seen.pop(
            session_id,
            None,
        )

        assignments.pop(
            session_id,
            None,
        )