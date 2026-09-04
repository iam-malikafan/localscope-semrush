from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class Account:
    id: str
    name: str
    cookie: str
    proxy_url: str | None = None
    enabled: bool = False

    # Additional proxies managed from the Proxies tab.
    # Each entry is {"id": str, "url": str}. The account's
    # effective rotation pool is proxy_url + these.
    proxies: list[dict] = field(default_factory=list)

    health: str = "unknown"
    last_status_code: int | None = None

    proxy_health: str = "unknown"
    proxy_status_code: int | None = None


def create_account(
    name: str,
    cookie: str,
    proxy_url: str | None = None,
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


@dataclass
class Proxy:
    """A proxy in the global pool, shared by all accounts."""
    id: str
    label: str
    url: str
    enabled: bool = False

    # Runtime-only (not persisted), same pattern as Account.health.
    health: str = "unknown"
    status_code: int | None = None


def create_proxy(
    label: str,
    url: str,
) -> Proxy:

    return Proxy(
        id=str(uuid4()),
        label=label,
        url=url,
        enabled=False,
        health="unknown",
        status_code=None,
    )