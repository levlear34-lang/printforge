"""Orchestrates a single create request: classify -> (design) -> submit ->
poll -> retrieve. Anonymous jobs are in-memory only; signed-in (user_id
set) jobs also get mirrored into Postgres for dashboard history -- see
accounts.record_job_start/record_job_update.
"""
import json
import os
import tempfile

from app.vendored.request_classifier import classify_request
from app.vendored.request_parser import parse_request
from app.vendored.design_agent import design_alternatives
from app.services import accounts, content_filter, jobs, kaggle_client, kernel_builder, rate_limit

GENERATED_ROOT = os.path.join(tempfile.gettempdir(), "objexa_generated")


class GenerationError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def submit_request(text, token=None, tier=None, ip=None, user_id=None):
    text = (text or "").strip()
    if not text:
        raise GenerationError("Please describe what you'd like to print.")

    if not token and user_id is not None:
        token = accounts.get_saved_token_plaintext(user_id)
    if not token:
        raise GenerationError("A Kaggle token is required.", status_code=422)

    try:
        content_filter.check_prompt(text)
    except content_filter.ContentFilterError as exc:
        raise GenerationError(str(exc), status_code=422) from exc

    try:
        rate_limit.check(ip)
    except rate_limit.RateLimitError as exc:
        raise GenerationError(str(exc), status_code=429) from exc

    classification = classify_request(text)

    if classification == "creative" and tier not in ("fast", "refined"):
        raise GenerationError(
            "This looks like a creative/themed request -- pick a quality "
            "tier (fast or refined) before submitting.",
            status_code=422,
        )

    try:
        username = kaggle_client.resolve_username(token)
    except kaggle_client.KaggleAuthError as exc:
        raise GenerationError(str(exc), status_code=401) from exc
    except kaggle_client.KaggleCliError as exc:
        raise GenerationError(f"Couldn't reach Kaggle to verify this token: {exc}", status_code=502) from exc

    if classification == "creative":
        tier_key = tier
        spec = None
        kernel_kwargs = {"prompt": text}
    else:
        tier_key = "parametric"
        parsed = parse_request(text)
        spec = design_alternatives(parsed)[0]  # top-scored alternative, auto-selected
        kernel_kwargs = {"spec": spec}

    job_id = jobs.create_job(
        prompt=text,
        classification=classification,
        tier=tier if classification == "creative" else None,
        token=token,
        kaggle_username=username,
        kernel_id=None,
        ip=ip,
        user_id=user_id,
    )
    if user_id is not None:
        accounts.record_job_start(job_id, user_id, text, classification)

    kernel_dir, kernel_id = kernel_builder.build_kernel(tier_key, job_id, username, **kernel_kwargs)
    accelerator = kernel_builder.TIERS[tier_key]["accelerator"]
    try:
        kernel_id = kaggle_client.push_kernel(token, kernel_dir, accelerator=accelerator)
    except kaggle_client.KaggleCliError as exc:
        jobs.update_job(job_id, status="error", error=str(exc))
        if user_id is not None:
            accounts.record_job_update(job_id, status="error")
        raise GenerationError(f"Failed to submit the job to Kaggle: {exc}", status_code=502) from exc
    finally:
        kernel_builder.cleanup(kernel_dir)

    jobs.update_job(job_id, status="running", kernel_id=kernel_id, spec=spec)
    return job_id


def check_job(job_id):
    job = jobs.get_job(job_id)
    if job is None:
        raise GenerationError("Job not found.", status_code=404)

    if job["status"] in ("complete", "error", "quality_failed"):
        return jobs.public_view(job)

    if not jobs.should_recheck(job_id):
        return jobs.public_view(job)

    jobs.record_check(job_id)

    try:
        status_text = kaggle_client.get_status(job["token"], job["kernel_id"])
    except kaggle_client.KaggleCliError as exc:
        jobs.update_job(job_id, status="error", error=str(exc))
        if job["user_id"] is not None:
            accounts.record_job_update(job_id, status="error")
        return jobs.public_view(jobs.get_job(job_id))

    if "COMPLETE" in status_text.upper():
        _retrieve_and_finalize(job_id, job)
    elif "ERROR" in status_text.upper() or "CANCEL" in status_text.upper():
        jobs.update_job(job_id, status="error", error=f"Kaggle run failed: {status_text}")
        if job["user_id"] is not None:
            accounts.record_job_update(job_id, status="error")
    else:
        jobs.update_job(job_id, status="running")

    return jobs.public_view(jobs.get_job(job_id))


def _retrieve_and_finalize(job_id, job):
    user_id = job["user_id"]
    dest_dir = os.path.join(GENERATED_ROOT, job_id)
    try:
        kaggle_client.retrieve_output(
            job["token"], job["kernel_id"], dest_dir,
            file_pattern=r"model\.stl$|preview\.png$|report\.json$",
        )
    except kaggle_client.KaggleCliError as exc:
        jobs.update_job(job_id, status="error", error=str(exc))
        if user_id is not None:
            accounts.record_job_update(job_id, status="error")
        return

    stl_path = os.path.join(dest_dir, "model.stl")
    preview_path = os.path.join(dest_dir, "preview.png")
    report_path = os.path.join(dest_dir, "report.json")

    if not os.path.exists(stl_path):
        # Creative-tier kernels write only report.json (no model.stl) when
        # the raw generated mesh fails the pre-Blender sanity check (too
        # little geometry, degenerate volume, wildly mis-scaled) -- a
        # normal, expected outcome for some prompts, not a pipeline error.
        if os.path.exists(report_path):
            with open(report_path, encoding="utf-8") as f:
                report = json.load(f)
            reasons = ", ".join(report.get("reasons", [])) or "failed the raw mesh quality check"
            jobs.update_job(
                job_id,
                status="quality_failed",
                error=f"The generated mesh {reasons}. Try a different or more specific prompt.",
            )
            if user_id is not None:
                accounts.record_job_update(job_id, status="quality_failed")
            return

        jobs.update_job(
            job_id,
            status="error",
            error="Kaggle run finished but no model.stl was produced -- see the kernel log for details.",
        )
        if user_id is not None:
            accounts.record_job_update(job_id, status="error")
        return

    passed = True
    if os.path.exists(report_path):
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
        passed = bool(report.get("passed"))

    if not passed:
        jobs.update_job(
            job_id,
            status="quality_failed",
            error="The generated model failed validation (non-manifold geometry or out-of-envelope size). Try adjusting the request.",
            result={"stl_path": stl_path, "preview_path": preview_path, "report_path": report_path},
        )
        if user_id is not None:
            accounts.record_job_update(job_id, status="quality_failed", stl_path=stl_path, preview_path=preview_path)
        return

    jobs.update_job(
        job_id,
        status="complete",
        result={"stl_path": stl_path, "preview_path": preview_path, "report_path": report_path},
    )
    if user_id is not None:
        accounts.record_job_update(job_id, status="complete", stl_path=stl_path, preview_path=preview_path)
