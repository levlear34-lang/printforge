"""Milestone 2: anonymous create-flow endpoints.

No auth, no rate limiting, no content filter yet (those are Milestone 4/5).
"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services import generation, jobs

router = APIRouter(prefix="/api")


class CreateRequest(BaseModel):
    text: str
    kaggle_token: str
    tier: str | None = None


@router.post("/create")
def create(payload: CreateRequest):
    try:
        job_id = generation.submit_request(payload.text, payload.kaggle_token, payload.tier)
    except generation.GenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    try:
        view = generation.check_job(job_id)
    except generation.GenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    view.pop("kernel_id", None)
    return view


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
