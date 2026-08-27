"""HTTP-level tests for dashboard/account routes. db.*/kaggle_client.* mocked."""
import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import db
from app.config import settings
from app.main import app
from app.services import auth, kaggle_client

client = TestClient(app)


def _fake_user(user_id=1, email="a@example.com"):
    return {
        "id": user_id,
        "email": email,
        "password_hash": auth.hash_password("correct-password"),
        "saved_kaggle_token_encrypted": None,
        "saved_kaggle_username": None,
        "created_at": "2026-08-25T00:00:00Z",
    }


def _logged_in_client():
    c = TestClient(app)
    with patch.object(db, "get_user_by_email", return_value=_fake_user()):
        c.post("/api/login", json={"email": "a@example.com", "password": "correct-password"})
    return c


def test_dashboard_jobs_requires_login():
    fresh_client = TestClient(app)
    response = fresh_client.get("/api/dashboard/jobs")
    assert response.status_code == 401


def test_dashboard_jobs_lists_history():
    c = _logged_in_client()
    now = datetime.datetime.now(datetime.timezone.utc)
    fake_job = {
        "id": "abc123",
        "prompt": "phone stand",
        "classification": "parametric",
        "status": "complete",
        "stl_path": None,
        "preview_path": None,
        "created_at": now,
        "expires_at": now,
    }
    with patch.object(db, "list_job_history", return_value=[fake_job]):
        response = c.get("/api/dashboard/jobs")
    assert response.status_code == 200
    body = response.json()
    assert body[0]["id"] == "abc123"
    assert body[0]["preview_url"] is None  # file doesn't exist locally


def test_save_token_requires_login():
    fresh_client = TestClient(app)
    response = fresh_client.post("/api/account/token", json={"kaggle_token": "x"})
    assert response.status_code == 401


def test_save_token_success():
    c = _logged_in_client()
    with patch.object(kaggle_client, "resolve_username", return_value="realuser"), \
         patch.object(db, "save_kaggle_token") as mock_save:
        response = c.post("/api/account/token", json={"kaggle_token": "a-real-token"})
    assert response.status_code == 200
    assert response.json()["saved_kaggle_username"] == "realuser"
    mock_save.assert_called_once()


def test_save_token_with_malformed_encryption_key_returns_clean_503():
    """Regression guard for a real production incident: a malformed
    TOKEN_ENCRYPTION_KEY used to crash this endpoint with a raw,
    unhandled 500 instead of a clean error.
    """
    c = _logged_in_client()
    with patch.object(kaggle_client, "resolve_username", return_value="realuser"), \
         patch.object(settings, "token_encryption_key", "not-a-real-fernet-key"):
        response = c.post("/api/account/token", json={"kaggle_token": "a-real-token"})
    assert response.status_code == 503


def test_save_token_bad_token_401():
    c = _logged_in_client()
    with patch.object(kaggle_client, "resolve_username", side_effect=kaggle_client.KaggleAuthError("bad")):
        response = c.post("/api/account/token", json={"kaggle_token": "bad"})
    assert response.status_code == 401


def test_delete_token():
    c = _logged_in_client()
    with patch.object(db, "delete_kaggle_token") as mock_delete:
        response = c.delete("/api/account/token")
    assert response.status_code == 200
    mock_delete.assert_called_once_with(1)


def test_delete_account():
    c = _logged_in_client()
    with patch.object(db, "delete_user") as mock_delete:
        response = c.delete("/api/account")
    assert response.status_code == 200
    mock_delete.assert_called_once_with(1)
