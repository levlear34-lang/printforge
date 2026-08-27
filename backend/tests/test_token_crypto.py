from unittest.mock import patch

import pytest

from app.config import settings
from app.services import token_crypto


def test_encrypt_decrypt_roundtrip():
    encrypted = token_crypto.encrypt_token("my-real-kaggle-token")
    assert b"my-real-kaggle-token" not in encrypted
    assert token_crypto.decrypt_token(encrypted) == "my-real-kaggle-token"


def test_encrypted_value_is_not_plaintext():
    encrypted = token_crypto.encrypt_token("secret-token-value")
    assert encrypted != b"secret-token-value"


def test_malformed_key_raises_clean_error_not_raw_valueerror():
    """Regression guard for a real production incident: TOKEN_ENCRYPTION_KEY
    set to something that isn't a valid Fernet key (e.g. a plain random
    string instead of Fernet.generate_key() output) used to raise a bare
    ValueError from Fernet's own constructor, surfacing as an unhandled
    500 with no useful message on the live site.
    """
    with patch.object(settings, "token_encryption_key", "not-a-real-fernet-key"):
        with pytest.raises(token_crypto.EncryptionNotConfiguredError):
            token_crypto.encrypt_token("some-token")


def test_missing_key_raises_clean_error():
    with patch.object(settings, "token_encryption_key", None):
        with pytest.raises(token_crypto.EncryptionNotConfiguredError):
            token_crypto.encrypt_token("some-token")
