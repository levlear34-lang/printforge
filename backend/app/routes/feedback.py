"""Milestone 6: feedback submission (public) + a minimal admin view.

Per the spec, the admin view doesn't need to be over-built for v1 -- a
single shared ADMIN_TOKEN secret (not a full admin-user/role system) is
enough. Compared with secrets.compare_digest to avoid a timing side
channel, same discipline as password/session comparisons elsewhere.
"""
import secrets

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app import db
from app.config import settings

router = APIRouter(prefix="/api")


class FeedbackRequest(BaseModel):
    rating: int | None = None
    message: str = ""


@router.post("/feedback")
def submit_feedback(payload: FeedbackRequest):
    if payload.rating is not None and not (1 <= payload.rating <= 5):
        raise HTTPException(status_code=422, detail="Rating must be between 1 and 5.")
    message = (payload.message or "").strip()
    if not message and payload.rating is None:
        raise HTTPException(status_code=422, detail="Please provide a rating or a message.")
    db.create_feedback(payload.rating, message or None)
    return {"status": "ok"}


def _check_admin_token(x_admin_token: str | None):
    if not settings.admin_token:
        raise HTTPException(status_code=503, detail="Admin view isn't configured on the server.")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, settings.admin_token):
        raise HTTPException(status_code=401, detail="Invalid admin token.")


@router.get("/admin/feedback")
def admin_list_feedback(x_admin_token: str | None = Header(default=None)):
    _check_admin_token(x_admin_token)
    return [
        {
            "id": row["id"],
            "rating": row["rating"],
            "message": row["message"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in db.list_feedback()
    ]
