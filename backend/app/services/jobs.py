"""In-memory job store for anonymous create requests.

Deliberately in-memory (a plain dict guarded by a lock), not a database --
Milestone 5 adds Supabase/Neon for signed-in users' persistent history, but
Milestone 2 is anonymous-only, so there is nothing worth persisting past
this process's lifetime yet. Known, accepted limitation: a server restart
loses in-flight jobs, and this won't work across multiple server instances.
Documented in CLAUDE.md, not silently glossed over.

Each job's Kaggle token is held here, in memory, for the job's lifetime --
never written to disk or logged -- because Kaggle's push/status/output calls
are separate API round trips across an async job's lifetime and need the
token again on every poll. This is a deliberate reading of "never persisted
outside a single request's execution" as "this job's execution," not
"this one HTTP request" -- an async job spanning several minutes has to be
able to check on itself. See CLAUDE.md Progress Log for the full reasoning.
"""
import threading
import time
import uuid

_LOCK = threading.Lock()
_JOBS = {}

MIN_RECHECK_INTERVAL_SECONDS = 10
TERMINAL_STATUSES = ("complete", "error", "quality_failed")


def create_job(prompt, classification, tier, token, kaggle_username, kernel_id, ip=None):
    job_id = uuid.uuid4().hex[:12]
    with _LOCK:
        _JOBS[job_id] = {
            "id": job_id,
            "prompt": prompt,
            "classification": classification,
            "tier": tier,
            "token": token,
            "kaggle_username": kaggle_username,
            "kernel_id": kernel_id,
            "ip": ip,
            "status": "submitted",
            "created_at": time.time(),
            "last_checked_at": 0.0,
            "result": None,
            "error": None,
        }
    return job_id


def has_active_job(ip):
    """True if this IP already has a job that hasn't reached a terminal
    state -- used to enforce the "1 concurrent job per visitor" cap.
    """
    if not ip:
        return False
    with _LOCK:
        return any(
            job["ip"] == ip and job["status"] not in TERMINAL_STATUSES
            for job in _JOBS.values()
        )


def count_submissions_since(ip, since_timestamp):
    """Count this IP's job submissions at or after since_timestamp -- used
    to enforce the daily-submissions cap. _JOBS is never pruned within a
    process's lifetime, so this naturally includes the whole retained
    history; acceptable for an in-memory, single-process store (see the
    module docstring's known limitations).
    """
    if not ip:
        return 0
    with _LOCK:
        return sum(
            1 for job in _JOBS.values()
            if job["ip"] == ip and job["created_at"] >= since_timestamp
        )


def get_job(job_id):
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def update_job(job_id, **fields):
    with _LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(fields)


def should_recheck(job_id):
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return False
        return (time.time() - job["last_checked_at"]) >= MIN_RECHECK_INTERVAL_SECONDS


def public_view(job):
    """Strip the token out before this ever reaches an API response."""
    if job is None:
        return None
    view = dict(job)
    view.pop("token", None)
    return view
