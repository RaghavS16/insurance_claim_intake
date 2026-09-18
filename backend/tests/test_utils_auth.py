"""
Edge-case tests for src/utils/auth.py

Covers: get_password_hash, verify_password, create_access_token,
        revoke_token, is_token_revoked, verify_token, TokenError enum.
"""
import time
import uuid
from datetime import timedelta
import pytest


# ---------------------------------------------------------------------------
# get_password_hash
# ---------------------------------------------------------------------------
class TestGetPasswordHash:
    def test_returns_string(self):
        from src.utils.auth import get_password_hash
        result = get_password_hash("SomePass1!")
        assert isinstance(result, str)

    def test_hash_is_bcrypt_format(self):
        from src.utils.auth import get_password_hash
        h = get_password_hash("SomePass1!")
        assert h.startswith("$2b$") or h.startswith("$2a$")

    def test_same_password_different_hashes(self):
        """Bcrypt generates unique salts each time."""
        from src.utils.auth import get_password_hash
        h1 = get_password_hash("SamePassword1!")
        h2 = get_password_hash("SamePassword1!")
        assert h1 != h2

    def test_empty_string_password(self):
        """Empty password should still produce a valid bcrypt hash."""
        from src.utils.auth import get_password_hash
        h = get_password_hash("")
        assert h.startswith("$2b$") or h.startswith("$2a$")

    def test_very_long_password(self):
        """Newer bcrypt raises ValueError for passwords > 72 bytes instead of truncating."""
        from src.utils.auth import get_password_hash
        long_pass = "A1!" * 100  # 300 chars > 72 byte bcrypt limit
        # This library version raises ValueError for passwords exceeding 72 bytes
        with pytest.raises(ValueError):
            get_password_hash(long_pass)

    def test_unicode_password(self):
        from src.utils.auth import get_password_hash
        h = get_password_hash("Passw0rd!")
        assert h.startswith("$2b$") or h.startswith("$2a$")

    def test_password_with_null_bytes(self):
        """Null bytes can truncate bcrypt - must not crash."""
        from src.utils.auth import get_password_hash
        h = get_password_hash("Pass\x001!")
        assert isinstance(h, str)


# ---------------------------------------------------------------------------
# verify_password
# ---------------------------------------------------------------------------
class TestVerifyPassword:
    def test_correct_password_returns_true(self):
        from src.utils.auth import get_password_hash, verify_password
        h = get_password_hash("Correct1!")
        assert verify_password("Correct1!", h) is True

    def test_wrong_password_returns_false(self):
        from src.utils.auth import get_password_hash, verify_password
        h = get_password_hash("Correct1!")
        assert verify_password("Wrong1!", h) is False

    def test_empty_plain_returns_false_not_crash(self):
        from src.utils.auth import get_password_hash, verify_password
        h = get_password_hash("Correct1!")
        assert verify_password("", h) is False

    def test_garbage_hash_returns_false(self):
        from src.utils.auth import verify_password
        assert verify_password("anypassword", "not-a-valid-bcrypt-hash") is False

    def test_none_like_hash_returns_false(self):
        from src.utils.auth import verify_password
        assert verify_password("password", "None") is False

    def test_case_sensitive(self):
        from src.utils.auth import get_password_hash, verify_password
        h = get_password_hash("Password1!")
        assert verify_password("password1!", h) is False

    def test_whitespace_difference(self):
        from src.utils.auth import get_password_hash, verify_password
        h = get_password_hash("Pass1! ")
        assert verify_password("Pass1!", h) is False


# ---------------------------------------------------------------------------
# create_access_token
# ---------------------------------------------------------------------------
class TestCreateAccessToken:
    def test_returns_string(self):
        from src.utils.auth import create_access_token
        token = create_access_token({"sub": "user-123"})
        assert isinstance(token, str) and len(token) > 20

    def test_contains_jti(self):
        import jwt as _jwt
        from src.utils.auth import create_access_token, ALGORITHM
        from src.config import settings
        token = create_access_token({"sub": "user-123"})
        payload = _jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert "jti" in payload
        uuid.UUID(payload["jti"])  # must be valid UUID

    def test_contains_sub(self):
        import jwt as _jwt
        from src.utils.auth import create_access_token, ALGORITHM
        from src.config import settings
        token = create_access_token({"sub": "user-abc"})
        payload = _jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "user-abc"

    def test_custom_expiry_delta(self):
        import jwt as _jwt
        from src.utils.auth import create_access_token, ALGORITHM
        from src.config import settings
        token = create_access_token({"sub": "u"}, expires_delta=timedelta(seconds=5))
        payload = _jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["exp"] - payload["iat"] <= 10

    def test_default_expiry_applied(self):
        import jwt as _jwt
        from src.utils.auth import create_access_token, ALGORITHM
        from src.config import settings
        token = create_access_token({"sub": "u"})
        payload = _jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        expected_delta = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        actual_delta = payload["exp"] - payload["iat"]
        assert abs(actual_delta - expected_delta) < 5

    def test_empty_data_dict(self):
        from src.utils.auth import create_access_token
        token = create_access_token({})
        assert isinstance(token, str)

    def test_data_dict_not_mutated(self):
        from src.utils.auth import create_access_token
        original = {"sub": "u", "role": "ADMIN"}
        data_copy = dict(original)
        create_access_token(original)
        assert original == data_copy

    def test_unique_jti_per_token(self):
        import jwt as _jwt
        from src.utils.auth import create_access_token, ALGORITHM
        from src.config import settings
        t1 = create_access_token({"sub": "u"})
        t2 = create_access_token({"sub": "u"})
        p1 = _jwt.decode(t1, settings.SECRET_KEY, algorithms=[ALGORITHM])
        p2 = _jwt.decode(t2, settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert p1["jti"] != p2["jti"]


# ---------------------------------------------------------------------------
# revoke_token
# ---------------------------------------------------------------------------
class TestRevokeToken:
    def setup_method(self):
        from src.utils import auth
        with auth._revoked_tokens_lock:
            auth._revoked_tokens.clear()

    def test_revoke_valid_token_returns_true(self):
        from src.utils.auth import create_access_token, revoke_token
        token = create_access_token({"sub": "u"})
        assert revoke_token(token) is True

    def test_revoke_arbitrary_string_returns_true(self):
        from src.utils.auth import revoke_token
        assert revoke_token("garbage-token-string") is True

    def test_revoke_empty_string_returns_true(self):
        from src.utils.auth import revoke_token
        assert revoke_token("") is True

    def test_revoked_token_is_detectable(self):
        from src.utils.auth import create_access_token, revoke_token, is_token_revoked
        token = create_access_token({"sub": "u"})
        revoke_token(token)
        assert is_token_revoked(token) is True

    def test_expired_revocations_are_cleaned(self):
        from src.utils import auth
        old_jti = str(uuid.uuid4())
        with auth._revoked_tokens_lock:
            auth._revoked_tokens[old_jti] = time.time() - 1
        fresh_token = auth.create_access_token({"sub": "u"})
        auth.revoke_token(fresh_token)
        with auth._revoked_tokens_lock:
            assert old_jti not in auth._revoked_tokens

    def test_double_revoke_is_idempotent(self):
        from src.utils.auth import create_access_token, revoke_token, is_token_revoked
        token = create_access_token({"sub": "u"})
        revoke_token(token)
        revoke_token(token)
        assert is_token_revoked(token) is True


# ---------------------------------------------------------------------------
# is_token_revoked
# ---------------------------------------------------------------------------
class TestIsTokenRevoked:
    def setup_method(self):
        from src.utils import auth
        with auth._revoked_tokens_lock:
            auth._revoked_tokens.clear()

    def test_fresh_token_not_revoked(self):
        from src.utils.auth import create_access_token, is_token_revoked
        token = create_access_token({"sub": "u"})
        assert is_token_revoked(token) is False

    def test_empty_string_not_revoked_by_default(self):
        from src.utils.auth import is_token_revoked
        assert is_token_revoked("") is False

    def test_garbage_token_not_revoked_by_default(self):
        from src.utils.auth import is_token_revoked
        assert is_token_revoked("not.a.jwt") is False

    def test_expired_revocation_no_longer_detected(self):
        from src.utils import auth
        jti = str(uuid.uuid4())
        with auth._revoked_tokens_lock:
            auth._revoked_tokens[jti] = time.time() - 1
        import jwt as _jwt
        from src.utils.auth import ALGORITHM
        from src.config import settings
        token = _jwt.encode(
            {"sub": "u", "jti": jti, "exp": int(time.time()) + 3600, "iat": int(time.time())},
            settings.SECRET_KEY,
            algorithm=ALGORITHM,
        )
        assert auth.is_token_revoked(token) is False


# ---------------------------------------------------------------------------
# verify_token
# ---------------------------------------------------------------------------
class TestVerifyToken:
    def setup_method(self):
        from src.utils import auth
        with auth._revoked_tokens_lock:
            auth._revoked_tokens.clear()

    def test_valid_token_returns_payload(self):
        from src.utils.auth import create_access_token, verify_token
        token = create_access_token({"sub": "user-42", "role": "CLAIMANT"})
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == "user-42"

    def test_tampered_signature_returns_none(self):
        from src.utils.auth import create_access_token, verify_token
        token = create_access_token({"sub": "u"})
        tampered = token[:-5] + "XXXXX"
        assert verify_token(tampered) is None

    def test_expired_token_returns_none(self):
        import jwt as _jwt
        from src.utils.auth import ALGORITHM, verify_token
        from src.config import settings
        expired_token = _jwt.encode(
            {"sub": "u", "exp": int(time.time()) - 1, "iat": int(time.time()) - 100},
            settings.SECRET_KEY,
            algorithm=ALGORITHM,
        )
        assert verify_token(expired_token) is None

    def test_garbage_string_returns_none(self):
        from src.utils.auth import verify_token
        assert verify_token("not.a.jwt.at.all") is None

    def test_empty_string_returns_none(self):
        from src.utils.auth import verify_token
        assert verify_token("") is None

    def test_revoked_token_returns_none(self):
        from src.utils.auth import create_access_token, revoke_token, verify_token
        token = create_access_token({"sub": "u"})
        revoke_token(token)
        assert verify_token(token) is None

    def test_wrong_secret_returns_none(self):
        import jwt as _jwt
        from src.utils.auth import ALGORITHM, verify_token
        token = _jwt.encode(
            {"sub": "u", "exp": int(time.time()) + 3600, "iat": int(time.time())},
            "WRONG-SECRET",
            algorithm=ALGORITHM,
        )
        assert verify_token(token) is None

    def test_algorithm_none_attack_returns_none(self):
        """JWT none algorithm attack must be rejected."""
        from src.utils.auth import verify_token
        import base64, json
        header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(json.dumps({"sub": "hacker", "exp": 9999999999}).encode()).rstrip(b"=").decode()
        none_token = f"{header}.{payload}."
        assert verify_token(none_token) is None


# ---------------------------------------------------------------------------
# TokenError enum
# ---------------------------------------------------------------------------
class TestTokenErrorEnum:
    def test_enum_values_exist(self):
        from src.utils.auth import TokenError
        assert TokenError.EXPIRED.value == "token_expired"
        assert TokenError.INVALID.value == "token_invalid"
        assert TokenError.MALFORMED.value == "token_malformed"
        assert TokenError.REVOKED.value == "token_revoked"

