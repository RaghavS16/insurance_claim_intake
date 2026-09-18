"""
Shared test fixtures and configuration for all edge-case tests.
"""
import os
import pytest
from unittest.mock import MagicMock, patch

# Ensure test environment before importing anything from src
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-32chars!")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# ---------------------------------------------------------------------------
# Settings patch – use a lightweight in-memory config for all tests
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    """Patch settings to use safe test values without touching real .env."""
    from src.config import settings
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-key-at-least-32-chars!!")
    monkeypatch.setattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 60)
    monkeypatch.setattr(settings, "OTP_LENGTH", 6)
    monkeypatch.setattr(settings, "OTP_EXPIRY_MINUTES", 10)
    monkeypatch.setattr(settings, "SMTP_HOST", None)
    monkeypatch.setattr(settings, "REDIS_URL", None)


@pytest.fixture
def mock_db():
    """A MagicMock SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def make_user():
    """Factory for creating mock User objects."""
    from src.database.models import User

    def _make(role="CLAIMANT", uid="user-1", email="test@example.com"):
        u = MagicMock(spec=User)
        u.id = uid
        u.role = role
        u.email = email
        u.full_name = "Test User"
        return u

    return _make


@pytest.fixture
def make_claim():
    """Factory for creating mock Claim objects."""
    from src.database.models import Claim

    def _make(
        ticket_id="CLAIM-ABCD1234",
        status="draft",
        claimant_id="user-1",
        customer_id=None,
        insurance_type="motor",
        pipeline_state=None,
    ):
        c = MagicMock(spec=Claim)
        c.id = "claim-uuid-1"
        c.ticket_id = ticket_id
        c.status = status
        c.claimant_id = claimant_id
        c.customer_id = customer_id
        c.insurance_type = insurance_type
        c.pipeline_state = pipeline_state or {}
        return c

    return _make


@pytest.fixture
def make_adjuster():
    """Factory for creating mock Adjuster objects."""
    from src.database.models import Adjuster

    def _make(adj_id="adj-1", name="John Doe", specialization="motor", is_active=True, claims_assigned=0):
        a = MagicMock(spec=Adjuster)
        a.id = adj_id
        a.name = name
        a.specialization = specialization
        a.is_active = is_active
        a.claims_assigned = claims_assigned
        return a

    return _make
