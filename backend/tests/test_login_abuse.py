"""Tests for login abuse prevention, constant-time authentication, account lockout, and fail-closed behaviors."""
import time
import pytest
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from src.config import settings
from src.api.main import app
from src.utils.auth import get_password_hash
from src.utils.account_lockout import (
    lockout_manager,
    check_account_lock,
    record_auth_failure,
    record_auth_success,
    unlock_account,
    LOCKOUT_MAX_FAILURES,
)

client = TestClient(app)


@pytest.fixture
def abuse_test_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.database.models import Base
    from src.database.hardening_models import Base as HardeningBase
    from src.database.session import get_db

    db_file = tmp_path / "abuse_test.db"
    db_url = f"sqlite:///{db_file}"
    monkeypatch.setattr(settings, "DATABASE_URL", db_url)

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    HardeningBase.metadata.create_all(bind=engine)

    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield Session
    app.dependency_overrides.pop(get_db, None)


def test_unknown_email_and_wrong_password_indistinguishable(abuse_test_db, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_TEST_AUTH", True)

    from src.database.models import User

    db = abuse_test_db()
    try:
        user_id = str(uuid.uuid4())
        tenant_id = "00000000-0000-0000-0000-000000000001"
        real_email = f"real_user_{user_id}@example.com"
        u = User(
            id=user_id,
            email=real_email,
            password_hash=get_password_hash("CorrectPassword123!"),
            full_name="Real User",
            role="CLAIMANT",
            status="active",
            email_verified_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
        )
        db.add(u)
        db.commit()

        # Non-existent user
        fake_email = f"nonexistent_{uuid.uuid4()}@example.com"
        res_fake = client.post("/api/v1/auth/login", json={"email": fake_email, "password": "AnyPassword123!"})

        # Existing user with wrong password
        res_wrong = client.post("/api/v1/auth/login", json={"email": real_email, "password": "WrongPassword123!"})

        # Responses must be completely indistinguishable
        assert res_fake.status_code == 401
        assert res_wrong.status_code == 401
        assert res_fake.json() == {"detail": "Invalid email or password."}
        assert res_wrong.json() == {"detail": "Invalid email or password."}
    finally:
        db.close()


def test_login_lockout_after_5_failures_and_unlock(abuse_test_db, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_TEST_AUTH", True)

    from src.database.models import User

    db = abuse_test_db()
    try:
        user_id = str(uuid.uuid4())
        tenant_id = "00000000-0000-0000-0000-000000000001"
        test_email = f"lockout_{user_id}@example.com"
        u = User(
            id=user_id,
            email=test_email,
            password_hash=get_password_hash("ValidPass123!"),
            full_name="Lockout Test",
            role="CLAIMANT",
            status="active",
            email_verified_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
        )
        db.add(u)
        db.commit()

        # Unlock any prior state
        unlock_account("login", test_email)

        # 5 failed attempts
        for i in range(LOCKOUT_MAX_FAILURES):
            res = client.post("/api/v1/auth/login", json={"email": test_email, "password": f"WrongPass{i}!"})
            assert res.status_code == 401
            assert res.json() == {"detail": "Invalid email or password."}

        # 6th attempt must be locked out with 429
        res_locked = client.post("/api/v1/auth/login", json={"email": test_email, "password": "ValidPass123!"})
        assert res_locked.status_code == 429
        assert "temporarily locked" in res_locked.json()["detail"]
        assert "Retry-After" in res_locked.headers

        # Unlock account (simulating window expiry)
        unlock_account("login", test_email)

        # Now login succeeds
        res_success = client.post("/api/v1/auth/login", json={"email": test_email, "password": "ValidPass123!"})
        assert res_success.status_code == 200
        assert "access_token" in res_success.json()
    finally:
        db.close()


def test_verify_otp_lockout(abuse_test_db, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_TEST_AUTH", True)

    email = f"otp_abuse_{uuid.uuid4()}@example.com"
    unlock_account("verify_otp", email)

    for i in range(LOCKOUT_MAX_FAILURES):
        res = client.post("/api/v1/auth/verify-otp", json={"email": email, "otp": "000000"})
        assert res.status_code in (400, 429)

    # 6th attempt is locked
    res_locked = client.post("/api/v1/auth/verify-otp", json={"email": email, "otp": "000000"})
    assert res_locked.status_code == 429
    assert "temporarily locked" in res_locked.json()["detail"]
    assert "Retry-After" in res_locked.headers
    unlock_account("verify_otp", email)


def test_security_fail_closed_when_redis_fails_in_production(monkeypatch):
    from src.utils.account_lockout import RedisAccountLockout
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SECURITY_FAIL_CLOSED", True)
    monkeypatch.delenv("ALLOW_INSECURE_TEST_AUTH", raising=False)

    # RedisAccountLockout pointing to an invalid port
    bad_redis = RedisAccountLockout("redis://127.0.0.1:1/0")
    # Must fail closed in production
    with pytest.raises(HTTPException) as exc_info:
        bad_redis.is_locked("test_key")
    assert exc_info.value.status_code == 503
