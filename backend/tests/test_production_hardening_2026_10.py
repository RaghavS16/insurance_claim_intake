import os
from types import SimpleNamespace

import pytest
from starlette.requests import Request

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-characters-long")

from src import config
from src.api import auth_routes
from src.agents import llm_factory
from src.services import outbox
from src.utils import document_safety, rate_limiter
from src.voice.events import make_event

def _request(headers=None):
    raw = [(k.lower().encode(), str(v).encode()) for k, v in (headers or {}).items()]
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": raw,
        "client": ("203.0.113.10", 1234),
        "scheme": "http",
    })

def test_rate_limiter_uses_trusted_auth_state_not_client_identity_header(monkeypatch):
    captured = {}
    def fake_is_allowed(key, max_requests, window_seconds):
        captured["key"] = key
        return True, max_requests - 1, 0
    monkeypatch.setattr(rate_limiter.limiter, "is_allowed", fake_is_allowed)
    request = _request({
        "Authorization": "Bearer example-token",
        "X-Rate-Limit-Identity": "attacker-controlled",
        "X-Test-Enforce-Rate-Limit": "1",
    })
    request.state.authenticated_user_id = "user-123"
    request.state.authenticated_tenant_id = "tenant-123"
    rate_limiter.enforce_rate_limit(request, "claim", allow_test_bypass=False)
    assert "attacker-controlled" not in captured["key"]
    assert "tenant-123" in captured["key"]
    assert "user-123" in captured["key"]

def test_pdf_page_limit_is_enforced_before_parser_work(monkeypatch):
    class FakePdfReader:
        def __init__(self, *_args, **_kwargs):
            self.pages = [1, 2, 3]
    monkeypatch.setattr(document_safety, "PdfReader", FakePdfReader)
    monkeypatch.setattr(config.settings, "MAX_PDF_PAGES", 2)
    with pytest.raises(ValueError, match="maximum of 2 pages"):
        document_safety.enforce_document_limits(b"%PDF-fake", "claim.pdf")

from typing import Any, cast

def test_access_token_contains_tenant_and_actual_mfa_state():
    user = SimpleNamespace(id="user-123", tenant_id="tenant-123", role="CLAIMANT", full_name="Test User", email="test@example.com")
    response = auth_routes._auth_response(cast(Any, user), "refresh-token-placeholder", amr=["pwd"], mfa_authenticated=False)
    import jwt
    payload = jwt.decode(response["access_token"], config.settings.SECRET_KEY, algorithms=["HS256"])
    assert payload["tenant_id"] == "tenant-123"
    assert payload["mfa"] is False
    assert payload["amr"] == ["pwd"]

def test_llm_local_fallback_is_blocked_when_governance_disables_it(monkeypatch):
    class BrokenModel:
        def invoke(self, *_args, **_kwargs):
            raise RuntimeError("timeout")
    called = {"fallback": False}
    def fallback():
        called["fallback"] = True
        return SimpleNamespace(invoke=lambda *_a, **_k: "fallback")
    resilient = llm_factory.ResilientChatModel(cast(Any, BrokenModel()), cast(Any, fallback))
    monkeypatch.setattr(config.settings, "AI_ALLOW_LOCAL_FALLBACK", False)
    with pytest.raises(RuntimeError):
        resilient.invoke("hello")
    assert called["fallback"] is False

def test_voice_event_text_is_bounded(monkeypatch):
    monkeypatch.setattr(config.settings, "VOICE_MAX_EVENT_TEXT_CHARS", 10)
    event = make_event("voice.user.final", "CLAIM-1", text="0123456789ABCDEFGHIJ")
    assert event["text"] == "0123456789"

def test_outbox_exhaustion_moves_to_dead_letter(monkeypatch):
    row = SimpleNamespace(attempts=0, status="pending", next_attempt_at=None, processed_at=None, last_error=None)
    monkeypatch.setattr(config.settings, "OUTBOX_MAX_ATTEMPTS", 2)
    outbox.mark_retry(cast(Any, row), RuntimeError("temporary"))
    assert row.attempts == 1 and row.status == "pending"
    outbox.mark_retry(cast(Any, row), RuntimeError("temporary"))
    assert row.attempts == 2
    assert row.status == "dead_letter"
    assert row.processed_at is not None


@pytest.mark.asyncio
async def test_knowledge_search_preserves_ai_quota_http_errors(monkeypatch):
    from fastapi import HTTPException
    from src.api import knowledge_routes

    class FailingGuard:
        async def __aenter__(self):
            raise HTTPException(status_code=429, detail="AI request quota exceeded")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        knowledge_routes,
        "tenant_ai_guard",
        lambda *args, **kwargs: FailingGuard(),
    )
    user = SimpleNamespace(id="adjuster-1", tenant_id="tenant-1", role="ADJUSTER")

    with pytest.raises(HTTPException) as exc:
        await knowledge_routes.retrieve(q="coverage", user=user)

    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_local_ai_concurrency_is_released_when_redis_is_unavailable(monkeypatch):
    from src.services import ai_governance

    async def no_redis():
        return None

    monkeypatch.setattr(ai_governance, "_redis_client", no_redis)
    tenant = "tenant-local-concurrency-regression"
    key = f"{tenant}:claim_turn:concurrency"
    ai_governance._local_concurrency.pop(key, None)
    ai_governance._local_windows.pop(f"{tenant}:claim_turn", None)

    async with ai_governance.tenant_ai_guard(
        tenant,
        operation="claim_turn",
        max_requests=100,
        max_concurrent=1,
    ):
        assert ai_governance._local_concurrency[key] == 1

    assert ai_governance._local_concurrency[key] == 0
