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


def encrypt_cookie(
    cookie: str,
) -> str:

    cipher = get_cipher()

    encrypted = cipher.encrypt(
        cookie.encode("utf-8")
    )

    return encrypted.decode(
        "utf-8"
    )


def decrypt_cookie(
    encrypted_cookie: str,
) -> str:

    cipher = get_cipher()

    try:

        decrypted = cipher.decrypt(
            encrypted_cookie.encode(
                "utf-8"
            )
        )

    except InvalidToken as error:

        raise RuntimeError(
            "Stored account cookie "
            "could not be decrypted"
        ) from error

    return decrypted.decode(
        "utf-8"
    )