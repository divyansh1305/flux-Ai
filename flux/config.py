"""Configuration loaded from environment variables.

Production refuses to start without a real SECRET_KEY, so sessions can't be
forged and don't reset on every restart.
"""
import os
from datetime import timedelta


class ConfigError(RuntimeError):
    pass


def _bool(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    def __init__(self, overrides=None):
        overrides = overrides or {}
        env = overrides.get("ENV") or os.environ.get("FLUX_ENV", "development")
        self.ENV = env
        self.TESTING = overrides.get("TESTING", False)
        self.IS_PRODUCTION = env == "production"

        secret = overrides.get("SECRET_KEY") or os.environ.get("SECRET_KEY")
        if not secret:
            if self.IS_PRODUCTION:
                raise ConfigError("SECRET_KEY must be set in production.")
            secret = "dev-only-insecure-key-change-me"
        if self.IS_PRODUCTION and len(secret) < 32:
            raise ConfigError("SECRET_KEY must be at least 32 characters in production.")
        self.SECRET_KEY = secret

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.DATABASE = overrides.get("DATABASE") or os.environ.get(
            "DATABASE_PATH", os.path.join(base_dir, "instance", "flux.db")
        )

        # Session cookies
        self.SESSION_COOKIE_HTTPONLY = True
        self.SESSION_COOKIE_SAMESITE = "Lax"
        self.SESSION_COOKIE_SECURE = self.IS_PRODUCTION or _bool("FORCE_SECURE_COOKIES")
        self.SESSION_COOKIE_NAME = "flux_session"
        self.PERMANENT_SESSION_LIFETIME = timedelta(days=7)
        self.MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MB uploads max

        # Email (OTP login)
        self.MAIL_SENDER = os.environ.get("EMAIL_SENDER", "")
        self.MAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "").replace(" ", "")
        self.MAIL_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        self.MAIL_PORT = int(os.environ.get("SMTP_PORT", "465"))

        # Google Sign-In (optional)
        self.GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

        # Gemini (optional - app works without it)
        self.GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
        self.GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

        # Zerodha Kite Publisher (optional). Without it, investing runs in clearly-labelled practice mode.
        self.KITE_API_KEY = os.environ.get("KITE_API_KEY", "")

        # OTP policy
        self.OTP_TTL_SECONDS = 600
        self.OTP_MAX_ATTEMPTS = 5
        self.OTP_RESEND_COOLDOWN = 60

        for k, v in overrides.items():
            setattr(self, k, v)

    @property
    def mail_enabled(self):
        return bool(self.MAIL_SENDER and self.MAIL_PASSWORD)

    def as_flask_dict(self):
        return {k: getattr(self, k) for k in dir(self) if k.isupper()}
