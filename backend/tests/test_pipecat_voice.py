"""Unit tests for Pipecat voice adapters and the insurance-agent bridge."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pipecat.frames.frames import InterruptionFrame, OutputAudioRawFrame, OutputTransportMessageFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection

from src.voice.pipecat import ClaimAgentProcessor, PCM16WebSocketSerializer, WebRTCVADAnalyzer


@pytest.mark.asyncio
async def test_pcm_serializer_round_trips_audio_to_browser_wav():
    serializer = PCM16WebSocketSerializer()
    frame = OutputAudioRawFrame(audio=b"\x00\x00" * 160, sample_rate=16000, num_channels=1)
    payload = await serializer.serialize(frame)
    assert isinstance(payload, bytes)
    assert payload.startswith(b"RIFF")
    decoded = await serializer.deserialize(b"\x00\x00" * 160)
    assert decoded.sample_rate == 16000
    assert decoded.num_channels == 1
    assert decoded.audio == b"\x00\x00" * 160


@pytest.mark.asyncio
async def test_serializer_emits_application_json_events():
    serializer = PCM16WebSocketSerializer()
    payload = await serializer.serialize(OutputTransportMessageFrame(message={"type": "barge_in"}))
    assert '"type": "barge_in"' in payload


def test_webrtc_vad_uses_configurable_aggressiveness():
    analyzer = WebRTCVADAnalyzer(aggressiveness=2)
    assert analyzer.sample_rate == 16000
    assert analyzer.num_frames_required() == 320


@pytest.mark.asyncio
async def test_claim_agent_processor_forwards_interruption():
    claim = MagicMock()
    with patch("src.voice.pipecat.SessionLocal") as session_factory:
        db = MagicMock(); session_factory.return_value = db
        processor = ClaimAgentProcessor(claim)
        processor.push_frame = AsyncMock()
        await processor.process_frame(InterruptionFrame(), FrameDirection.DOWNSTREAM)
        messages = [call.args[0] for call in processor.push_frame.await_args_list]
        assert any(isinstance(item, OutputTransportMessageFrame) and item.message["type"] == "barge_in" for item in messages)
        assert any(isinstance(item, InterruptionFrame) for item in messages)
        await processor.cleanup()


@pytest.mark.asyncio
async def test_claim_agent_processor_debounces_short_pauses_into_one_turn():
    claim = MagicMock()
    result = {
        "extracted_data": {"insurance_type": "motor"},
        "missing_fields": ["policy_id"],
        "field_status": {},
        "awaiting_confirmation": False,
        "confirmed": False,
        "conversation_status": "collecting",
        "next_question": "What is your policy number?",
    }
    with patch("src.voice.pipecat.SessionLocal") as session_factory, patch(
        "src.voice.pipecat.process_claimant_turn", new=AsyncMock(return_value=result)
    ) as process_turn:
        db = MagicMock(); db.query.return_value.filter.return_value.first.return_value = claim
        session_factory.return_value = db
        processor = ClaimAgentProcessor(claim)
        processor.push_frame = AsyncMock()
        await processor.process_frame(TranscriptionFrame(text="I had a bike accident"), FrameDirection.DOWNSTREAM)
        await asyncio.sleep(0.15)
        await processor.process_frame(TranscriptionFrame(text="yesterday in Bengaluru"), FrameDirection.DOWNSTREAM)
        await asyncio.sleep(0.70)
        process_turn.assert_awaited_once_with(processor._db, claim, "I had a bike accident yesterday in Bengaluru", "voice")
        emitted = [call.args[0] for call in processor.push_frame.await_args_list]
        assert any(isinstance(item, OutputTransportMessageFrame) and item.message["type"] == "state_update" for item in emitted)
        await processor.cleanup()
