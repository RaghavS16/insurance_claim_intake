"""
Edge-case tests for src/api/deps.py

Covers: get_current_user_id, require_role, resolve_bearer_user,
        get_claim_or_404, get_adjuster_or_404, db_commit_or_500.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# get_current_user_id
# ---------------------------------------------------------------------------
class TestGetCurrentUserId:
    def test_returns_user_id_string(self):
        from src.api.deps import get_current_user_id
        user = MagicMock()
        user.id = "user-123"
        result = get_current_user_id(current_user=user)
        assert result == "user-123"

    def test_returns_integer_id_as_is(self):
        from src.api.deps import get_current_user_id
        user = MagicMock()
        user.id = 42
        result = get_current_user_id(current_user=user)
        assert result == 42


# ---------------------------------------------------------------------------
# require_role
# ---------------------------------------------------------------------------
class TestRequireRole:
    def _make_user(self, role):
        u = MagicMock()
        u.role = role
        return u

    def test_allowed_role_returns_user(self):
        from src.api.deps import require_role
        dep = require_role(["ADMIN", "ADJUSTER"])
        user = self._make_user("ADMIN")
        with patch("src.api.deps.get_current_user", return_value=user):
            result = dep(current_user=user)
        assert result.role == "ADMIN"

    def test_forbidden_role_raises_403(self):
        from src.api.deps import require_role
        dep = require_role(["ADMIN"])
        user = self._make_user("CLAIMANT")
        with pytest.raises(HTTPException) as exc:
            dep(current_user=user)
        assert exc.value.status_code == 403

    def test_empty_allowed_roles_always_raises(self):
        from src.api.deps import require_role
        dep = require_role([])
        user = self._make_user("ADMIN")
        with pytest.raises(HTTPException) as exc:
            dep(current_user=user)
        assert exc.value.status_code == 403

    def test_multiple_allowed_roles_any_passes(self):
        from src.api.deps import require_role
        for role in ["ADMIN", "ADJUSTER"]:
            dep = require_role(["ADMIN", "ADJUSTER"])
            user = self._make_user(role)
            result = dep(current_user=user)
            assert result.role == role

    def test_unknown_role_raises(self):
        from src.api.deps import require_role
        dep = require_role(["ADMIN"])
        user = self._make_user("SUPERUSER")
        with pytest.raises(HTTPException) as exc:
            dep(current_user=user)
        assert exc.value.status_code == 403

    def test_error_message_mentions_role(self):
        from src.api.deps import require_role
        dep = require_role(["ADMIN"])
        user = self._make_user("CLAIMANT")
        with pytest.raises(HTTPException) as exc:
            dep(current_user=user)
        assert "CLAIMANT" in exc.value.detail


# ---------------------------------------------------------------------------
# get_claim_or_404
# ---------------------------------------------------------------------------
class TestGetClaimOr404:
    def test_existing_claim_returned(self):
        from src.api.deps import get_claim_or_404
        db = MagicMock()
        mock_claim = MagicMock()
        mock_claim.ticket_id = "CLAIM-ABCD1234"
        db.query.return_value.filter.return_value.first.return_value = mock_claim
        result = get_claim_or_404(db, "CLAIM-ABCD1234")
        assert result.ticket_id == "CLAIM-ABCD1234"

    def test_missing_claim_raises_404(self):
        from src.api.deps import get_claim_or_404
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(HTTPException) as exc:
            get_claim_or_404(db, "CLAIM-NOTEXIST")
        assert exc.value.status_code == 404

    def test_empty_ticket_id_raises_404(self):
        from src.api.deps import get_claim_or_404
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(HTTPException) as exc:
            get_claim_or_404(db, "")
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# get_adjuster_or_404
# ---------------------------------------------------------------------------
class TestGetAdjusterOr404:
    def test_existing_adjuster_returned(self):
        from src.api.deps import get_adjuster_or_404
        db = MagicMock()
        mock_adj = MagicMock()
        mock_adj.id = "adj-1"
        db.query.return_value.filter.return_value.first.return_value = mock_adj
        result = get_adjuster_or_404(db, "adj-1")
        assert result.id == "adj-1"

    def test_missing_adjuster_raises_404(self):
        from src.api.deps import get_adjuster_or_404
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(HTTPException) as exc:
            get_adjuster_or_404(db, "nonexistent-id")
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# db_commit_or_500
# ---------------------------------------------------------------------------
class TestDbCommitOr500:
    def test_successful_commit_no_raise(self):
        from src.api.deps import db_commit_or_500
        db = MagicMock()
        db.commit.return_value = None
        logger = MagicMock()
        db_commit_or_500(db, logger, "Operation failed")  # must not raise

    def test_commit_failure_raises_500(self):
        from src.api.deps import db_commit_or_500
        db = MagicMock()
        db.commit.side_effect = Exception("DB connection lost")
        logger = MagicMock()
        with pytest.raises(HTTPException) as exc:
            db_commit_or_500(db, logger, "Operation failed")
        assert exc.value.status_code == 500

    def test_rollback_called_on_failure(self):
        from src.api.deps import db_commit_or_500
        db = MagicMock()
        db.commit.side_effect = Exception("Deadlock")
        logger = MagicMock()
        with pytest.raises(HTTPException):
            db_commit_or_500(db, logger, "Failed")
        db.rollback.assert_called_once()

    def test_error_detail_in_exception(self):
        from src.api.deps import db_commit_or_500
        db = MagicMock()
        db.commit.side_effect = Exception("DB error")
        logger = MagicMock()
        with pytest.raises(HTTPException) as exc:
            db_commit_or_500(db, logger, "Custom error message")
        assert "Custom error message" in exc.value.detail

    def test_custom_log_message_used(self):
        from src.api.deps import db_commit_or_500
        db = MagicMock()
        db.commit.side_effect = Exception("err")
        logger = MagicMock()
        with pytest.raises(HTTPException):
            db_commit_or_500(db, logger, "error detail", log_message="Custom log message")
        # Logger exception should have been called
        logger.exception.assert_called()

    def test_empty_error_detail(self):
        from src.api.deps import db_commit_or_500
        db = MagicMock()
        db.commit.side_effect = Exception("err")
        logger = MagicMock()
        with pytest.raises(HTTPException) as exc:
            db_commit_or_500(db, logger, "")
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# resolve_bearer_user
# ---------------------------------------------------------------------------
class TestResolveBearerUser:
    def _make_request(self, auth_header=None):
        req = MagicMock()
        headers = {}
        if auth_header:
            headers["authorization"] = auth_header
        req.headers.get = lambda k, d="": headers.get(k.lower(), d)
        return req

    def test_valid_bearer_token_and_role(self, monkeypatch):
        from src.api.deps import resolve_bearer_user
        user = MagicMock()
        user.role = "ADMIN"
        req = self._make_request("Bearer valid-token")
        db = MagicMock()
        with patch("src.api.deps.get_current_user", return_value=user):
            result = resolve_bearer_user(req, db, ["ADMIN"])
        assert result.role == "ADMIN"

    def test_role_not_allowed_raises_403(self, monkeypatch):
        from src.api.deps import resolve_bearer_user
        user = MagicMock()
        user.role = "CLAIMANT"
        req = self._make_request("Bearer some-token")
        db = MagicMock()
        with patch("src.api.deps.get_current_user", return_value=user):
            with pytest.raises(HTTPException) as exc:
                resolve_bearer_user(req, db, ["ADMIN"])
        assert exc.value.status_code == 403

    def test_missing_bearer_prefix_passes_none_credentials(self, monkeypatch):
        from src.api.deps import resolve_bearer_user
        user = MagicMock()
        user.role = "ADMIN"
        req = self._make_request("Token some-token")  # no Bearer prefix
        db = MagicMock()
        with patch("src.api.deps.get_current_user", return_value=user):
            resolve_bearer_user(req, db, ["ADMIN"])

    def test_no_auth_header_passes_none_credentials(self, monkeypatch):
        from src.api.deps import resolve_bearer_user
        user = MagicMock()
        user.role = "ADMIN"
        req = self._make_request()
        db = MagicMock()
        with patch("src.api.deps.get_current_user", return_value=user):
            resolve_bearer_user(req, db, ["ADMIN"])
