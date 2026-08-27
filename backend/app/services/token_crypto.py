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
    try:
        return Fernet(settings.token_encryption_key)
    except ValueError as exc:
        # Fernet's own constructor validates the key format (32 url-safe
        # base64-encoded bytes) and raises ValueError for anything else --
        # e.g. a plain random string pasted in by mistake instead of a
        # real Fernet key. Previously unhandled here, surfacing as a raw
        # 500 with no useful message; found via a real deploy where
        # TOKEN_ENCRYPTION_KEY had been set to something not in that
        # format.
        raise EncryptionNotConfiguredError(
            "TOKEN_ENCRYPTION_KEY is set but isn't a valid Fernet key. "
            "Generate one with: python -c \"from cryptography.fernet "
            "import Fernet; print(Fernet.generate_key().decode())\""
        ) from exc


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
