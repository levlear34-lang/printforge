"""Encrypt/decrypt a saved Kaggle token at rest, using Fernet (AES-128-CBC
+ HMAC, authenticated encryption) from the `cryptography` library.

TOKEN_ENCRYPTION_KEY must be a Fernet key (44-char urlsafe-base64), not just
any random string -- generate one with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class EncryptionNotConfiguredError(Exception):
    """TOKEN_ENCRYPTION_KEY is missing -- can't save/read tokens safely."""


def _fernet():
    if not settings.token_encryption_key:
        raise EncryptionNotConfiguredError(
            "TOKEN_ENCRYPTION_KEY is not set. Saved-token features are "
            "disabled until it's configured."
        )
    return Fernet(settings.token_encryption_key)


def encrypt_token(token):
    return _fernet().encrypt(token.strip().encode("utf-8"))


def decrypt_token(encrypted_token):
    try:
        return _fernet().decrypt(bytes(encrypted_token)).decode("utf-8")
    except InvalidToken as exc:
        raise EncryptionNotConfiguredError(
            "Saved token could not be decrypted -- it may have been "
            "encrypted with a different TOKEN_ENCRYPTION_KEY."
        ) from exc
