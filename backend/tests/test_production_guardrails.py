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
        SECRET_KEY="x" * 48,
        DATABASE_URL="postgresql://postgres:password@db.example/claims",
        REDIS_URL=None,
    )
    with pytest.raises(RuntimeError, match="REDIS_URL is required"):
        cfg.validate_startup()
