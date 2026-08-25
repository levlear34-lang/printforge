"""HTTP-level tests for signup/login/logout/me. db.* mocked throughout."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.services import auth

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


def test_signup_sets_session_cookie():
    with patch.object(db, "create_user", return_value=_fake_user()):
        response = client.post("/api/signup", json={"email": "a@example.com", "password": "longenoughpw"})
    assert response.status_code == 200
    assert response.json()["email"] == "a@example.com"
    assert auth.SESSION_COOKIE_NAME in response.cookies


def test_signup_duplicate_email_409():
    with patch.object(db, "create_user", side_effect=db.UserExistsError("exists")):
        response = client.post("/api/signup", json={"email": "a@example.com", "password": "longenoughpw"})
    assert response.status_code == 409


def test_login_success_sets_cookie():
    with patch.object(db, "get_user_by_email", return_value=_fake_user()):
        response = client.post("/api/login", json={"email": "a@example.com", "password": "correct-password"})
    assert response.status_code == 200
    assert auth.SESSION_COOKIE_NAME in response.cookies


def test_login_wrong_password_401():
    with patch.object(db, "get_user_by_email", return_value=_fake_user()):
        response = client.post("/api/login", json={"email": "a@example.com", "password": "wrong"})
    assert response.status_code == 401


def test_me_logged_out():
    fresh_client = TestClient(app)
    response = fresh_client.get("/api/me")
    assert response.status_code == 200
    assert response.json() == {"logged_in": False}


def test_me_logged_in_after_login():
    fresh_client = TestClient(app)
    with patch.object(db, "get_user_by_email", return_value=_fake_user()):
        login_response = fresh_client.post("/api/login", json={"email": "a@example.com", "password": "correct-password"})
    assert login_response.status_code == 200

    with patch.object(db, "get_user_by_id", return_value=_fake_user()):
        response = fresh_client.get("/api/me")
    assert response.status_code == 200
    body = response.json()
    assert body["logged_in"] is True
    assert body["email"] == "a@example.com"
    assert "password_hash" not in body


def test_logout_clears_cookie():
    fresh_client = TestClient(app)
    with patch.object(db, "get_user_by_email", return_value=_fake_user()):
        fresh_client.post("/api/login", json={"email": "a@example.com", "password": "correct-password"})
    response = fresh_client.post("/api/logout")
    assert response.status_code == 200
    me_response = fresh_client.get("/api/me")
    assert me_response.json() == {"logged_in": False}
