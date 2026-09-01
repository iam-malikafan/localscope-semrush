import sqlite3
from app.accounts.models import Account
from app.security.cookie_crypto import (
    encrypt_cookie,
    decrypt_cookie,
)

DATABASE_PATH = "localscope.db"


def get_connection():

    connection = sqlite3.connect(DATABASE_PATH)

    connection.row_factory = sqlite3.Row

    return connection


def initialize_database():

    with get_connection() as connection:

        connection.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                cookie TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0
            )
            """)

        connection.commit()


def save_account(
    account: Account,
):

    with get_connection() as connection:

        connection.execute(
            """
            INSERT INTO accounts (
                id,
                name,
                cookie,
                enabled
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                account.id,
                account.name,
                encrypt_cookie(account.cookie),
                int(account.enabled),
            ),
        )

        connection.commit()


def load_accounts() -> list[Account]:

    with get_connection() as connection:

        rows = connection.execute("""
            SELECT
                id,
                name,
                cookie,
                enabled
            FROM accounts
            ORDER BY rowid
            """).fetchall()

    return [
        Account(
            id=row["id"],
            name=row["name"],
            cookie=decrypt_cookie(row["cookie"]),
            enabled=bool(row["enabled"]),
        )
        for row in rows
    ]


def update_account_enabled(
    account_id: str,
    enabled: bool,
):

    with get_connection() as connection:

        connection.execute(
            """
            UPDATE accounts
            SET enabled = ?
            WHERE id = ?
            """,
            (
                int(enabled),
                account_id,
            ),
        )

        connection.commit()


def update_account_cookie(
    account_id: str,
    cookie: str,
):

    with get_connection() as connection:

        connection.execute(
            """
            UPDATE accounts
            SET cookie = ?
            WHERE id = ?
            """,
            (
                encrypt_cookie(cookie),
                account_id,
            ),
        )

        connection.commit()


def delete_account_from_database(
    account_id: str,
):

    with get_connection() as connection:

        connection.execute(
            """
            DELETE FROM accounts
            WHERE id = ?
            """,
            (account_id,),
        )

        connection.commit()
