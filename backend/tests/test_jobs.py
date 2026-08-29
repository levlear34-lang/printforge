"""Tests for jobs.py's exponential backoff on real Kaggle status checks --
added after a real production 429 from Kaggle's API during job-status
polling (a flat 10s interval for a job's whole multi-minute run was too
aggressive). See jobs.py's module-level comment for the full story.
"""
import time

import pytest

from app.services import jobs


@pytest.fixture(autouse=True)
def _clear_jobs():
    jobs._JOBS.clear()
    yield
    jobs._JOBS.clear()


def test_should_recheck_true_for_a_brand_new_job():
    job_id = jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel")
    assert jobs.should_recheck(job_id) is True


def test_record_check_resets_the_clock_and_blocks_immediate_recheck():
    job_id = jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel")
    jobs.record_check(job_id)
    assert jobs.should_recheck(job_id) is False


def test_record_check_increments_check_count():
    job_id = jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel")
    jobs.record_check(job_id)
    jobs.record_check(job_id)
    assert jobs.get_job(job_id)["check_count"] == 2


def test_backoff_interval_grows_with_check_count():
    """A job checked many times must wait longer before its next recheck
    than a job checked only once -- proves the interval actually grows
    instead of staying flat at BASE_RECHECK_INTERVAL_SECONDS forever.
    """
    job_id = jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel")
    jobs.update_job(job_id, check_count=5)
    # Just past the ORIGINAL base interval -- nowhere near what 5 rounds
    # of 1.5x backoff should now require.
    jobs.update_job(job_id, last_checked_at=time.time() - jobs.BASE_RECHECK_INTERVAL_SECONDS - 0.5)
    assert jobs.should_recheck(job_id) is False


def test_backoff_interval_caps_at_max():
    job_id = jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel")
    jobs.update_job(
        job_id,
        check_count=100,  # would blow past MAX without the cap
        last_checked_at=time.time() - jobs.MAX_RECHECK_INTERVAL_SECONDS - 1,
    )
    assert jobs.should_recheck(job_id) is True


def test_should_recheck_false_for_unknown_job():
    assert jobs.should_recheck("does-not-exist") is False
