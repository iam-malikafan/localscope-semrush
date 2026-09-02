from dataclasses import dataclass
from uuid import uuid4


@dataclass
class Account:
    id: str
    name: str
    cookie: str
    proxy_url: str | None = None
    enabled: bool = False

    health: str = "unknown"
    last_status_code: int | None = None

    proxy_health: str = "unknown"
    proxy_status_code: int | None = None


def create_account(
    name: str,
    cookie: str,
    proxy_url: str,
) -> Account:

    return Account(
        id=str(uuid4()),
        name=name,
        cookie=cookie,
        proxy_url=proxy_url,
        enabled=False,
        health="unknown",
        last_status_code=None,
        proxy_health="unknown",
        proxy_status_code=None,
    )