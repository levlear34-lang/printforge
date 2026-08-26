"""Milestone 2 tests. All Kaggle calls are mocked -- no real network calls,
per this project's working rules (same discipline as AI_3D_FACTORY).
"""
import json
import os
from unittest.mock import patch

import pytest

from app.services import generation, jobs, kaggle_client


@pytest.fixture(autouse=True)
def _clear_jobs():
    jobs._JOBS.clear()
    yield
    jobs._JOBS.clear()


def test_submit_request_rejects_empty_text():
    with pytest.raises(generation.GenerationError):
        generation.submit_request("   ", "fake-token")


def test_submit_request_rejects_bad_token():
    with patch.object(kaggle_client, "resolve_username", side_effect=kaggle_client.KaggleAuthError("bad token")):
        with pytest.raises(generation.GenerationError) as exc_info:
            generation.submit_request("phone stand, 2 slots, 18 degrees", "bad-token")
        assert exc_info.value.status_code == 401


def test_submit_request_rejects_filtered_content():
    with pytest.raises(generation.GenerationError) as exc_info:
        generation.submit_request("a figurine of a faggot", "fake-token")
    assert exc_info.value.status_code == 422


def test_submit_request_rejects_over_rate_limit():
    jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel", ip="9.9.9.9")
    with pytest.raises(generation.GenerationError) as exc_info:
        generation.submit_request("phone stand, 2 slots, 18 degrees", "fake-token", ip="9.9.9.9")
    assert exc_info.value.status_code == 429


def test_submit_request_creative_without_tier_asks_for_one():
    with pytest.raises(generation.GenerationError) as exc_info:
        generation.submit_request("Batman themed phone holder", "fake-token")
    assert exc_info.value.status_code == 422


def test_submit_request_creative_pushes_correct_tier_kernel():
    with patch.object(kaggle_client, "resolve_username", return_value="testuser"), \
         patch.object(kaggle_client, "push_kernel", return_value="testuser/printforge-xyz") as mock_push:
        job_id = generation.submit_request("Batman themed phone holder", "fake-token", tier="fast")

    job = jobs.get_job(job_id)
    assert job["status"] == "running"
    assert job["classification"] == "creative"
    assert job["tier"] == "fast"
    assert job["spec"] is None
    mock_push.assert_called_once()
    # fast/refined tiers request a T4 explicitly (see kernel_builder.TIERS)
    assert mock_push.call_args.kwargs["accelerator"] == "NvidiaTeslaT4"


def test_submit_request_refined_tier_also_wired():
    with patch.object(kaggle_client, "resolve_username", return_value="testuser"), \
         patch.object(kaggle_client, "push_kernel", return_value="testuser/printforge-xyz"):
        job_id = generation.submit_request("Batman themed phone holder", "fake-token", tier="refined")

    assert jobs.get_job(job_id)["tier"] == "refined"


def test_submit_request_parametric_pushes_kernel_and_creates_job(tmp_path):
    with patch.object(kaggle_client, "resolve_username", return_value="testuser"), \
         patch.object(kaggle_client, "push_kernel", return_value="testuser/printforge-abc123") as mock_push:
        job_id = generation.submit_request(
            "phone stand, 2 slots, 18 degrees, 4mm walls, 3mm clearance, 70x12x150mm items",
            "fake-token",
        )

    assert job_id
    job = jobs.get_job(job_id)
    assert job["status"] == "running"
    assert job["classification"] == "parametric"
    assert job["kaggle_username"] == "testuser"
    assert job["kernel_id"] == "testuser/printforge-abc123"
    assert job["spec"]["model_type"] == "stand"
    mock_push.assert_called_once()


def test_check_job_not_found():
    with pytest.raises(generation.GenerationError) as exc_info:
        generation.check_job("does-not-exist")
    assert exc_info.value.status_code == 404


def test_check_job_still_running_does_not_recheck_before_interval():
    import time

    job_id = jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel")
    jobs.update_job(job_id, status="running", last_checked_at=time.time())

    with patch.object(kaggle_client, "get_status") as mock_status:
        view = generation.check_job(job_id)

    mock_status.assert_not_called()
    assert view["status"] == "running"


def test_check_job_retrieves_and_completes_on_success(tmp_path, monkeypatch):
    job_id = jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel")
    jobs.update_job(job_id, status="running", last_checked_at=0.0)

    dest_dir = os.path.join(str(tmp_path), job_id)
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "model.stl"), "w") as f:
        f.write("fake stl")
    with open(os.path.join(dest_dir, "report.json"), "w") as f:
        json.dump({"passed": True}, f)

    monkeypatch.setattr(generation, "GENERATED_ROOT", str(tmp_path))

    with patch.object(kaggle_client, "get_status", return_value="COMPLETE"), \
         patch.object(kaggle_client, "retrieve_output", return_value=[]):
        view = generation.check_job(job_id)

    assert view["status"] == "complete"
    assert view["result"]["stl_path"].endswith("model.stl")


def test_check_job_marks_quality_failed_when_report_says_so(tmp_path, monkeypatch):
    job_id = jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel")
    jobs.update_job(job_id, status="running", last_checked_at=0.0)

    dest_dir = os.path.join(str(tmp_path), job_id)
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "model.stl"), "w") as f:
        f.write("fake stl")
    with open(os.path.join(dest_dir, "report.json"), "w") as f:
        json.dump({"passed": False, "non_manifold_edges": 12}, f)

    monkeypatch.setattr(generation, "GENERATED_ROOT", str(tmp_path))

    with patch.object(kaggle_client, "get_status", return_value="COMPLETE"), \
         patch.object(kaggle_client, "retrieve_output", return_value=[]):
        view = generation.check_job(job_id)

    assert view["status"] == "quality_failed"


def test_check_job_marks_quality_failed_when_no_stl_but_report_exists(tmp_path, monkeypatch):
    """Creative-tier kernels write only report.json (no model.stl) when the
    raw generated mesh fails the pre-Blender sanity check -- a normal
    outcome for some prompts, not a pipeline error.
    """
    job_id = jobs.create_job("a vague prompt", "creative", "fast", "tok", "user", "user/kernel")
    jobs.update_job(job_id, status="running", last_checked_at=0.0)

    dest_dir = os.path.join(str(tmp_path), job_id)
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "report.json"), "w") as f:
        json.dump({"passed": False, "reasons": ["too small (largest dimension 0.1)"]}, f)

    monkeypatch.setattr(generation, "GENERATED_ROOT", str(tmp_path))

    with patch.object(kaggle_client, "get_status", return_value="COMPLETE"), \
         patch.object(kaggle_client, "retrieve_output", return_value=[]):
        view = generation.check_job(job_id)

    assert view["status"] == "quality_failed"
    assert "too small" in view["error"]


def test_check_job_marks_error_on_kaggle_failure_status():
    job_id = jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel")
    jobs.update_job(job_id, status="running", last_checked_at=0.0)

    with patch.object(kaggle_client, "get_status", return_value="KernelWorkerStatus.ERROR"):
        view = generation.check_job(job_id)

    assert view["status"] == "error"


def test_public_view_never_includes_token():
    job_id = jobs.create_job("prompt", "parametric", None, "super-secret-token", "user", "user/kernel")
    view = generation.check_job(job_id)
    assert "token" not in view
    assert "super-secret-token" not in json.dumps(view)
