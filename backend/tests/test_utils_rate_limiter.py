"""
Edge-case tests for src/utils/rate_limiter.py

Covers: InMemorySlidingWindowRateLimiter.is_allowed, reset,
        enforce_rate_limit (with mocked Request).
"""
import time
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# InMemorySlidingWindowRateLimiter
# ---------------------------------------------------------------------------
class TestInMemorySlidingWindowRateLimiter:
    def _make_limiter(self):
        from src.utils.rate_limiter import InMemorySlidingWindowRateLimiter
        return InMemorySlidingWindowRateLimiter()

    def test_first_request_allowed(self):
        lim = self._make_limiter()
        allowed, remaining, retry_after = lim.is_allowed("key1", max_requests=3, window_seconds=60)
        assert allowed is True
        assert remaining == 2
        assert retry_after == 0

    def test_within_limit_all_allowed(self):
        lim = self._make_limiter()
        for i in range(5):
            allowed, _, _ = lim.is_allowed("key2", max_requests=5, window_seconds=60)
            assert allowed is True

    def test_exceeds_limit_blocked(self):
        lim = self._make_limiter()
        for _ in range(3):
            lim.is_allowed("key3", max_requests=3, window_seconds=60)
        allowed, remaining, retry_after = lim.is_allowed("key3", max_requests=3, window_seconds=60)
        assert allowed is False
        assert remaining == 0
        assert retry_after >= 1

    def test_different_keys_independent(self):
        lim = self._make_limiter()
        for _ in range(3):
            lim.is_allowed("key-a", max_requests=3, window_seconds=60)
        # key-b should still be allowed
        allowed, _, _ = lim.is_allowed("key-b", max_requests=3, window_seconds=60)
        assert allowed is True

    def test_reset_specific_key(self):
        lim = self._make_limiter()
        for _ in range(3):
            lim.is_allowed("key4", max_requests=3, window_seconds=60)
        lim.reset("key4")
        allowed, _, _ = lim.is_allowed("key4", max_requests=3, window_seconds=60)
        assert allowed is True

    def test_reset_all_keys(self):
        lim = self._make_limiter()
        for _ in range(3):
            lim.is_allowed("k1", max_requests=3, window_seconds=60)
            lim.is_allowed("k2", max_requests=3, window_seconds=60)
        lim.reset()
        a1, _, _ = lim.is_allowed("k1", max_requests=3, window_seconds=60)
        a2, _, _ = lim.is_allowed("k2", max_requests=3, window_seconds=60)
        assert a1 is True
        assert a2 is True

    def test_window_expiry_allows_again(self):
        """After the window expires, requests should be allowed again."""
        lim = self._make_limiter()
        # Fill up window of 1 second
        for _ in range(2):
            lim.is_allowed("expkey", max_requests=2, window_seconds=1)
        allowed, _, _ = lim.is_allowed("expkey", max_requests=2, window_seconds=1)
        assert allowed is False
        # Wait for window to expire
        time.sleep(1.1)
        allowed, _, _ = lim.is_allowed("expkey", max_requests=2, window_seconds=1)
        assert allowed is True

    def test_max_requests_one_exactly(self):
        lim = self._make_limiter()
        a1, _, _ = lim.is_allowed("single", max_requests=1, window_seconds=60)
        assert a1 is True
        a2, _, _ = lim.is_allowed("single", max_requests=1, window_seconds=60)
        assert a2 is False

    def test_remaining_decrements_correctly(self):
        lim = self._make_limiter()
        _, rem1, _ = lim.is_allowed("rem", max_requests=5, window_seconds=60)
        _, rem2, _ = lim.is_allowed("rem", max_requests=5, window_seconds=60)
        assert rem1 == 4
        assert rem2 == 3

    def test_reset_nonexistent_key_no_error(self):
        lim = self._make_limiter()
        lim.reset("does-not-exist")  # Must not raise

    def test_empty_key_treated_as_valid(self):
        """Empty string key should work without errors."""
        lim = self._make_limiter()
        allowed, _, _ = lim.is_allowed("", max_requests=2, window_seconds=60)
        assert allowed is True

    def test_very_large_max_requests(self):
        lim = self._make_limiter()
        for _ in range(100):
            allowed, _, _ = lim.is_allowed("big", max_requests=10000, window_seconds=60)
            assert allowed is True


# ---------------------------------------------------------------------------
# enforce_rate_limit
# ---------------------------------------------------------------------------
class TestEnforceRateLimit:
    def _make_request(self, ip="127.0.0.1"):
        req = MagicMock()
        req.client = MagicMock()
        req.client.host = ip
        req.headers = MagicMock()
        req.headers.get = MagicMock(return_value=None)
        return req

    def test_test_environment_bypassed_by_default(self, monkeypatch):
        """In test env, enforce_rate_limit should not raise without X-Test-Enforce-Rate-Limit."""
        from src.utils.rate_limiter import enforce_rate_limit
        from src.config import settings
        monkeypatch.setattr(settings, "ENVIRONMENT", "test")
        req = self._make_request()
        # Should not raise even after many calls
        for _ in range(20):
            enforce_rate_limit(req, "test-action", max_requests=1, window_seconds=60)

    def test_test_environment_enforced_with_header(self, monkeypatch):
        """With X-Test-Enforce-Rate-Limit header, rate limit IS enforced in test env."""
        from src.utils.rate_limiter import enforce_rate_limit, limiter
        from src.config import settings
        monkeypatch.setattr(settings, "ENVIRONMENT", "test")
        limiter.reset()
        req = self._make_request()
        req.headers.get = lambda k, d=None: "1" if k == "X-Test-Enforce-Rate-Limit" else d
        with pytest.raises(HTTPException) as exc:
            for _ in range(10):
                enforce_rate_limit(req, "enforced-action", max_requests=2, window_seconds=60)
        assert exc.value.status_code == 429

    def test_retry_after_header_in_exception(self, monkeypatch):
        from src.utils.rate_limiter import enforce_rate_limit, limiter
        from src.config import settings
        monkeypatch.setattr(settings, "ENVIRONMENT", "test")
        limiter.reset()
        req = self._make_request(ip="10.0.0.1")
        req.headers.get = lambda k, d=None: "1" if k == "X-Test-Enforce-Rate-Limit" else d
        with pytest.raises(HTTPException) as exc:
            for _ in range(10):
                enforce_rate_limit(req, "action-retry", max_requests=1, window_seconds=60)
        assert exc.value.headers is not None and "Retry-After" in exc.value.headers

    def test_no_client_ip_uses_unknown(self, monkeypatch):
        """If request.client is None, key should use 'unknown'."""
        from src.utils.rate_limiter import enforce_rate_limit, limiter
        from src.config import settings
        monkeypatch.setattr(settings, "ENVIRONMENT", "test")
        limiter.reset()
        req = MagicMock()
        req.client = None
        req.headers.get = lambda k, d=None: "1" if k == "X-Test-Enforce-Rate-Limit" else d
        # Should not crash with None client
        with pytest.raises(HTTPException):
            for _ in range(10):
                enforce_rate_limit(req, "no-client", max_requests=1, window_seconds=60)

    def test_allow_test_bypass_false_enforces_in_test(self, monkeypatch):
        """allow_test_bypass=False should enforce even in test environment."""
        from src.utils.rate_limiter import enforce_rate_limit, limiter
        from src.config import settings
        monkeypatch.setattr(settings, "ENVIRONMENT", "test")
        limiter.reset()
        req = self._make_request(ip="10.0.0.2")
        req.headers.get = lambda k, d=None: None
        with pytest.raises(HTTPException):
            for _ in range(10):
                enforce_rate_limit(req, "no-bypass", max_requests=1, window_seconds=60, allow_test_bypass=False)
