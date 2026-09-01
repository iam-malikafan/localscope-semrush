from dataclasses import dataclass
from uuid import uuid4


@dataclass
class Account:
    id: str
    name: str
    cookie: str
    enabled: bool = False

    health: str = "unknown"
    last_status_code: int | None = None


def create_account(
    name: str,
    cookie: str,
) -> Account:

    return Account(
        id=str(uuid4()),
        name=name,
        cookie=cookie,
        enabled=False,
        health="unknown",
        last_status_code=None,
    )