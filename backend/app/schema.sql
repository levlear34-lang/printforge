-- PrintForge Postgres schema. Applied on startup by db.init_schema() if the
-- tables don't already exist -- no migration framework yet, appropriate for
-- this project's current size (see db.py's module docstring).

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    saved_kaggle_token_encrypted BYTEA,
    saved_kaggle_username TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Persisted job history for signed-in users only. Anonymous jobs stay in
-- the in-memory store (jobs.py) and are never written here, per the spec's
-- "anonymous use fully supported, no history saved" requirement.
CREATE TABLE IF NOT EXISTS job_history (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    prompt TEXT NOT NULL,
    classification TEXT NOT NULL,
    status TEXT NOT NULL,
    stl_path TEXT,
    preview_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS job_history_user_id_idx ON job_history (user_id);
