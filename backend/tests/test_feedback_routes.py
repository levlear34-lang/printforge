"""HTTP-level tests for feedback submission + the admin view. db.* mocked."""
import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import db
from app.config import settings
from app.main import app

client = TestClient(app)


def test_submit_feedback_success():
    with patch.object(db, "create_feedback") as mock_create:
        response = client.post("/api/feedback", json={"rating": 5, "message": "Loved it!"})
    assert response.status_code == 200
    mock_create.assert_called_once_with(5, "Loved it!")


def test_submit_feedback_rating_only():
    with patch.object(db, "create_feedback") as mock_create:
        response = client.post("/api/feedback", json={"rating": 3})
    assert response.status_code == 200
    mock_create.assert_called_once_with(3, None)


def test_submit_feedback_rejects_bad_rating():
    response = client.post("/api/feedback", json={"rating": 9, "message": "x"})
    assert response.status_code == 422


def test_submit_feedback_rejects_completely_empty():
    response = client.post("/api/feedback", json={})
    assert response.status_code == 422


def test_admin_feedback_requires_token():
    with patch.object(settings, "admin_token", "correct-admin-token"):
        response = client.get("/api/admin/feedback")
    assert response.status_code == 401


def test_admin_feedback_rejects_wrong_token():
    with patch.object(settings, "admin_token", "correct-admin-token"):
        response = client.get("/api/admin/feedback", headers={"x-admin-token": "wrong"})
    assert response.status_code == 401


def test_admin_feedback_accepts_correct_token():
    fake_rows = [{"id": 1, "rating": 5, "message": "great", "created_at": datetime.datetime.now(datetime.timezone.utc)}]
    with patch.object(settings, "admin_token", "correct-admin-token"), \
         patch.object(db, "list_feedback", return_value=fake_rows):
        response = client.get("/api/admin/feedback", headers={"x-admin-token": "correct-admin-token"})
    assert response.status_code == 200
    assert response.json()[0]["message"] == "great"


def test_admin_feedback_disabled_when_not_configured():
    with patch.object(settings, "admin_token", None):
        response = client.get("/api/admin/feedback", headers={"x-admin-token": "anything"})
    assert response.status_code == 503
