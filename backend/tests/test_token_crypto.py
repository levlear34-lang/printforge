from app.services import token_crypto


def test_encrypt_decrypt_roundtrip():
    encrypted = token_crypto.encrypt_token("my-real-kaggle-token")
    assert b"my-real-kaggle-token" not in encrypted
    assert token_crypto.decrypt_token(encrypted) == "my-real-kaggle-token"


def test_encrypted_value_is_not_plaintext():
    encrypted = token_crypto.encrypt_token("secret-token-value")
    assert encrypted != b"secret-token-value"
