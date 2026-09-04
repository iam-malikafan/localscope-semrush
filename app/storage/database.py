import sqlite3
from uuid import uuid4
from urllib.parse import urlsplit
from app.accounts.models import Account, Proxy
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

        # Additional proxies per account (legacy; kept for migration only).
        connection.execute("""
            CREATE TABLE IF NOT EXISTS account_proxies (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                proxy_url TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0
            )
            """)

        # Global proxy pool, shared by all accounts.
        connection.execute("""
            CREATE TABLE IF NOT EXISTS proxies (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                url TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0
            )
            """)

        # One-time migration: if the global pool is empty, seed it from any
        # proxies that were previously attached to accounts so nothing is lost.
        already = connection.execute(
            "SELECT COUNT(*) AS c FROM proxies"
        ).fetchone()["c"]

        if already == 0:
            legacy_encrypted = []

            for row in connection.execute(
                "SELECT proxy_url FROM accounts WHERE proxy_url IS NOT NULL"
            ).fetchall():
                legacy_encrypted.append(row["proxy_url"])

            for row in connection.execute(
                "SELECT proxy_url FROM account_proxies"
            ).fetchall():
                legacy_encrypted.append(row["proxy_url"])

            seen_urls = set()

            for encrypted in legacy_encrypted:
                try:
                    url = decrypt_secret(encrypted)
                except Exception:
                    continue

                if url in seen_urls:
                    continue
                seen_urls.add(url)

                parts = urlsplit(url)
                label = f"{parts.hostname}:{parts.port}" if parts.hostname else "proxy"

                connection.execute(
                    """
                    INSERT INTO proxies (id, label, url, enabled)
                    VALUES (?, ?, ?, 1)
                    """,
                    (str(uuid4()), label, encrypt_secret(url)),
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

        accounts = [
            Account(
                id=row["id"],
                name=row["name"],
                cookie=decrypt_cookie(row["cookie"]),
                proxy_url=(decrypt_secret(row["proxy_url"]) if row["proxy_url"] else None),
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

        for account in accounts:
            proxy_rows = connection.execute(
                """
                SELECT id, proxy_url
                FROM account_proxies
                WHERE account_id = ?
                ORDER BY position, rowid
                """,
                (account.id,),
            ).fetchall()

            account.proxies = [
                {
                    "id": proxy_row["id"],
                    "url": decrypt_secret(proxy_row["proxy_url"]),
                }
                for proxy_row in proxy_rows
            ]

    return accounts


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

        connection.execute(
            """
            DELETE FROM account_proxies
            WHERE account_id = ?
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

# =========================================================
# Per-account proxy pool (Proxies tab)
# =========================================================

def add_account_proxy(
    proxy_id: str,
    account_id: str,
    proxy_url: str,
    position: int = 0,
):

    with get_connection() as connection:

        connection.execute(
            """
            INSERT INTO account_proxies (
                id,
                account_id,
                proxy_url,
                position
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                proxy_id,
                account_id,
                encrypt_secret(proxy_url),
                position,
            ),
        )

        connection.commit()


def list_account_proxies(
    account_id: str,
) -> list[dict]:

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT id, proxy_url
            FROM account_proxies
            WHERE account_id = ?
            ORDER BY position, rowid
            """,
            (account_id,),
        ).fetchall()

    return [
        {
            "id": row["id"],
            "url": decrypt_secret(row["proxy_url"]),
        }
        for row in rows
    ]


def delete_account_proxy(
    proxy_id: str,
):

    with get_connection() as connection:

        connection.execute(
            """
            DELETE FROM account_proxies
            WHERE id = ?
            """,
            (proxy_id,),
        )

        connection.commit()


# =========================================================
# Global proxy pool
# =========================================================

def save_proxy(
    proxy: Proxy,
):

    with get_connection() as connection:

        connection.execute(
            """
            INSERT INTO proxies (
                id,
                label,
                url,
                enabled
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                proxy.id,
                proxy.label,
                encrypt_secret(proxy.url),
                int(proxy.enabled),
            ),
        )

        connection.commit()


def load_proxies() -> list[Proxy]:

    with get_connection() as connection:

        rows = connection.execute("""
            SELECT id, label, url, enabled
            FROM proxies
            ORDER BY rowid
            """).fetchall()

    return [
        Proxy(
            id=row["id"],
            label=row["label"],
            url=decrypt_secret(row["url"]),
            enabled=bool(row["enabled"]),
        )
        for row in rows
    ]


def update_proxy(
    proxy_id: str,
    label: str,
    url: str | None,
):

    with get_connection() as connection:

        if url is not None:
            connection.execute(
                """
                UPDATE proxies
                SET label = ?, url = ?
                WHERE id = ?
                """,
                (label, encrypt_secret(url), proxy_id),
            )
        else:
            connection.execute(
                """
                UPDATE proxies
                SET label = ?
                WHERE id = ?
                """,
                (label, proxy_id),
            )

        connection.commit()


def update_proxy_enabled(
    proxy_id: str,
    enabled: bool,
):

    with get_connection() as connection:

        connection.execute(
            """
            UPDATE proxies
            SET enabled = ?
            WHERE id = ?
            """,
            (int(enabled), proxy_id),
        )

        connection.commit()


def delete_proxy_from_database(
    proxy_id: str,
):

    with get_connection() as connection:

        connection.execute(
            """
            DELETE FROM proxies
            WHERE id = ?
            """,
            (proxy_id,),
        )

        connection.commit()