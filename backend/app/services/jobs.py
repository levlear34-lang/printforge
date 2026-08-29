"""In-memory job store, shared by anonymous and signed-in create requests.

Deliberately in-memory (a plain dict guarded by a lock), not a database --
this remains the live/in-flight source of truth for polling regardless of
who submitted the job. As of Milestone 5, a job with a non-null user_id
also gets mirrored into Postgres (accounts.record_job_start/record_job_update)
for persistent dashboard history; anonymous jobs (user_id=None) are never
written to the database, per the spec's "anonymous use fully supported, no
history saved" requirement. Known, accepted limitation carried over from
Milestone 2: a server restart loses whatever's only in this in-memory
store (in-flight status/polling state), and this won't work across
multiple server instances. Documented in CLAUDE.md, not silently glossed
over.

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

# Exponential backoff on real Kaggle status checks: starts at 10s, grows
# 1.5x per consecutive check, caps at 60s. A real production 429 from
# Kaggle's API during status polling showed a flat 10s interval for a
# job's entire (often several-minutes-long) run is too aggressive --
# fine early on when a visitor is actively watching, wasteful and
# rate-limit-risky once a job has been running for a while. Frontend
# poll frequency (job.html's setTimeout loop) is irrelevant to this --
# it only controls how often the browser asks *our* backend for status;
# should_recheck() is what actually gates a real call to Kaggle,
# regardless of how often the frontend asks.
BASE_RECHECK_INTERVAL_SECONDS = 10
MAX_RECHECK_INTERVAL_SECONDS = 60
RECHECK_BACKOFF_MULTIPLIER = 1.5
TERMINAL_STATUSES = ("complete", "error", "quality_failed")


def create_job(prompt, classification, tier, token, kaggle_username, kernel_id, ip=None, user_id=None):
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
            "user_id": user_id,
            "status": "submitted",
            "created_at": time.time(),
            "last_checked_at": 0.0,
            "check_count": 0,
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
        interval = min(
            MAX_RECHECK_INTERVAL_SECONDS,
            BASE_RECHECK_INTERVAL_SECONDS * (RECHECK_BACKOFF_MULTIPLIER ** job["check_count"]),
        )
        return (time.time() - job["last_checked_at"]) >= interval


def record_check(job_id):
    """Call exactly once per real Kaggle status check (not per frontend
    poll) -- advances the backoff in should_recheck() above.
    """
    with _LOCK:
        if job_id in _JOBS:
            job = _JOBS[job_id]
            job["last_checked_at"] = time.time()
            job["check_count"] += 1


def public_view(job):
    """Strip the token out before this ever reaches an API response."""
    if job is None:
        return None
    view = dict(job)
    view.pop("token", None)
    return view
