"""Tests for Settings.validate_startup production SMTP requirements."""
import pytest
from src.config import Settings


def _valid_production_kwargs():
    return {
        "ENVIRONMENT": "production",
        "DEBUG": False,
        "SECRET_KEY": "s" * 48,
        "PUBLIC_APP_URL": "https://app.example.com",
        "DATABASE_URL": "postgresql://postgres:pass@localhost:5432/claims",
        "REDIS_URL": "redis://localhost:6379/0",
        "CLAMAV_HOST": "clamav",
        "S3_BUCKET": "claims-bucket",
        "AI_ALLOWED_MODELS": "openai/gpt-oss-20b:groq",
        "HF_TOKEN": "hf_test_token",
        "EMAIL_BACKEND": "smtp",
        "SMTP_HOST": "smtp.example.com",
        "SMTP_USERNAME": "smtp_user",
        "SMTP_PASSWORD": "smtp_password",
        "SMTP_FROM_EMAIL": "claims@example.com",
        "SMTP_USE_TLS": True,
        "SMTP_USE_SSL": False,
        "ALLOW_INSECURE_TEST_AUTH": False,
    }


def test_production_rejects_mailpit_backend():
    kwargs = _valid_production_kwargs()
    kwargs["EMAIL_BACKEND"] = "mailpit"
    cfg = Settings(**kwargs)
    with pytest.raises(RuntimeError, match="EMAIL_BACKEND must be 'smtp' in production/staging"):
        cfg.validate_startup()


def test_production_requires_smtp_host():
    kwargs = _valid_production_kwargs()
    kwargs["SMTP_HOST"] = None
    cfg = Settings(**kwargs)
    with pytest.raises(RuntimeError, match="SMTP_HOST is required in production/staging"):
        cfg.validate_startup()


def test_production_requires_smtp_username():
    kwargs = _valid_production_kwargs()
    kwargs["SMTP_USERNAME"] = ""
    cfg = Settings(**kwargs)
    with pytest.raises(RuntimeError, match="SMTP_USERNAME is required in production/staging"):
        cfg.validate_startup()


def test_production_requires_smtp_password():
    kwargs = _valid_production_kwargs()
    kwargs["SMTP_PASSWORD"] = None
    cfg = Settings(**kwargs)
    with pytest.raises(RuntimeError, match="SMTP_PASSWORD is required in production/staging"):
        cfg.validate_startup()


def test_production_requires_smtp_from_email():
    kwargs = _valid_production_kwargs()
    kwargs["SMTP_FROM_EMAIL"] = ""
    cfg = Settings(**kwargs)
    with pytest.raises(RuntimeError, match="SMTP_FROM_EMAIL is required in production/staging"):
        cfg.validate_startup()


def test_production_requires_tls_or_ssl():
    kwargs = _valid_production_kwargs()
    kwargs["SMTP_USE_TLS"] = False
    kwargs["SMTP_USE_SSL"] = False
    cfg = Settings(**kwargs)
    with pytest.raises(RuntimeError, match="One of SMTP_USE_TLS or SMTP_USE_SSL must be true in production/staging"):
        cfg.validate_startup()


def test_production_valid_smtp_passes_validation():
    kwargs = _valid_production_kwargs()
    cfg = Settings(**kwargs)
    # Should not raise
    cfg.validate_startup()
