"""App configuration, read from environment variables only.

No secret ever has a hardcoded default here -- values that matter for
security (DB URL, session secret, token-encryption key) are required and the
app fails to start with a clear message if they're missing, once those
pieces exist (milestone 5). For milestone 1 everything is optional so the
hello-world app can boot with zero configuration.
"""
import os


class Settings:
    def __init__(self):
        self.environment = os.environ.get("ENVIRONMENT", "development")
        self.database_url = os.environ.get("DATABASE_URL")
        self.session_secret = os.environ.get("SESSION_SECRET")
        self.token_encryption_key = os.environ.get("TOKEN_ENCRYPTION_KEY")
        self.admin_token = os.environ.get("ADMIN_TOKEN")


settings = Settings()
