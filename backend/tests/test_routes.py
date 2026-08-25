"""HTTP-level tests for the create-flow routes. Kaggle calls mocked."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import jobs, kaggle_client

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_jobs():
    jobs._JOBS.clear()
    yield
    jobs._JOBS.clear()


def test_create_returns_job_id():
    with patch.object(kaggle_client, "resolve_username", return_value="testuser"), \
         patch.object(kaggle_client, "push_kernel", return_value="testuser/printforge-x"):
        response = client.post(
            "/api/create",
            json={"text": "phone stand, 2 slots, 18 degrees", "kaggle_token": "tok"},
        )
    assert response.status_code == 200
    assert "job_id" in response.json()


def test_create_bad_token_returns_401():
    with patch.object(kaggle_client, "resolve_username", side_effect=kaggle_client.KaggleAuthError("bad")):
        response = client.post(
            "/api/create",
            json={"text": "phone stand, 2 slots, 18 degrees", "kaggle_token": "bad"},
        )
    assert response.status_code == 401


def test_job_status_not_found():
    response = client.get("/api/jobs/does-not-exist")
    assert response.status_code == 404


def test_job_status_hides_local_paths_and_exposes_urls(tmp_path, monkeypatch):
    from app.services import generation
    import json
    import os

    job_id = jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel")
    jobs.update_job(job_id, status="running", last_checked_at=0.0)

    dest_dir = os.path.join(str(tmp_path), job_id)
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "model.stl"), "w") as f:
        f.write("fake")
    with open(os.path.join(dest_dir, "preview.png"), "w") as f:
        f.write("fake")
    with open(os.path.join(dest_dir, "report.json"), "w") as f:
        json.dump({"passed": True}, f)
    monkeypatch.setattr(generation, "GENERATED_ROOT", str(tmp_path))

    with patch.object(kaggle_client, "get_status", return_value="COMPLETE"), \
         patch.object(kaggle_client, "retrieve_output", return_value=[]):
        response = client.get(f"/api/jobs/{job_id}")

    body = response.json()
    assert body["status"] == "complete"
    assert body["preview_url"] == f"/api/jobs/{job_id}/preview"
    assert body["download_url"] == f"/api/jobs/{job_id}/download"
    assert "result" not in body
    assert "C:" not in response.text and str(tmp_path) not in response.text


def test_download_not_ready_returns_409():
    job_id = jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel")
    response = client.get(f"/api/jobs/{job_id}/download")
    assert response.status_code == 409


def test_preview_not_available_returns_404():
    job_id = jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel")
    response = client.get(f"/api/jobs/{job_id}/preview")
    assert response.status_code == 404
