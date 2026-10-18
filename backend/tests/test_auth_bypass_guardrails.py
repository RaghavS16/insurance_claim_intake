"""Tests proving that test auth bypasses cannot be reached unless both
ENVIRONMENT == 'test' AND ALLOW_INSECURE_TEST_AUTH is explicitly True,
and that Settings rejects ALLOW_INSECURE_TEST_AUTH in non-test environments.
"""
import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock
from src.config import Settings, settings
from src.api.deps import get_current_user


def test_validator_rejects_insecure_flag_in_production():
    """Settings model_validator must raise if ALLOW_INSECURE_TEST_AUTH is True when ENVIRONMENT != 'test'."""
    with pytest.raises(ValueError, match="ALLOW_INSECURE_TEST_AUTH is only permitted when ENVIRONMENT == 'test'"):
        Settings(
            ENVIRONMENT="production",
            ALLOW_INSECURE_TEST_AUTH=True,
            DEBUG=False,
            SECRET_KEY="x" * 48,
            PUBLIC_APP_URL="https://app.example.com",
            DATABASE_URL="postgresql://postgres:pass@localhost:5432/claims",
            REDIS_URL="redis://localhost:6379/0",
        )


def test_validator_rejects_insecure_flag_in_development():
    """Settings model_validator must also raise if ALLOW_INSECURE_TEST_AUTH is True in development."""
    with pytest.raises(ValueError, match="ALLOW_INSECURE_TEST_AUTH is only permitted when ENVIRONMENT == 'test'"):
        Settings(
            ENVIRONMENT="development",
            ALLOW_INSECURE_TEST_AUTH=True,
            DEBUG=True,
            SECRET_KEY="dev-secret-key-change-in-production",
        )


def test_flag_unset_in_test_env_rejects_unauthenticated_request(monkeypatch):
    """When ALLOW_INSECURE_TEST_AUTH is False in test env, requests without token return 401."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_TEST_AUTH", False)

    mock_request = MagicMock()
    mock_request.headers = {}
    mock_db = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(request=mock_request, credentials=None, db=mock_db)
    assert exc_info.value.status_code == 401
    assert "missing bearer token" in exc_info.value.detail.lower()


def test_flag_unset_in_test_env_x_user_id_does_not_authenticate(monkeypatch):
    """When ALLOW_INSECURE_TEST_AUTH is False in test env, X-User-ID header does not authenticate."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_TEST_AUTH", False)

    mock_request = MagicMock()
    mock_request.headers = {"X-User-ID": "test-user-id-123"}
    mock_db = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(request=mock_request, credentials=None, db=mock_db)
    assert exc_info.value.status_code == 401
    assert "missing bearer token" in exc_info.value.detail.lower()
