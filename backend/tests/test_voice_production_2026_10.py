import os
from types import SimpleNamespace

import pytest
from aiortc import RTCPeerConnection

from src import config
from src.voice import pipecat as voice_pipecat
from src.voice.events import make_event
from src.voice.session_manager import VoiceEventStore, VoiceSessionManager


class FakeRedis:
    def __init__(self, active=None):
        self.active = active
        self.expirations = {}
        self.streams = []

    async def xadd(self, key, data, **kwargs):
        self.streams.append((key, data, kwargs))
        return "1-0"

    async def expire(self, key, ttl):
        self.expirations[key] = ttl
        return True

    async def get(self, key):
        if key.startswith("voice:active:"):
            return self.active
        return None

    async def set(self, *args, **kwargs):
        return True

    async def eval(self, *args, **kwargs):
        return 1


@pytest.mark.asyncio
async def test_voice_event_stream_has_explicit_retention(monkeypatch):
    monkeypatch.setattr(config.settings, "VOICE_EVENT_RETENTION_SECONDS", 3600)
    store = VoiceEventStore()
    store.redis = FakeRedis()
    await store.publish("CLAIM-1", make_event("voice.user.final", "CLAIM-1", text="hello"))
    assert store.expirations["voice:events:CLAIM-1"] == 3600


@pytest.mark.asyncio
async def test_voice_worker_drain_rejects_new_sessions(monkeypatch):
    manager = VoiceSessionManager()
    monkeypatch.setattr(config.settings, "VOICE_WORKER_DRAINING", True)
    assert await manager.start("CALL-1", "CLAIM-1", "USER-1", "model", "TENANT-1") is False


@pytest.mark.asyncio
async def test_attach_recovers_distributed_call_ownership(monkeypatch):
    manager = VoiceSessionManager()
    manager.events.redis = FakeRedis(active="CALL-1")
    row = SimpleNamespace(worker_id=config.settings.VOICE_WORKER_ID, ended_at=None, status="connecting")

    class Query:
        def filter(self, *args):
            return self
        def first(self):
            return row

    class DB:
        def query(self, *_args):
            return Query()
        def close(self):
            pass

    monkeypatch.setattr("src.voice.session_manager.SessionLocal", lambda: DB())

    async def fake_run(self, **_kwargs):
        return None

    monkeypatch.setattr(VoiceSessionManager, "_run", fake_run)

    class Connection:
        async def disconnect(self):
            return None

    await manager.attach(
        call_id="CALL-1",
        ticket_id="CLAIM-1",
        user_id="USER-1",
        connection=Connection(),
        tenant_id="TENANT-1",
    )
    await manager._tasks["CALL-1"]
    assert manager._active_call_by_ticket["CLAIM-1"] == "CALL-1"


@pytest.mark.asyncio
async def test_voice_heartbeat_uses_distributed_fencing_token():
    manager = VoiceSessionManager()
    manager.events.redis = FakeRedis(active="CALL-1")
    assert await manager.heartbeat(ticket_id="CLAIM-1", call_id="CALL-1") is True


@pytest.mark.asyncio
async def test_webrtc_offer_answer_round_trip():
    if os.getenv("RUN_VOICE_INTEGRATION") != "1":
        pytest.skip("Set RUN_VOICE_INTEGRATION=1 to run the WebRTC negotiation smoke test")
    browser = RTCPeerConnection()
    browser.addTransceiver("audio", direction="sendrecv")
    offer = await browser.createOffer()
    await browser.setLocalDescription(offer)
    server = voice_pipecat.SmallWebRTCConnection()
    try:
        await server.initialize(sdp=browser.localDescription.sdp, type=browser.localDescription.type)
        answer = server.get_answer()
        assert answer and answer.get("sdp") and answer.get("type") == "answer"
    finally:
        await server.disconnect()
        await browser.close()


@pytest.mark.asyncio
async def test_claim_voice_processor_executes_authoritative_claim_turn(monkeypatch):
    claim = SimpleNamespace(ticket_id="CLAIM-1", claimant_id="USER-1", tenant_id="TENANT-1")

    class Query:
        def filter(self, *args):
            return self
        def first(self):
            return claim

    class DB:
        def query(self, *_args):
            return Query()
        def close(self):
            pass

    class Events:
        def __init__(self):
            self.items = []
        async def publish(self, ticket_id, event):
            self.items.append((ticket_id, event))

    async def fake_turn(*_args, **_kwargs):
        return {
            "next_question": "What date did the incident happen?",
            "conversation_status": "collecting_dynamic",
            "extracted_data": {"incident_type": "accident"},
            "missing_fields": ["event_date"],
        }

    monkeypatch.setattr(voice_pipecat, "SessionLocal", lambda: DB())
    monkeypatch.setattr(voice_pipecat, "process_claimant_turn", fake_turn)
    processor = voice_pipecat.ClaimVoiceProcessor(
        ticket_id="CLAIM-1",
        call_id="CALL-1",
        user_id="USER-1",
        events=Events(),
        tenant_id="TENANT-1",
    )
    response = await processor._process_transcript("I had an accident")
    assert response == "What date did the incident happen?"
    assert processor._turn_count == 1
