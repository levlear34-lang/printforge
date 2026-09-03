"""Password hashing + stateless signed-cookie sessions.

Sessions are a signed, timestamped token (itsdangerous) holding the user's
id -- not a server-side session store. Simpler and consistent with this
project's in-memory/stateless bias elsewhere; the tradeoff (can't
force-invalidate one session without rotating SESSION_SECRET for everyone)
is acceptable for a v1 with no admin/security-incident tooling yet.
"""
import re

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

SESSION_COOKIE_NAME = "objexa_session"
SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60  # 30 days

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def validate_email(email):
    if not email or not _EMAIL_PATTERN.match(email):
        raise AuthError("Please enter a valid email address.", status_code=422)


def validate_password(password):
    if not password or len(password) < 8:
        raise AuthError("Password must be at least 8 characters.", status_code=422)


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password, password_hash):
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _serializer():
    if not settings.session_secret:
        raise AuthError("SESSION_SECRET is not configured on the server.", status_code=500)
    return URLSafeTimedSerializer(settings.session_secret, salt="objexa-session")


def create_session_token(user_id):
    return _serializer().dumps({"user_id": user_id})


def read_session_token(token):
    """Returns the user_id, or None if the token is missing/invalid/expired."""
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id")
