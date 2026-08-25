import pytest

from app.services import auth


def test_hash_and_verify_password_roundtrip():
    hashed = auth.hash_password("correct horse battery staple")
    assert auth.verify_password("correct horse battery staple", hashed)
    assert not auth.verify_password("wrong password", hashed)


def test_hash_is_not_the_plaintext():
    hashed = auth.hash_password("my-secret-password")
    assert "my-secret-password" not in hashed


def test_validate_email_accepts_valid():
    auth.validate_email("someone@example.com")


@pytest.mark.parametrize("bad_email", ["", "not-an-email", "missing@domain", "@example.com"])
def test_validate_email_rejects_invalid(bad_email):
    with pytest.raises(auth.AuthError):
        auth.validate_email(bad_email)


def test_validate_password_rejects_short():
    with pytest.raises(auth.AuthError):
        auth.validate_password("short")


def test_validate_password_accepts_long_enough():
    auth.validate_password("longenough1")


def test_session_token_roundtrip():
    token = auth.create_session_token(42)
    assert auth.read_session_token(token) == 42


def test_session_token_rejects_garbage():
    assert auth.read_session_token("not-a-real-token") is None


def test_session_token_rejects_none():
    assert auth.read_session_token(None) is None
