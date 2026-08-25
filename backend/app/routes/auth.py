"""Milestone 5: signup/login/logout, session cookie management.

Session is a signed, stateless cookie (see services/auth.py) -- no
server-side session table. httponly + samesite=lax so it's not readable
from JS and isn't sent on cross-site requests, secure=True in production
(disabled only for local http:// dev, see config.settings.environment).
"""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app import db
from app.config import settings
from app.services import accounts, auth

router = APIRouter(prefix="/api")


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


def _set_session_cookie(response: Response, user_id: int):
    response.set_cookie(
        auth.SESSION_COOKIE_NAME,
        auth.create_session_token(user_id),
        max_age=auth.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=(settings.environment == "production"),
    )


def get_current_user_id(request: Request):
    return auth.read_session_token(request.cookies.get(auth.SESSION_COOKIE_NAME))


def require_user_id(request: Request) -> int:
    user_id = get_current_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Please log in.")
    return user_id


@router.post("/signup")
def signup(payload: SignupRequest, response: Response):
    try:
        user = accounts.signup(payload.email, payload.password)
    except auth.AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    _set_session_cookie(response, user["id"])
    return accounts.public_user_view(user)


@router.post("/login")
def login(payload: LoginRequest, response: Response):
    try:
        user = accounts.login(payload.email, payload.password)
    except auth.AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    _set_session_cookie(response, user["id"])
    return accounts.public_user_view(user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(auth.SESSION_COOKIE_NAME)
    return {"status": "ok"}


@router.get("/me")
def me(request: Request):
    user_id = get_current_user_id(request)
    if user_id is None:
        return {"logged_in": False}
    user = db.get_user_by_id(user_id)
    if user is None:
        return {"logged_in": False}
    return {"logged_in": True, **accounts.public_user_view(user)}
