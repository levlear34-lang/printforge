"""Per-IP abuse prevention for the free-tier web service itself.

Deliberately independent of whose Kaggle token is used for generation --
this protects the (free-tier) backend from being hammered with job
submissions, not Kaggle's quota (that's the visitor's own problem, on
their own account). Judgment call on the actual numbers: 1 concurrent job
and 5 submissions/day per IP. Generous enough that a real visitor
experimenting with a couple of prompts a day never notices it, tight
enough that no single visitor can flood the job store. IP-based (not
session/account-based) because Milestone 4 still has no auth -- Milestone 5
can layer an account-based limit on top once accounts exist, without
removing this one (a logged-in abuser is still one visitor).
"""
import time

from app.services import jobs

MAX_CONCURRENT_PER_IP = 1
MAX_DAILY_PER_IP = 5
ONE_DAY_SECONDS = 24 * 60 * 60


class RateLimitError(Exception):
    def __init__(self, message):
        super().__init__(message)


def check(ip):
    if jobs.has_active_job(ip):
        raise RateLimitError(
            "You already have a job in progress. Please wait for it to "
            "finish before submitting another."
        )
    recent = jobs.count_submissions_since(ip, time.time() - ONE_DAY_SECONDS)
    if recent >= MAX_DAILY_PER_IP:
        raise RateLimitError(
            f"You've reached the daily limit of {MAX_DAILY_PER_IP} requests. "
            "Please try again tomorrow."
        )
