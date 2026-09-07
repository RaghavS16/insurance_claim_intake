"""Unit tests for the Pipecat voice adapters and insurance-agent bridge."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pipecat.frames.frames import (
    InterruptionFrame,
    OutputAudioRawFrame,
    OutputTransportMessageFrame,
    TranscriptionFrame,
)
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
        db = MagicMock()
        session_factory.return_value = db
        processor = ClaimAgentProcessor(claim)
        processor.push_frame = AsyncMock()

        frame = InterruptionFrame()
        await processor.process_frame(frame, FrameDirection.DOWNSTREAM)

        messages = [call.args[0] for call in processor.push_frame.await_args_list]
        assert any(isinstance(item, OutputTransportMessageFrame) and item.message["type"] == "barge_in" for item in messages)
        assert any(isinstance(item, InterruptionFrame) for item in messages)


@pytest.mark.asyncio
async def test_claim_agent_processor_delegates_final_transcript():
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
        processor = ClaimAgentProcessor(claim)
        processor.push_frame = AsyncMock()
        await processor.process_frame(TranscriptionFrame(text="It was a car accident."), FrameDirection.DOWNSTREAM)

        process_turn.assert_awaited_once()
        emitted = [call.args[0] for call in processor.push_frame.await_args_list]
        assert any(isinstance(item, OutputTransportMessageFrame) and item.message["type"] == "state_update" for item in emitted)
