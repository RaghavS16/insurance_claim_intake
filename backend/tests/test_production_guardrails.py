import os
os.environ.setdefault("ENVIRONMENT","test")
os.environ.setdefault("DEBUG","true")
os.environ.setdefault("SECRET_KEY","test-secret-key-at-least-32-characters-long")
os.environ.setdefault("DATABASE_URL","sqlite:///./test.db")

from src.utils.upload_limits import validate_declared_size
from src.utils.auth import create_access_token, verify_token

def test_upload_declared_size_rejects_oversize():
    try:
        validate_declared_size("1001", 1000)
    except ValueError:
        return
    assert False

def test_token_has_session_version():
    token = create_access_token({"sub": "user-1", "sv": 7})
    payload = verify_token(token)
    assert payload is not None
    assert payload["sv"] == 7


def test_production_requires_redis():
    from src.config import Settings
    import pytest
    cfg = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        ALLOW_INSECURE_TEST_AUTH=False,
        SECRET_KEY="x" * 48,
        DATABASE_URL="postgresql://postgres:password@db.example/claims",
        REDIS_URL=None,
        PUBLIC_APP_URL="https://app.example.com",
    )
    with pytest.raises(RuntimeError, match="REDIS_URL is required"):
        cfg.validate_startup()


def test_production_requires_https_public_app_url():
    from src.config import Settings
    import pytest
    cfg = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        ALLOW_INSECURE_TEST_AUTH=False,
        SECRET_KEY="x" * 48,
        DATABASE_URL="postgresql://postgres:password@db.example/claims",
        REDIS_URL="redis://127.0.0.1:6379/0",
        EMAIL_BACKEND="smtp",
        SMTP_HOST="smtp.example.com",
        SMTP_USERNAME="smtp-user",
        SMTP_PASSWORD="smtp-password",
        SMTP_FROM_EMAIL="claims@example.com",
        SMTP_USE_TLS=True,
        PUBLIC_APP_URL="http://app.example.com",
    )
    with pytest.raises(RuntimeError, match="PUBLIC_APP_URL must use HTTPS"):
        cfg.validate_startup()
