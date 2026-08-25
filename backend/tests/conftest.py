"""Test-only environment setup, loaded by pytest before any test module.

Sets SESSION_SECRET/TOKEN_ENCRYPTION_KEY so app.config.settings (a
module-level singleton read once at import time) has valid values before
any test imports app code -- these are throwaway values for the test
process only, never used for anything real. DATABASE_URL is deliberately
left unset: no test hits a real database (see app/db.py's module
docstring), so every db.* call in tests must be mocked.
"""
import os

from cryptography.fernet import Fernet

os.environ.setdefault("SESSION_SECRET", "test-session-secret-not-for-production")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
