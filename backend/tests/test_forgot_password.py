import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.database.models import User, PasswordResetOTP
from src.utils.auth import get_password_hash, create_access_token
from src.utils.email_otp import hash_otp


def test_forgot_password_full_flow(client: TestClient, db: Session):
    # 1. Create a test user
    test_email = "forgot_user@example.com"
    old_password = "OldPassword123!"
    user = User(
        full_name="Forgot User",
        email=test_email,
        phone="+919876543210",
        password_hash=get_password_hash(old_password),
        role="CLAIMANT",
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 2. Request OTP for existing active user
    res = client.post("/api/v1/auth/forgot-password", json={"email": test_email})
    assert res.status_code == 200
    assert "reset code has been sent" in res.json()["message"]

    # Verify OTP record in DB
    otp_record = (
        db.query(PasswordResetOTP)
        .filter(PasswordResetOTP.user_id == user.id)
        .order_by(PasswordResetOTP.created_at.desc())
        .first()
    )
    assert otp_record is not None
    assert otp_record.verified is False
    assert otp_record.consumed is False
    assert otp_record.attempts == 0

    # 3. Test generic response for non-existent email (enumeration safety)
    res_non_existent = client.post("/api/v1/auth/forgot-password", json={"email": "nonexistent@example.com"})
    assert res_non_existent.status_code == 200
    assert "reset code has been sent" in res_non_existent.json()["message"]

    # 4. Verify OTP failure with incorrect code
    res_wrong = client.post("/api/v1/auth/verify-otp", json={
        "email": test_email,
        "otp": "000000"
    })
    assert res_wrong.status_code == 400
    db.refresh(otp_record)
    assert otp_record.attempts == 1

    # 5. Set known OTP on record for deterministic testing
    test_otp = "123456"
    setattr(otp_record, "otp_hash", hash_otp(test_otp))
    db.commit()

    # 6. Verify OTP with correct code
    res_verify = client.post("/api/v1/auth/verify-otp", json={
        "email": test_email,
        "otp": test_otp
    })
    assert res_verify.status_code == 200
    verify_data = res_verify.json()
    assert "reset_token" in verify_data
    reset_token = verify_data["reset_token"]

    db.refresh(otp_record)
    assert otp_record.verified is True

    # 7. Reset password validation: passwords don't match
    res_mismatch = client.post("/api/v1/auth/reset-password", json={
        "reset_token": reset_token,
        "new_password": "NewPassword123!",
        "confirm_password": "DifferentPassword123!"
    })
    assert res_mismatch.status_code == 400
    assert "do not match" in res_mismatch.json()["detail"]

    # 8. Reset password validation: weak password (fails complexity validator)
    res_weak = client.post("/api/v1/auth/reset-password", json={
        "reset_token": reset_token,
        "new_password": "weakpassword",
        "confirm_password": "weakpassword"
    })
    assert res_weak.status_code == 400
    assert "Password must" in res_weak.json()["detail"]

    # 9. Successful password reset
    new_password = "NewPassword123!"
    res_reset = client.post("/api/v1/auth/reset-password", json={
        "reset_token": reset_token,
        "new_password": new_password,
        "confirm_password": new_password
    })
    assert res_reset.status_code == 200
    assert "successfully" in res_reset.json()["message"]

    db.refresh(otp_record)
    assert otp_record.consumed is True

    # 10. Cannot reuse reset token / OTP record
    res_reuse = client.post("/api/v1/auth/reset-password", json={
        "reset_token": reset_token,
        "new_password": "AnotherPassword123!",
        "confirm_password": "AnotherPassword123!"
    })
    assert res_reuse.status_code == 401

    # 11. Old password fails login, new password succeeds
    res_login_old = client.post("/api/v1/auth/login", json={
        "email": test_email,
        "password": old_password
    })
    assert res_login_old.status_code == 401

    res_login_new = client.post("/api/v1/auth/login", json={
        "email": test_email,
        "password": new_password
    })
    assert res_login_new.status_code == 200
    assert "access_token" in res_login_new.json()


def test_verify_otp_max_attempts_rate_limit(client: TestClient, db: Session):
    test_email = "rate_limit_user@example.com"
    user = User(
        full_name="Rate Limit User",
        email=test_email,
        password_hash=get_password_hash("Password123!"),
        role="CLAIMANT",
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    record = PasswordResetOTP(
        user_id=user.id,
        otp_hash=hash_otp("999999"),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        attempts=5,  # Exceeded max attempts
        verified=False,
        consumed=False,
    )
    db.add(record)
    db.commit()

    res = client.post("/api/v1/auth/verify-otp", json={
        "email": test_email,
        "otp": "999999"
    })
    assert res.status_code == 429
    assert "Too many incorrect attempts" in res.json()["detail"]


def test_verify_otp_expired(client: TestClient, db: Session):
    test_email = "expired_otp_user@example.com"
    user = User(
        full_name="Expired User",
        email=test_email,
        password_hash=get_password_hash("Password123!"),
        role="CLAIMANT",
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    record = PasswordResetOTP(
        user_id=user.id,
        otp_hash=hash_otp("111222"),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # Expired
        attempts=0,
        verified=False,
        consumed=False,
    )
    db.add(record)
    db.commit()

    res = client.post("/api/v1/auth/verify-otp", json={
        "email": test_email,
        "otp": "111222"
    })
    assert res.status_code == 400
    assert "Invalid or expired code" in res.json()["detail"]


def test_send_otp_email_sender_name_insureclaim_ai(monkeypatch):
    from unittest.mock import MagicMock, patch
    from src.config import settings
    from src.utils.email_otp import send_otp_email

    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "raghavradhakrishnan.d@gmail.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret")
    monkeypatch.setattr(settings, "SMTP_FROM_NAME", "InsureClaim AI")

    mock_smtp_instance = MagicMock()
    with patch("smtplib.SMTP", return_value=mock_smtp_instance) as mock_smtp_cls:
        mock_smtp_instance.__enter__.return_value = mock_smtp_instance
        success = send_otp_email("user@example.com", "123456", "Test User")
        assert success is True

        # Verify sendmail was called and inspect the MIME message payload
        args, kwargs = mock_smtp_instance.sendmail.call_args
        from_addr, to_addrs, raw_msg = args
        assert "From: InsureClaim AI <raghavradhakrishnan.d@gmail.com>" in raw_msg
        assert "Subject: Your InsureClaimAI password reset code" in raw_msg
