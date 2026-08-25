import pytest

from app.services import jobs, rate_limit


@pytest.fixture(autouse=True)
def _clear_jobs():
    jobs._JOBS.clear()
    yield
    jobs._JOBS.clear()


def test_no_jobs_passes():
    rate_limit.check("1.2.3.4")


def test_blocks_concurrent_job_from_same_ip():
    jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel", ip="1.2.3.4")
    with pytest.raises(rate_limit.RateLimitError):
        rate_limit.check("1.2.3.4")


def test_different_ip_not_blocked_by_concurrent_job():
    jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel", ip="1.2.3.4")
    rate_limit.check("5.6.7.8")


def test_terminal_job_does_not_block_concurrency():
    job_id = jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel", ip="1.2.3.4")
    jobs.update_job(job_id, status="complete")
    rate_limit.check("1.2.3.4")


def test_blocks_after_daily_cap():
    for _ in range(rate_limit.MAX_DAILY_PER_IP):
        job_id = jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel", ip="1.2.3.4")
        jobs.update_job(job_id, status="complete")
    with pytest.raises(rate_limit.RateLimitError):
        rate_limit.check("1.2.3.4")


def test_old_submissions_do_not_count_toward_daily_cap():
    import time

    for _ in range(rate_limit.MAX_DAILY_PER_IP):
        job_id = jobs.create_job("prompt", "parametric", None, "tok", "user", "user/kernel", ip="1.2.3.4")
        jobs.update_job(job_id, status="complete", created_at=time.time() - rate_limit.ONE_DAY_SECONDS - 10)
    rate_limit.check("1.2.3.4")
