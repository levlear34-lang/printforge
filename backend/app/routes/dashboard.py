"""Milestone 5: dashboard job history, saved-token management, account
deletion. All routes require a valid session (see routes/auth.py).
"""
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import db
from app.routes.auth import require_user_id
from app.services import accounts, auth

router = APIRouter(prefix="/api")


class SaveTokenRequest(BaseModel):
    kaggle_token: str


def _job_view(job):
    view = {
        "id": job["id"],
        "prompt": job["prompt"],
        "classification": job["classification"],
        "status": job["status"],
        "created_at": job["created_at"].isoformat(),
        "expires_at": job["expires_at"].isoformat(),
    }
    view["preview_url"] = f"/api/dashboard/jobs/{job['id']}/preview" if job["preview_path"] and os.path.exists(job["preview_path"]) else None
    view["download_url"] = f"/api/dashboard/jobs/{job['id']}/download" if job["stl_path"] and os.path.exists(job["stl_path"]) else None
    return view


@router.get("/dashboard/jobs")
def list_jobs(user_id: int = Depends(require_user_id)):
    return [_job_view(job) for job in accounts.list_dashboard_jobs(user_id)]


@router.delete("/dashboard/jobs/{job_id}")
def delete_job(job_id: str, user_id: int = Depends(require_user_id)):
    accounts.delete_dashboard_job(job_id, user_id)
    return {"status": "ok"}


@router.get("/dashboard/jobs/{job_id}/preview")
def job_preview(job_id: str, user_id: int = Depends(require_user_id)):
    job = db.get_job_history(job_id, user_id)
    if job is None or not job["preview_path"] or not os.path.exists(job["preview_path"]):
        raise HTTPException(status_code=404, detail="No preview available.")
    return FileResponse(job["preview_path"], media_type="image/png")


@router.get("/dashboard/jobs/{job_id}/download")
def job_download(job_id: str, user_id: int = Depends(require_user_id)):
    job = db.get_job_history(job_id, user_id)
    if job is None or not job["stl_path"] or not os.path.exists(job["stl_path"]):
        raise HTTPException(status_code=404, detail="This file has expired or doesn't exist.")
    return FileResponse(job["stl_path"], media_type="model/stl", filename=f"objexa-{job_id}.stl")


@router.post("/account/token")
def save_token(payload: SaveTokenRequest, user_id: int = Depends(require_user_id)):
    try:
        username = accounts.save_kaggle_token(user_id, payload.kaggle_token)
    except auth.AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"saved_kaggle_username": username}


@router.delete("/account/token")
def delete_token(user_id: int = Depends(require_user_id)):
    accounts.delete_kaggle_token(user_id)
    return {"status": "ok"}


@router.delete("/account")
def delete_account(user_id: int = Depends(require_user_id)):
    accounts.delete_account(user_id)
    return {"status": "ok"}
