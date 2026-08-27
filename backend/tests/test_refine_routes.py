"""HTTP-level tests for the /api/refine routes. Kaggle calls mocked."""
import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import jobs, kaggle_client, refinement

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_jobs():
    jobs._JOBS.clear()
    yield
    jobs._JOBS.clear()


def test_refine_returns_job_id():
    with patch.object(kaggle_client, "resolve_username", return_value="testuser"), \
         patch.object(kaggle_client, "push_kernel", return_value="testuser/printforge-x"):
        response = client.post(
            "/api/refine",
            json={"idea": "a batman phone holder", "kaggle_token": "tok"},
        )
    assert response.status_code == 200
    assert "job_id" in response.json()


def test_refine_missing_token_returns_422():
    response = client.post("/api/refine", json={"idea": "a batman phone holder"})
    assert response.status_code == 422


def test_refine_round_two_accepts_feedback():
    with patch.object(kaggle_client, "resolve_username", return_value="testuser"), \
         patch.object(kaggle_client, "push_kernel", return_value="testuser/printforge-x") as mock_push:
        response = client.post(
            "/api/refine",
            json={
                "idea": "a detailed batman phone holder description",
                "feedback": "make it more armored",
                "kaggle_token": "tok",
            },
        )
    assert response.status_code == 200
    mock_push.assert_called_once()


def test_refine_status_not_found():
    response = client.get("/api/refine/does-not-exist")
    assert response.status_code == 404


def test_refine_status_exposes_refined_prompt_not_local_paths(tmp_path, monkeypatch):
    job_id = jobs.create_job("an idea", "refine", "refine", "tok", "user", "user/kernel")
    jobs.update_job(job_id, status="running", last_checked_at=0.0)

    dest_dir = os.path.join(str(tmp_path), job_id)
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "report.json"), "w") as f:
        json.dump({"passed": True, "refined_prompt": "a very detailed prompt"}, f)
    monkeypatch.setattr(refinement, "REFINEMENTS_ROOT", str(tmp_path))

    with patch.object(kaggle_client, "get_status", return_value="COMPLETE"), \
         patch.object(kaggle_client, "retrieve_output", return_value=[]):
        response = client.get(f"/api/refine/{job_id}")

    body = response.json()
    assert body["status"] == "complete"
    assert body["refined_prompt"] == "a very detailed prompt"
    assert "result" not in body
    assert str(tmp_path) not in response.text
