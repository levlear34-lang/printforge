"""Account business logic: signup/login, saved-token management, dashboard
history. Thin composition over db.py + auth.py + token_crypto.py so routes
stay simple and this logic stays testable via mocking db.py (no real
Postgres in the automated test suite -- see db.py's module docstring).
"""
import datetime

from app import db
from app.services import auth, kaggle_client, token_crypto

JOB_RETENTION_DAYS = 7


def signup(email, password):
    auth.validate_email(email)
    auth.validate_password(password)
    password_hash = auth.hash_password(password)
    try:
        user = db.create_user(email, password_hash)
    except db.UserExistsError as exc:
        raise auth.AuthError(str(exc), status_code=409) from exc
    return user


def login(email, password):
    user = db.get_user_by_email(email)
    if user is None or not auth.verify_password(password, user["password_hash"]):
        raise auth.AuthError("Incorrect email or password.", status_code=401)
    return user


def public_user_view(user):
    """Never include password_hash or the encrypted token blob in an API
    response -- only whether a token is saved, and its username, so the
    frontend can show "token saved (as <username>)" without ever seeing
    the encrypted bytes let alone the plaintext.
    """
    return {
        "id": user["id"],
        "email": user["email"],
        "has_saved_token": user["saved_kaggle_token_encrypted"] is not None,
        "saved_kaggle_username": user["saved_kaggle_username"],
    }


def save_kaggle_token(user_id, token):
    try:
        username = kaggle_client.resolve_username(token)
    except kaggle_client.KaggleAuthError as exc:
        raise auth.AuthError(str(exc), status_code=401) from exc
    except kaggle_client.KaggleCliError as exc:
        raise auth.AuthError(f"Couldn't reach Kaggle to verify this token: {exc}", status_code=502) from exc
    encrypted = token_crypto.encrypt_token(token)
    db.save_kaggle_token(user_id, encrypted, username)
    return username


def delete_kaggle_token(user_id):
    db.delete_kaggle_token(user_id)


def get_saved_token_plaintext(user_id):
    """Decrypts the saved token for one-time use submitting a job -- never
    returned from an API endpoint, only used server-side.
    """
    user = db.get_user_by_id(user_id)
    if user is None or user["saved_kaggle_token_encrypted"] is None:
        return None
    return token_crypto.decrypt_token(user["saved_kaggle_token_encrypted"])


def delete_account(user_id):
    db.delete_user(user_id)  # job_history rows cascade via FK ON DELETE CASCADE


def record_job_start(job_id, user_id, prompt, classification):
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=JOB_RETENTION_DAYS)
    db.create_job_history(job_id, user_id, prompt, classification, status="running", expires_at=expires_at)


def record_job_update(job_id, status, stl_path=None, preview_path=None):
    db.update_job_history(job_id, status, stl_path=stl_path, preview_path=preview_path)


def list_dashboard_jobs(user_id):
    return db.list_job_history(user_id)


def delete_dashboard_job(job_id, user_id):
    db.delete_job_history(job_id, user_id)
