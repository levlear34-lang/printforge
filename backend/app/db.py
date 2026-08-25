"""Postgres access layer -- plain parameterized SQL via psycopg, no ORM.

Judgment call: raw SQL over an ORM (SQLAlchemy etc.) because the schema is
small (2 tables) and this matches the rest of the codebase's minimalism
(kaggle_client.py shells out to a CLI rather than wrapping it in a client
class hierarchy; there's no framework here beyond FastAPI itself). No
migration framework either -- init_schema() just runs schema.sql's
CREATE TABLE IF NOT EXISTS statements on startup, which is enough for a
project at this stage; revisit if the schema needs to evolve in
backward-incompatible ways later.

A new connection is opened per call rather than pooled -- acceptable at
this traffic scale (matches the "1 concurrent job per IP" ceiling from
rate_limit.py) and keeps this module simple; a connection pool
(psycopg_pool) is the natural next step if that ever becomes a bottleneck.

Every function here is exercised in tests only via mocking (patching this
module's functions), never against a real database in the automated
suite -- there is no Postgres available in CI/this dev environment. Real
verification happens manually against the developer's actual Supabase/Neon
instance once DATABASE_URL is configured, same discipline this project
already applies to Kaggle and Blender calls.
"""
import os

import psycopg

from app.config import settings

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


class UserExistsError(Exception):
    """Signup attempted with an email that's already registered."""


class DatabaseNotConfiguredError(RuntimeError):
    """DATABASE_URL isn't set -- account/dashboard features are disabled
    until it is, but the rest of the app keeps working. Has its own FastAPI
    exception handler (main.py) so this surfaces as a clean 503, not a
    generic unhandled-exception 500.
    """


def get_connection():
    if not settings.database_url:
        raise DatabaseNotConfiguredError(
            "Accounts/dashboard features aren't available yet -- the "
            "server's database isn't configured."
        )
    return psycopg.connect(settings.database_url)


def init_schema():
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        schema_sql = f.read()
    with get_connection() as conn:
        conn.execute(schema_sql)
        conn.commit()


def _row_to_user(row):
    if row is None:
        return None
    return {
        "id": row[0],
        "email": row[1],
        "password_hash": row[2],
        "saved_kaggle_token_encrypted": row[3],
        "saved_kaggle_username": row[4],
        "created_at": row[5],
    }


def create_user(email, password_hash):
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO users (email, password_hash)
                VALUES (%s, %s)
                RETURNING id, email, password_hash, saved_kaggle_token_encrypted,
                          saved_kaggle_username, created_at
                """,
                (email, password_hash),
            ).fetchone()
            conn.commit()
            return _row_to_user(row)
    except psycopg.errors.UniqueViolation as exc:
        raise UserExistsError(f"An account already exists for {email}.") from exc


def get_user_by_email(email):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, email, password_hash, saved_kaggle_token_encrypted,
                   saved_kaggle_username, created_at
            FROM users WHERE email = %s
            """,
            (email,),
        ).fetchone()
        return _row_to_user(row)


def get_user_by_id(user_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, email, password_hash, saved_kaggle_token_encrypted,
                   saved_kaggle_username, created_at
            FROM users WHERE id = %s
            """,
            (user_id,),
        ).fetchone()
        return _row_to_user(row)


def save_kaggle_token(user_id, encrypted_token, username):
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE users
            SET saved_kaggle_token_encrypted = %s, saved_kaggle_username = %s
            WHERE id = %s
            """,
            (encrypted_token, username, user_id),
        )
        conn.commit()


def delete_kaggle_token(user_id):
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE users
            SET saved_kaggle_token_encrypted = NULL, saved_kaggle_username = NULL
            WHERE id = %s
            """,
            (user_id,),
        )
        conn.commit()


def delete_user(user_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()


def _row_to_job(row):
    if row is None:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "prompt": row[2],
        "classification": row[3],
        "status": row[4],
        "stl_path": row[5],
        "preview_path": row[6],
        "created_at": row[7],
        "expires_at": row[8],
    }


def create_job_history(job_id, user_id, prompt, classification, status, expires_at):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO job_history (id, user_id, prompt, classification, status, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (job_id, user_id, prompt, classification, status, expires_at),
        )
        conn.commit()


def update_job_history(job_id, status, stl_path=None, preview_path=None):
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE job_history
            SET status = %s, stl_path = COALESCE(%s, stl_path),
                preview_path = COALESCE(%s, preview_path)
            WHERE id = %s
            """,
            (status, stl_path, preview_path, job_id),
        )
        conn.commit()


def list_job_history(user_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, prompt, classification, status, stl_path,
                   preview_path, created_at, expires_at
            FROM job_history WHERE user_id = %s ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [_row_to_job(row) for row in rows]


def get_job_history(job_id, user_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, prompt, classification, status, stl_path,
                   preview_path, created_at, expires_at
            FROM job_history WHERE id = %s AND user_id = %s
            """,
            (job_id, user_id),
        ).fetchone()
        return _row_to_job(row)


def delete_job_history(job_id, user_id):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM job_history WHERE id = %s AND user_id = %s",
            (job_id, user_id),
        )
        conn.commit()
