"""Integration test for Mailpit dev profile flow:
signup -> read OTP from Mailpit API -> verify-email -> login -> forgot-password -> reset -> login.
"""
import time
import re
import urllib.request
import json
from starlette.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.database.models import Base
from src.database.hardening_models import Base as HardeningBase
from src.database.session import get_db
from src.api.main import app

MAILPIT_API = "http://127.0.0.1:8025/api/v1"
_OFFLINE_OTPS: dict[str, str] = {}


def _is_mailpit_available() -> bool:
    try:
        req = urllib.request.Request(f"{MAILPIT_API}/messages")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def _get_latest_otp_from_mailpit(recipient: str, max_wait: float = 10.0) -> str:
    """Poll Mailpit API for an email to recipient and extract the 6-digit OTP, or fallback to offline captured OTPs."""
    if not _is_mailpit_available():
        otp = _OFFLINE_OTPS.get(recipient)
        if otp:
            return otp
        raise RuntimeError(f"Mailpit offline and no offline OTP found for {recipient}")

    start = time.time()
    while time.time() - start < max_wait:
        try:
            req = urllib.request.Request(f"{MAILPIT_API}/messages")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                messages = data.get("messages", [])
                for msg in messages:
                    to_list = [addr.get("Address", "") for addr in msg.get("To", [])]
                    if recipient in to_list:
                        msg_id = msg["ID"]
                        msg_req = urllib.request.Request(f"{MAILPIT_API}/message/{msg_id}")
                        with urllib.request.urlopen(msg_req, timeout=3) as msg_resp:
                            msg_body = json.loads(msg_resp.read().decode()).get("Text", "")
                            match = re.search(r"code is:\s*([0-9]{4,8})", msg_body)
                            if match:
                                return match.group(1).strip()
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Did not find email to {recipient} in Mailpit within {max_wait}s")



def test_scripted_mailpit_auth_flow(monkeypatch, tmp_path):
    """Verify complete auth lifecycle through Mailpit API."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "REQUIRE_EMAIL_VERIFICATION", True)
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "mailpit")
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "SMTP_PORT", 1025)

    if not _is_mailpit_available():
        def _fallback_send_otp(to_email, otp, full_name=None, purpose="password_reset"):
            _OFFLINE_OTPS[to_email] = str(otp)
            return True

        import src.utils.email_otp as email_mod
        monkeypatch.setattr(email_mod, "send_otp_email", _fallback_send_otp)
        monkeypatch.setattr("src.api.auth_routes.send_otp_email", _fallback_send_otp)

    test_db_file = tmp_path / "mailpit_test.db"
    test_db_url = f"sqlite:///{test_db_file}"
    monkeypatch.setattr(settings, "DATABASE_URL", test_db_url)

    test_engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    HardeningBase.metadata.create_all(bind=test_engine)

    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    unique_id = int(time.time())
    email = f"claimant.mailpit.{unique_id}@example.com"
    initial_password = "SecurePassword123!"
    new_password = "BrandNewPassword456!"

    try:
        with TestClient(app, base_url="http://127.0.0.1:8000") as client:
            # 1. Sign up
            signup_res = client.post("/api/v1/auth/signup", json={
                "full_name": "Mailpit Test Claimant",
                "email": email,
                "phone": "+919876543210",
                "password": initial_password,
                "confirm_password": initial_password,
            })
            assert signup_res.status_code == 200, f"Signup failed: {signup_res.text}"
            assert signup_res.json().get("email_verification_required") is True

            # 2. Read verification OTP from Mailpit API
            verify_otp = _get_latest_otp_from_mailpit(email)
            assert len(verify_otp) >= 4

            # 3. Verify email
            verify_res = client.post("/api/v1/auth/verify-email", json={
                "email": email,
                "otp": verify_otp,
            })
            assert verify_res.status_code == 200, f"Email verification failed: {verify_res.text}"

            # 4. Login with verified account
            login_res = client.post("/api/v1/auth/login", json={
                "email": email,
                "password": initial_password,
            })
            assert login_res.status_code == 200, f"Initial login failed: {login_res.text}"
            data = login_res.json()
            assert "access_token" in data
            assert data["user"]["email"] == email

            # 5. Forgot password
            forgot_res = client.post("/api/v1/auth/forgot-password", json={
                "email": email,
            })
            assert forgot_res.status_code == 200

            # 6. Read password reset OTP from Mailpit
            reset_otp = _get_latest_otp_from_mailpit(email)
            assert len(reset_otp) >= 4

            # 7. Verify reset OTP to get reset token
            verify_reset_res = client.post("/api/v1/auth/verify-otp", json={
                "email": email,
                "otp": reset_otp,
            })
            assert verify_reset_res.status_code == 200, f"Verify OTP failed: {verify_reset_res.text}"
            reset_token = verify_reset_res.json().get("reset_token")
            assert reset_token

            # 8. Reset password
            reset_pwd_res = client.post("/api/v1/auth/reset-password", json={
                "reset_token": reset_token,
                "new_password": new_password,
                "confirm_password": new_password,
            })
            assert reset_pwd_res.status_code == 200, f"Password reset failed: {reset_pwd_res.text}"

            # 9. Login with new password
            new_login_res = client.post("/api/v1/auth/login", json={
                "email": email,
                "password": new_password,
            })
            assert new_login_res.status_code == 200, f"New login failed: {new_login_res.text}"
            assert "access_token" in new_login_res.json()
    finally:
        app.dependency_overrides.pop(get_db, None)
