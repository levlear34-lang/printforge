"""Milestone 8 step 2 tests. All Kaggle calls are mocked -- no real network
calls, same discipline as test_generation.py.
"""
import json
import os
from unittest.mock import patch

import pytest

from app.services import jobs, kaggle_client, refinement


@pytest.fixture(autouse=True)
def _clear_jobs():
    jobs._JOBS.clear()
    yield
    jobs._JOBS.clear()


def test_submit_refinement_rejects_empty_idea():
    with pytest.raises(refinement.RefinementError):
        refinement.submit_refinement("   ", token="fake-token")


def test_submit_refinement_rejects_missing_token():
    with pytest.raises(refinement.RefinementError) as exc_info:
        refinement.submit_refinement("a batman phone holder", token=None)
    assert exc_info.value.status_code == 422


def test_submit_refinement_rejects_filtered_idea():
    with pytest.raises(refinement.RefinementError) as exc_info:
        refinement.submit_refinement("a figurine of a faggot", token="fake-token")
    assert exc_info.value.status_code == 422


def test_submit_refinement_rejects_filtered_feedback():
    with pytest.raises(refinement.RefinementError) as exc_info:
        refinement.submit_refinement("a phone holder", feedback="make it a faggot", token="fake-token")
    assert exc_info.value.status_code == 422


def test_submit_refinement_rejects_bad_token():
    with patch.object(kaggle_client, "resolve_username", side_effect=kaggle_client.KaggleAuthError("bad")):
        with pytest.raises(refinement.RefinementError) as exc_info:
            refinement.submit_refinement("a batman phone holder", token="bad-token")
        assert exc_info.value.status_code == 401


def test_submit_refinement_does_not_apply_daily_cap():
    """Unlike generation.submit_request, refinement rounds must not be
    blocked by rate_limit's 5/day cap -- the spec requires unlimited
    iteration rounds. Five prior *completed* (non-active) jobs on the same
    IP would trip generation's rate_limit.check() but must not trip this.
    """
    for _ in range(5):
        job_id = jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel", ip="9.9.9.9")
        jobs.update_job(job_id, status="complete")

    with patch.object(kaggle_client, "resolve_username", return_value="testuser"), \
         patch.object(kaggle_client, "push_kernel", return_value="testuser/objexa-xyz"):
        job_id = refinement.submit_refinement("a batman phone holder", token="fake-token", ip="9.9.9.9")

    assert jobs.get_job(job_id)["status"] == "running"


def test_submit_refinement_still_blocks_concurrent_active_job():
    jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel", ip="9.9.9.9")
    with pytest.raises(refinement.RefinementError) as exc_info:
        refinement.submit_refinement("a batman phone holder", token="fake-token", ip="9.9.9.9")
    assert exc_info.value.status_code == 429


def test_submit_refinement_pushes_cpu_only_kernel():
    with patch.object(kaggle_client, "resolve_username", return_value="testuser"), \
         patch.object(kaggle_client, "push_kernel", return_value="testuser/objexa-xyz") as mock_push:
        job_id = refinement.submit_refinement("a batman phone holder", token="fake-token")

    job = jobs.get_job(job_id)
    assert job["status"] == "running"
    assert job["tier"] == "refine"
    assert job["classification"] == "refine"
    mock_push.assert_called_once()
    assert mock_push.call_args.kwargs["accelerator"] is None


def test_check_refinement_not_found():
    with pytest.raises(refinement.RefinementError) as exc_info:
        refinement.check_refinement("does-not-exist")
    assert exc_info.value.status_code == 404


def test_check_refinement_completes_and_extracts_prompt(tmp_path, monkeypatch):
    job_id = jobs.create_job("a batman phone holder", "refine", "refine", "tok", "user", "user/kernel")
    jobs.update_job(job_id, status="running", last_checked_at=0.0)

    dest_dir = os.path.join(str(tmp_path), job_id)
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "report.json"), "w") as f:
        json.dump({"passed": True, "refined_prompt": "a detailed batman phone holder description"}, f)

    monkeypatch.setattr(refinement, "REFINEMENTS_ROOT", str(tmp_path))

    with patch.object(kaggle_client, "get_status", return_value="COMPLETE"), \
         patch.object(kaggle_client, "retrieve_output", return_value=[]):
        view = refinement.check_refinement(job_id)

    assert view["status"] == "complete"
    assert view["result"]["refined_prompt"] == "a detailed batman phone holder description"


def test_check_refinement_marks_refine_failed_when_report_says_so(tmp_path, monkeypatch):
    job_id = jobs.create_job("a vague idea", "refine", "refine", "tok", "user", "user/kernel")
    jobs.update_job(job_id, status="running", last_checked_at=0.0)

    dest_dir = os.path.join(str(tmp_path), job_id)
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "report.json"), "w") as f:
        json.dump({"passed": False, "reason": "Model output too short/empty (3 chars)."}, f)

    monkeypatch.setattr(refinement, "REFINEMENTS_ROOT", str(tmp_path))

    with patch.object(kaggle_client, "get_status", return_value="COMPLETE"), \
         patch.object(kaggle_client, "retrieve_output", return_value=[]):
        view = refinement.check_refinement(job_id)

    assert view["status"] == "refine_failed"
    assert "too short" in view["error"]


def test_check_refinement_marks_error_on_kaggle_failure_status():
    job_id = jobs.create_job("an idea", "refine", "refine", "tok", "user", "user/kernel")
    jobs.update_job(job_id, status="running", last_checked_at=0.0)

    with patch.object(kaggle_client, "get_status", return_value="KernelWorkerStatus.ERROR"):
        view = refinement.check_refinement(job_id)

    assert view["status"] == "error"


def test_public_view_never_includes_token():
    job_id = jobs.create_job("an idea", "refine", "refine", "super-secret-token", "user", "user/kernel")
    view = refinement.check_refinement(job_id)
    assert "token" not in view
    assert "super-secret-token" not in json.dumps(view)
