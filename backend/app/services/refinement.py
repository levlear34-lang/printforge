"""Orchestrates one "Advanced" prompt-refinement round: submit -> poll ->
retrieve. Reuses the exact same async job pattern as generation.py (jobs.py
for tracking, kernel_builder.py to assemble a per-job kernel copy,
kaggle_client.py to push/poll/retrieve) -- a refinement round is just a
different kind of job through the same pipeline, not a parallel system.

Two deliberate differences from generation.py's 3D-generation jobs:

1. Refinement jobs are never mirrored into Postgres via
   accounts.record_job_start/record_job_update. Unlike a finished STL, a
   refinement round isn't a deliverable the visitor would want in their
   dashboard history -- it's an ephemeral pre-processing step. Only the
   real generation job submitted after Approve (via generation.py,
   unchanged) gets recorded, exactly as it already does today.

2. Refinement submissions skip rate_limit.check()'s daily-submission cap
   (5/day) -- that cap is shared with 3D-generation submissions in the
   same jobs.py store, and the spec for this feature explicitly calls for
   *unlimited* refinement rounds. Applying the daily cap here would mean
   a handful of iteration rounds could silently exhaust a visitor's
   ability to submit their *actual* generation job the same day, which
   defeats the point. The concurrency check (jobs.has_active_job) still
   applies, since round N+1 always depends on round N's output anyway --
   that's not an artificial cap, just the natural sequencing of
   iteration.
"""
import json
import os
import tempfile

from app.services import content_filter, jobs, kaggle_client, kernel_builder

REFINEMENTS_ROOT = os.path.join(tempfile.gettempdir(), "objexa_refinements")


class RefinementError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def submit_refinement(idea, feedback=None, token=None, ip=None, user_id=None):
    idea = (idea or "").strip()
    feedback = (feedback or "").strip()
    if not idea:
        raise RefinementError("Describe what you'd like to print.")
    if not token:
        raise RefinementError("A Kaggle token is required.", status_code=422)

    try:
        content_filter.check_prompt(idea)
        if feedback:
            content_filter.check_prompt(feedback)
    except content_filter.ContentFilterError as exc:
        raise RefinementError(str(exc), status_code=422) from exc

    if jobs.has_active_job(ip):
        raise RefinementError(
            "You already have a job in progress. Please wait for it to "
            "finish before starting another refinement round.",
            status_code=429,
        )

    try:
        username = kaggle_client.resolve_username(token)
    except kaggle_client.KaggleAuthError as exc:
        raise RefinementError(str(exc), status_code=401) from exc
    except kaggle_client.KaggleCliError as exc:
        raise RefinementError(f"Couldn't reach Kaggle to verify this token: {exc}", status_code=502) from exc

    job_id = jobs.create_job(
        prompt=idea,
        classification="refine",
        tier="refine",
        token=token,
        kaggle_username=username,
        kernel_id=None,
        ip=ip,
        user_id=user_id,
    )

    kernel_dir, kernel_id = kernel_builder.build_kernel("refine", job_id, username, idea=idea, feedback=feedback)
    accelerator = kernel_builder.TIERS["refine"]["accelerator"]
    try:
        kernel_id = kaggle_client.push_kernel(token, kernel_dir, accelerator=accelerator)
    except kaggle_client.KaggleCliError as exc:
        jobs.update_job(job_id, status="error", error=str(exc))
        raise RefinementError(f"Failed to submit the refinement job to Kaggle: {exc}", status_code=502) from exc
    finally:
        kernel_builder.cleanup(kernel_dir)

    jobs.update_job(job_id, status="running", kernel_id=kernel_id)
    return job_id


def check_refinement(job_id):
    job = jobs.get_job(job_id)
    if job is None:
        raise RefinementError("Refinement job not found.", status_code=404)

    if job["status"] in ("complete", "error", "refine_failed"):
        return jobs.public_view(job)

    if not jobs.should_recheck(job_id):
        return jobs.public_view(job)

    jobs.record_check(job_id)

    try:
        status_text = kaggle_client.get_status(job["token"], job["kernel_id"])
    except kaggle_client.KaggleCliError as exc:
        jobs.update_job(job_id, status="error", error=str(exc))
        return jobs.public_view(jobs.get_job(job_id))

    if "COMPLETE" in status_text.upper():
        _retrieve_and_finalize(job_id, job)
    elif "ERROR" in status_text.upper() or "CANCEL" in status_text.upper():
        jobs.update_job(job_id, status="error", error=f"Kaggle run failed: {status_text}")
    else:
        jobs.update_job(job_id, status="running")

    return jobs.public_view(jobs.get_job(job_id))


def _retrieve_and_finalize(job_id, job):
    dest_dir = os.path.join(REFINEMENTS_ROOT, job_id)
    try:
        kaggle_client.retrieve_output(
            job["token"], job["kernel_id"], dest_dir,
            file_pattern=r"report\.json$",
        )
    except kaggle_client.KaggleCliError as exc:
        jobs.update_job(job_id, status="error", error=str(exc))
        return

    report_path = os.path.join(dest_dir, "report.json")
    if not os.path.exists(report_path):
        jobs.update_job(
            job_id,
            status="error",
            error="Kaggle run finished but no report was produced -- see the kernel log for details.",
        )
        return

    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    if not report.get("passed"):
        jobs.update_job(
            job_id,
            status="refine_failed",
            error=report.get("reason") or "The model didn't produce a usable prompt. Try again.",
        )
        return

    jobs.update_job(
        job_id,
        status="complete",
        result={"refined_prompt": report["refined_prompt"]},
    )
