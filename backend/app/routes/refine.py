"""Milestone 8: the opt-in "Advanced" prompt-refinement flow. Each round is
its own async job through refinement.py, mirroring create.py's shape almost
exactly -- same client-IP resolution, same saved-token fallback for
signed-in visitors, same never-expose-server-paths discipline on the status
endpoint (there's nothing file-based to leak here, but the response shape
stays consistent with /api/jobs/{id} regardless).
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.routes.auth import get_current_user_id
from app.routes.create import _client_ip
from app.services import accounts, refinement

router = APIRouter(prefix="/api")


class RefineRequest(BaseModel):
    idea: str
    feedback: str | None = None
    kaggle_token: str | None = None


@router.post("/refine")
def refine(payload: RefineRequest, request: Request):
    user_id = get_current_user_id(request)
    token = payload.kaggle_token
    if not token and user_id is not None:
        token = accounts.get_saved_token_plaintext(user_id)

    try:
        job_id = refinement.submit_refinement(
            payload.idea,
            payload.feedback,
            token,
            ip=_client_ip(request),
            user_id=user_id,
        )
    except refinement.RefinementError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"job_id": job_id}


@router.get("/refine/{job_id}")
def refine_status(job_id: str):
    try:
        view = refinement.check_refinement(job_id)
    except refinement.RefinementError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    view.pop("kernel_id", None)

    result = view.pop("result", None)
    view["refined_prompt"] = result["refined_prompt"] if result else None
    return view
