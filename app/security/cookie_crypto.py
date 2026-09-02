import os

from cryptography.fernet import (
    Fernet,
    InvalidToken,
)


def get_cipher() -> Fernet:

    key = os.getenv(
        "LOCALSCOPE_ENCRYPTION_KEY"
    )

    if not key:
        raise RuntimeError(
            "LOCALSCOPE_ENCRYPTION_KEY "
            "is not configured"
        )

    return Fernet(
        key.encode("utf-8")
    )


def encrypt_secret(
    value: str,
) -> str:

    cipher = get_cipher()

    encrypted = cipher.encrypt(
        value.encode("utf-8")
    )

    return encrypted.decode(
        "utf-8"
    )


def decrypt_secret(
    encrypted_value: str,
) -> str:

    cipher = get_cipher()

    try:

        decrypted = cipher.decrypt(
            encrypted_value.encode(
                "utf-8"
            )
        )

    except InvalidToken as error:

        raise RuntimeError(
            "Stored encrypted value "
            "could not be decrypted"
        ) from error

    return decrypted.decode(
        "utf-8"
    )

# Backwards-compatible names for account cookie encryption.
def encrypt_cookie(cookie: str) -> str:
    return encrypt_secret(cookie)


def decrypt_cookie(encrypted_cookie: str) -> str:
    return decrypt_secret(encrypted_cookie)
