"""Milestone 2/3/4: anonymous create-flow endpoints + the pages that use them.

No auth yet (Milestone 5). Content filter and per-IP rate limiting are
enforced in generation.submit_request (Milestone 4).
"""
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services import generation, jobs

router = APIRouter(prefix="/api")


class CreateRequest(BaseModel):
    text: str
    kaggle_token: str
    tier: str | None = None


def _client_ip(request: Request) -> str:
    """Render (and most PaaS) terminate TLS at a reverse proxy, so the real
    visitor IP arrives via X-Forwarded-For, not request.client.host (that's
    the proxy's internal address). Falls back to request.client.host for
    local dev, where there's no proxy in front.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/create")
def create(payload: CreateRequest, request: Request):
    try:
        job_id = generation.submit_request(
            payload.text, payload.kaggle_token, payload.tier, ip=_client_ip(request),
        )
    except generation.GenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    """Never exposes local server file paths -- only status + relative URLs
    the frontend can fetch, since job["result"] otherwise holds this
    machine's absolute filesystem paths.
    """
    try:
        view = generation.check_job(job_id)
    except generation.GenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    view.pop("kernel_id", None)

    result = view.pop("result", None)
    if result:
        view["preview_url"] = f"/api/jobs/{job_id}/preview" if os.path.exists(result.get("preview_path", "")) else None
        view["download_url"] = f"/api/jobs/{job_id}/download" if os.path.exists(result.get("stl_path", "")) else None
    else:
        view["preview_url"] = None
        view["download_url"] = None

    return view


@router.get("/jobs/{job_id}/preview")
def preview(job_id: str):
    job = jobs.get_job(job_id)
    if job is None or not job.get("result"):
        raise HTTPException(status_code=404, detail="No preview available for this job.")
    preview_path = job["result"].get("preview_path")
    if not preview_path or not os.path.exists(preview_path):
        raise HTTPException(status_code=410, detail="This preview has expired.")
    return FileResponse(preview_path, media_type="image/png")


@router.get("/jobs/{job_id}/download")
def download(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["status"] != "complete" or not job.get("result"):
        raise HTTPException(status_code=409, detail="This job isn't ready to download yet.")
    stl_path = job["result"]["stl_path"]
    if not os.path.exists(stl_path):
        raise HTTPException(status_code=410, detail="This file has expired.")
    return FileResponse(stl_path, media_type="model/stl", filename=f"printforge-{job_id}.stl")
