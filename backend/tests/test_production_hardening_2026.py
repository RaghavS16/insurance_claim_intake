"""Production hardening regression tests that do not require the frontend."""
from __future__ import annotations

import asyncio
import io
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request


def _request(headers: dict[str, str], host: str = "127.0.0.1") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": "POST", "path": "/", "headers": raw, "client": (host, 1234), "query_string": b""})


def test_rate_limiter_does_not_trust_client_identity_header():
    from src.utils.rate_limiter import enforce_rate_limit, limiter
    limiter.reset()
    first = _request({"X-Rate-Limit-Identity": "attacker-a"})
    second = _request({"X-Rate-Limit-Identity": "attacker-b"})
    enforce_rate_limit(first, action="hardening-test", max_requests=1, window_seconds=60, allow_test_bypass=False)
    with pytest.raises(Exception) as exc:
        enforce_rate_limit(second, action="hardening-test", max_requests=1, window_seconds=60, allow_test_bypass=False)
    assert getattr(exc.value, "status_code", None) == 429


def test_document_archive_expansion_limit(monkeypatch):
    from src.config import settings
    from src.utils.document_safety import enforce_document_limits
    monkeypatch.setattr(settings, "MAX_ARCHIVE_EXPANDED_BYTES", 100)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("a.txt", b"x" * 101)
    with pytest.raises(ValueError):
        enforce_document_limits(buf.getvalue(), "evidence.zip")


def test_extracted_text_limit(monkeypatch):
    from src.config import settings
    from src.utils.document_safety import enforce_extracted_text_limit
    monkeypatch.setattr(settings, "MAX_EXTRACTED_TEXT_CHARS", 10)
    with pytest.raises(ValueError):
        enforce_extracted_text_limit("01234567890", "policy.pdf")


def test_voice_worker_drain_rejects_new_session(monkeypatch):
    from src.voice.session_manager import VoiceSessionManager
    from src.config import settings
    monkeypatch.setattr(settings, "VOICE_WORKER_DRAINING", True)
    manager = VoiceSessionManager()
    result = asyncio.run(manager.start(
        call_id="CALL-DRAIN",
        ticket_id="CLAIM-DRAIN",
        user_id="user-1",
        model="test",
        tenant_id="tenant-1",
    ))
    assert result is False


@pytest.mark.asyncio
async def test_voice_pipeline_connected_callback_updates_session_without_self(monkeypatch):
    import src.voice.pipecat as voice

    callbacks = {}
    class FakeTransport:
        def event_handler(self, name):
            def decorator(fn):
                callbacks[name] = fn
                return fn
            return decorator
        async def event(self, name):
            return await callbacks[name](self, object())

    class FakeRunner:
        def __init__(self, *args, **kwargs):
            pass
        async def run(self, task):
            await callbacks["on_client_connected"](fake_transport, object())

    fake_transport = FakeTransport()
    monkeypatch.setattr(voice, "PipelineRunner", FakeRunner)
    async def fake_build(**kwargs):
        return fake_transport, object(), AsyncMock()
    monkeypatch.setattr(voice, "build_voice_pipeline", fake_build)
    status = AsyncMock()
    monkeypatch.setattr(voice, "_set_session_status", status)

    events = SimpleNamespace(publish=AsyncMock())
    connection = AsyncMock()

    await voice.run_voice_pipeline(
        connection=connection,
        ticket_id="CLAIM-VOICE",
        call_id="CALL-VOICE",
        user_id="user-1",
        tenant_id="tenant-1",
        events=events,
    )
    status.assert_awaited_once_with("CALL-VOICE", "active")
    assert callbacks["on_client_connected"] is not None


def test_ai_model_allowlist_blocks_unapproved_model(monkeypatch):
    from src.config import settings
    from src.services.ai_governance import assert_model_allowed
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "AI_REQUIRE_MODEL_GOVERNANCE_IN_PRODUCTION", True)
    monkeypatch.setattr(settings, "AI_ALLOWED_MODELS", "approved:model")
    with pytest.raises(RuntimeError):
        assert_model_allowed("blocked:model")


def test_adjuster_model_exposes_user_identity():
    from src.database.models import Adjuster
    assert hasattr(Adjuster, "user_id")


def test_webauthn_models_import():
    from src.database.hardening_models import WebAuthnCredential, WebAuthnChallenge
    assert WebAuthnCredential.__tablename__ == "webauthn_credentials"
    assert WebAuthnChallenge.__tablename__ == "webauthn_challenges"
