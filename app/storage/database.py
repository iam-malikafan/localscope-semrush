import sqlite3
from app.accounts.models import Account
from app.security.cookie_crypto import (
    encrypt_cookie,
    decrypt_cookie,
    encrypt_secret,
    decrypt_secret,
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
                enabled INTEGER NOT NULL DEFAULT 0,
                proxy_url TEXT
            )
            """)

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(accounts)").fetchall()
        }

        if "proxy_url" not in columns:
            connection.execute(
                "ALTER TABLE accounts ADD COLUMN proxy_url TEXT"
            )

        # Existing accounts cannot safely be enabled until a proxy is configured.
        connection.execute(
            "UPDATE accounts SET enabled = 0 WHERE proxy_url IS NULL"
        )

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
                enabled,
                proxy_url
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                account.id,
                account.name,
                encrypt_cookie(account.cookie),
                int(account.enabled),
                encrypt_secret(account.proxy_url) if account.proxy_url else None,
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
                enabled,
                proxy_url
            FROM accounts
            ORDER BY rowid
            """).fetchall()

    return [
        Account(
            id=row["id"],
            name=row["name"],
            cookie=decrypt_cookie(row["cookie"]),
            proxy_url=(decrypt_secret(row["proxy_url"]) if row["proxy_url"] else None),
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




def update_account(
    account_id: str,
    name: str,
    cookie: str | None,
    proxy_url: str | None,
):
    with get_connection() as connection:
        if cookie is not None and proxy_url is not None:
            connection.execute(
                """
                UPDATE accounts
                SET name = ?, cookie = ?, proxy_url = ?
                WHERE id = ?
                """,
                (
                    name,
                    encrypt_cookie(cookie),
                    encrypt_secret(proxy_url),
                    account_id,
                ),
            )

        elif cookie is not None:
            connection.execute(
                """
                UPDATE accounts
                SET name = ?, cookie = ?
                WHERE id = ?
                """,
                (
                    name,
                    encrypt_cookie(cookie),
                    account_id,
                ),
            )

        elif proxy_url is not None:
            connection.execute(
                """
                UPDATE accounts
                SET name = ?, proxy_url = ?
                WHERE id = ?
                """,
                (
                    name,
                    encrypt_secret(proxy_url),
                    account_id,
                ),
            )

        else:
            connection.execute(
                """
                UPDATE accounts
                SET name = ?
                WHERE id = ?
                """,
                (
                    name,
                    account_id,
                ),
            )

        connection.commit()