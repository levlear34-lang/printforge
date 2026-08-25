"""app.services.accounts tests. db.* and kaggle_client.* are always mocked
here -- no real Postgres or Kaggle calls (see db.py's module docstring).
"""
from unittest.mock import patch

import pytest

from app import db
from app.services import accounts, auth, kaggle_client, token_crypto


def _fake_user(user_id=1, email="a@example.com", encrypted_token=None, saved_username=None):
    return {
        "id": user_id,
        "email": email,
        "password_hash": auth.hash_password("correct-password"),
        "saved_kaggle_token_encrypted": encrypted_token,
        "saved_kaggle_username": saved_username,
        "created_at": "2026-08-25T00:00:00Z",
    }


def test_signup_creates_user():
    with patch.object(db, "create_user", return_value=_fake_user()) as mock_create:
        user = accounts.signup("a@example.com", "longenoughpassword")
    assert user["email"] == "a@example.com"
    mock_create.assert_called_once()


def test_signup_rejects_invalid_email():
    with pytest.raises(auth.AuthError):
        accounts.signup("not-an-email", "longenoughpassword")


def test_signup_rejects_short_password():
    with pytest.raises(auth.AuthError):
        accounts.signup("a@example.com", "short")


def test_signup_duplicate_email_returns_409():
    with patch.object(db, "create_user", side_effect=db.UserExistsError("exists")):
        with pytest.raises(auth.AuthError) as exc_info:
            accounts.signup("a@example.com", "longenoughpassword")
    assert exc_info.value.status_code == 409


def test_login_success():
    with patch.object(db, "get_user_by_email", return_value=_fake_user()):
        user = accounts.login("a@example.com", "correct-password")
    assert user["email"] == "a@example.com"


def test_login_wrong_password_returns_401():
    with patch.object(db, "get_user_by_email", return_value=_fake_user()):
        with pytest.raises(auth.AuthError) as exc_info:
            accounts.login("a@example.com", "wrong-password")
    assert exc_info.value.status_code == 401


def test_login_nonexistent_user_returns_401():
    with patch.object(db, "get_user_by_email", return_value=None):
        with pytest.raises(auth.AuthError) as exc_info:
            accounts.login("nobody@example.com", "whatever-password")
    assert exc_info.value.status_code == 401


def test_public_user_view_never_leaks_password_or_token():
    encrypted = token_crypto.encrypt_token("real-token")
    user = _fake_user(encrypted_token=encrypted, saved_username="someuser")
    view = accounts.public_user_view(user)
    assert "password_hash" not in view
    assert "saved_kaggle_token_encrypted" not in view
    assert view["has_saved_token"] is True
    assert view["saved_kaggle_username"] == "someuser"


def test_public_user_view_no_saved_token():
    view = accounts.public_user_view(_fake_user())
    assert view["has_saved_token"] is False


def test_save_kaggle_token_encrypts_and_stores():
    with patch.object(kaggle_client, "resolve_username", return_value="realuser"), \
         patch.object(db, "save_kaggle_token") as mock_save:
        username = accounts.save_kaggle_token(1, "a-real-token")
    assert username == "realuser"
    args = mock_save.call_args[0]
    assert args[0] == 1
    assert args[1] != b"a-real-token"  # encrypted, not plaintext
    assert args[2] == "realuser"


def test_save_kaggle_token_rejects_bad_token():
    with patch.object(kaggle_client, "resolve_username", side_effect=kaggle_client.KaggleAuthError("bad")):
        with pytest.raises(auth.AuthError) as exc_info:
            accounts.save_kaggle_token(1, "bad-token")
    assert exc_info.value.status_code == 401


def test_get_saved_token_plaintext_decrypts():
    encrypted = token_crypto.encrypt_token("the-real-token")
    with patch.object(db, "get_user_by_id", return_value=_fake_user(encrypted_token=encrypted)):
        assert accounts.get_saved_token_plaintext(1) == "the-real-token"


def test_get_saved_token_plaintext_none_when_no_token_saved():
    with patch.object(db, "get_user_by_id", return_value=_fake_user()):
        assert accounts.get_saved_token_plaintext(1) is None


def test_get_saved_token_plaintext_none_when_user_missing():
    with patch.object(db, "get_user_by_id", return_value=None):
        assert accounts.get_saved_token_plaintext(999) is None


def test_delete_account_calls_db():
    with patch.object(db, "delete_user") as mock_delete:
        accounts.delete_account(1)
    mock_delete.assert_called_once_with(1)
