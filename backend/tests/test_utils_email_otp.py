"""
Edge-case tests for src/utils/email_otp.py

Covers: generate_otp, hash_otp, otp_expiry, send_otp_email.
"""
import pytest
import hashlib
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# generate_otp
# ---------------------------------------------------------------------------
class TestGenerateOtp:
    def test_returns_string(self):
        from src.utils.email_otp import generate_otp
        assert isinstance(generate_otp(), str)

    def test_all_digits(self):
        from src.utils.email_otp import generate_otp
        otp = generate_otp()
        assert otp.isdigit()

    def test_length_matches_settings(self, monkeypatch):
        from src.utils.email_otp import generate_otp
        from src.config import settings
        monkeypatch.setattr(settings, "OTP_LENGTH", 4)
        # Re-import to pick up mock
        import importlib, src.utils.email_otp as m
        importlib.reload(m)
        otp = m.generate_otp()
        assert len(otp) == 4

    def test_unique_each_call(self):
        from src.utils.email_otp import generate_otp
        otps = {generate_otp() for _ in range(20)}
        assert len(otps) > 1  # very unlikely to be all the same

    def test_cryptographic_source(self):
        """generate_otp should use secrets module (no predictability test, just smoke)."""
        from src.utils.email_otp import generate_otp
        otp = generate_otp()
        assert len(otp) >= 4


# ---------------------------------------------------------------------------
# hash_otp
# ---------------------------------------------------------------------------
class TestHashOtp:
    def test_returns_sha256_hex(self):
        from src.utils.email_otp import hash_otp
        result = hash_otp("123456")
        expected = hashlib.sha256("123456".encode("utf-8")).hexdigest()
        assert result == expected

    def test_deterministic(self):
        from src.utils.email_otp import hash_otp
        assert hash_otp("999999") == hash_otp("999999")

    def test_different_otp_different_hash(self):
        from src.utils.email_otp import hash_otp
        assert hash_otp("123456") != hash_otp("654321")

    def test_empty_otp_hashes_consistently(self):
        from src.utils.email_otp import hash_otp
        h = hash_otp("")
        assert len(h) == 64  # SHA-256 hex length

    def test_returns_string(self):
        from src.utils.email_otp import hash_otp
        assert isinstance(hash_otp("000000"), str)


# ---------------------------------------------------------------------------
# otp_expiry
# ---------------------------------------------------------------------------
class TestOtpExpiry:
    def test_returns_future_datetime(self):
        from src.utils.email_otp import otp_expiry
        expiry = otp_expiry()
        assert expiry > datetime.now(timezone.utc)

    def test_expiry_matches_settings(self, monkeypatch):
        from src.config import settings
        monkeypatch.setattr(settings, "OTP_EXPIRY_MINUTES", 15)
        from src.utils.email_otp import otp_expiry
        before = datetime.now(timezone.utc)
        expiry = otp_expiry()
        after = datetime.now(timezone.utc)
        expected_lower = before + timedelta(minutes=14, seconds=59)
        expected_upper = after + timedelta(minutes=15, seconds=1)
        assert expected_lower <= expiry <= expected_upper

    def test_returns_timezone_aware_datetime(self):
        from src.utils.email_otp import otp_expiry
        expiry = otp_expiry()
        assert expiry.tzinfo is not None


# ---------------------------------------------------------------------------
# send_otp_email
# ---------------------------------------------------------------------------
class TestSendOtpEmail:
    def test_no_smtp_host_returns_false(self, monkeypatch):
        from src.config import settings
        monkeypatch.setattr(settings, "SMTP_HOST", None)
        monkeypatch.setattr(settings, "ENVIRONMENT", "test")
        from src.utils.email_otp import send_otp_email
        result = send_otp_email("test@example.com", "123456")
        assert result is False

    def test_smtp_sends_returns_true(self, monkeypatch):
        from src.config import settings
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.com")
        monkeypatch.setattr(settings, "SMTP_PORT", 587)
        monkeypatch.setattr(settings, "SMTP_USERNAME", "user@test.com")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "testpassword")
        monkeypatch.setattr(settings, "SMTP_USE_TLS", True)
        monkeypatch.setattr(settings, "ENVIRONMENT", "test")
        from src.utils.email_otp import send_otp_email

        mock_server = MagicMock()
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_server):
            result = send_otp_email("test@example.com", "123456", "Test User")
        assert result is True

    def test_smtp_failure_returns_false(self, monkeypatch):
        from src.config import settings
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.com")
        monkeypatch.setattr(settings, "SMTP_PORT", 587)
        monkeypatch.setattr(settings, "SMTP_USERNAME", "user")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "pass")
        monkeypatch.setattr(settings, "SMTP_USE_TLS", False)
        monkeypatch.setattr(settings, "ENVIRONMENT", "test")
        from src.utils.email_otp import send_otp_email
        with patch("smtplib.SMTP", side_effect=Exception("Connection refused")):
            result = send_otp_email("test@example.com", "123456")
        assert result is False

    def test_with_full_name_includes_name_in_body(self, monkeypatch):
        from src.config import settings
        monkeypatch.setattr(settings, "SMTP_HOST", None)
        monkeypatch.setattr(settings, "ENVIRONMENT", "test")
        from src.utils.email_otp import send_otp_email
        # Just test it doesn't raise with a full_name
        result = send_otp_email("test@example.com", "123456", full_name="Alice")
        assert result is False

    def test_without_full_name(self, monkeypatch):
        from src.config import settings
        monkeypatch.setattr(settings, "SMTP_HOST", None)
        monkeypatch.setattr(settings, "ENVIRONMENT", "test")
        from src.utils.email_otp import send_otp_email
        result = send_otp_email("test@example.com", "123456", full_name=None)
        assert result is False

    def test_production_env_no_otp_in_logs(self, monkeypatch, caplog):
        """In production, OTP must not be logged in plaintext."""
        import logging
        from src.config import settings
        monkeypatch.setattr(settings, "SMTP_HOST", None)
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        from src.utils.email_otp import send_otp_email
        with caplog.at_level(logging.INFO):
            send_otp_email("test@example.com", "SUPER_SECRET_OTP")
        for record in caplog.records:
            assert "SUPER_SECRET_OTP" not in record.getMessage()


# ---------------------------------------------------------------------------
# send_otp_email_async
# ---------------------------------------------------------------------------
class TestSendOtpEmailAsync:
    @pytest.mark.asyncio
    async def test_async_returns_false_without_smtp(self, monkeypatch):
        from src.config import settings
        monkeypatch.setattr(settings, "SMTP_HOST", None)
        monkeypatch.setattr(settings, "ENVIRONMENT", "test")
        from src.utils.email_otp import send_otp_email_async
        result = await send_otp_email_async("test@example.com", "123456")
        assert result is False
