"""Orchestrates a single create request: classify -> (design) -> submit ->
poll -> retrieve. No auth, no persistence -- Milestone 2 scope only.
"""
import json
import os
import tempfile
import time

from app.vendored.request_classifier import classify_request
from app.vendored.request_parser import parse_request
from app.vendored.design_agent import design_alternatives
from app.services import jobs, kaggle_client, kernel_builder

GENERATED_ROOT = os.path.join(tempfile.gettempdir(), "printforge_generated")


class GenerationError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def submit_request(text, token, tier=None):
    text = (text or "").strip()
    if not text:
        raise GenerationError("Please describe what you'd like to print.")

    classification = classify_request(text)

    if classification == "creative":
        if tier not in ("fast", "refined"):
            raise GenerationError(
                "This looks like a creative/themed request -- pick a quality "
                "tier (fast or refined) before submitting.",
                status_code=422,
            )
        raise GenerationError(
            "Creative (Shap-E / Stable Diffusion->TripoSR) generation isn't "
            "wired up yet -- only parametric requests (with explicit "
            "measurements) are supported so far. Try adding dimensions, a "
            "slot count, or an angle.",
            status_code=501,
        )

    try:
        username = kaggle_client.resolve_username(token)
    except kaggle_client.KaggleAuthError as exc:
        raise GenerationError(str(exc), status_code=401) from exc

    parsed = parse_request(text)
    spec = design_alternatives(parsed)[0]  # top-scored alternative, auto-selected

    job_id = jobs.create_job(
        prompt=text,
        classification=classification,
        tier=None,
        token=token,
        kaggle_username=username,
        kernel_id=None,
    )

    kernel_dir, kernel_id = kernel_builder.build_kernel("parametric", job_id, username, spec=spec)
    try:
        kernel_id = kaggle_client.push_kernel(token, kernel_dir)
    except kaggle_client.KaggleCliError as exc:
        jobs.update_job(job_id, status="error", error=str(exc))
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

    jobs.update_job(job_id, last_checked_at=time.time())

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
    dest_dir = os.path.join(GENERATED_ROOT, job_id)
    try:
        kaggle_client.retrieve_output(
            job["token"], job["kernel_id"], dest_dir,
            file_pattern=r"model\.stl$|preview\.png$|report\.json$",
        )
    except kaggle_client.KaggleCliError as exc:
        jobs.update_job(job_id, status="error", error=str(exc))
        return

    stl_path = os.path.join(dest_dir, "model.stl")
    preview_path = os.path.join(dest_dir, "preview.png")
    report_path = os.path.join(dest_dir, "report.json")

    if not os.path.exists(stl_path):
        jobs.update_job(
            job_id,
            status="error",
            error="Kaggle run finished but no model.stl was produced -- see the kernel log for details.",
        )
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
        return

    jobs.update_job(
        job_id,
        status="complete",
        result={"stl_path": stl_path, "preview_path": preview_path, "report_path": report_path},
    )
