import pytest
import time
from fastapi.testclient import TestClient
from src.database.models import Claim
from src.database.session import SessionLocal
from src.voice.vad import SpeechEndpointDetector, calculate_rms
from src.voice.stt import _is_hallucination, _run_whisper


def test_calculate_rms():
    """Verify calculate_rms computes correct values for silence and signals."""
    silence = b"\x00\x00" * 480
    assert calculate_rms(silence) == 0.0

    # Sine-like signal bytes: alternating small positive and negative shorts
    signal = b"\x10\x00\xf0\xff" * 240
    rms = calculate_rms(signal)
    assert rms > 0.0


def test_whisper_hallucination_filtering():
    """Verify that is_hallucination correctly identifies hallucinated phrases."""
    assert _is_hallucination("thank you") is True
    assert _is_hallucination("thank you very much.") is True
    assert _is_hallucination("Go ahead") is True
    assert _is_hallucination("I broke my windshield yesterday") is False


def test_speech_detector_rms_gate():
    """Verify SpeechEndpointDetector rejects silent low-energy frames even if VAD suggests speech."""
    detector = SpeechEndpointDetector()
    
    # 1. Feed low-amplitude/silent bytes (VAD might trigger, but RMS gate should drop it)
    # alternations around 10-20 amplitude (very low noise)
    noise_chunk = b"\x10\x00\xf0\xff" * 240  # 480 samples = 30ms frame
    events = detector.feed(noise_chunk)
    assert not detector.is_in_speech
    assert len(events) == 0


def test_auth_claim_endpoints(client: TestClient):
    """Test claim endpoints enforce authentication and authorization (ownership)."""
    # 1. Initialize session for USER-A
    headers_a = {"X-User-ID": "USER-A"}
    res = client.post("/api/v1/claims/voice-session", headers=headers_a)
    assert res.status_code == 200
    data = res.json()
    ticket_id = data["ticket_id"]

    # 2. Verify USER-A can retrieve the claim details
    res_get = client.get(f"/api/v1/claims/{ticket_id}", headers=headers_a)
    assert res_get.status_code == 200

    # 3. Verify USER-B is blocked from retrieving the claim details (403 Forbidden)
    headers_b = {"X-User-ID": "USER-B"}
    res_blocked = client.get(f"/api/v1/claims/{ticket_id}", headers=headers_b)
    assert res_blocked.status_code == 403

    # 4. Verify list_claims returns only USER-A's claims for USER-A
    res_list = client.get("/api/v1/claims", headers=headers_a)
    assert res_list.status_code == 200
    claims = res_list.json()["items"]
    assert all(c["ticket_id"] == ticket_id for c in claims)
