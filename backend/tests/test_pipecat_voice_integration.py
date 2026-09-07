"""Integration-level construction tests for the Pipecat insurance pipeline."""

from unittest.mock import MagicMock, patch

from src.voice.pipecat import build_voice_pipeline, websocket_transport


def test_pipeline_contains_transport_vad_stt_agent_and_tts():
    claim = MagicMock()
    transport = MagicMock()
    transport.input.return_value = MagicMock(name="input")
    transport.output.return_value = MagicMock(name="output")

    with patch("src.voice.pipecat.WhisperSTTService") as stt_cls, patch(
        "src.voice.pipecat.PiperHTTPService"
    ) as tts_cls:
        worker = build_voice_pipeline(
            transport,
            claim,
            stt_model="small",
            vad_aggressiveness=1,
            piper_url="http://localhost:5000",
        )

    assert worker is not None
    stt_cls.assert_called_once()
    tts_cls.assert_called_once_with(base_url="http://localhost:5000", voice=None)
    transport.input.assert_called_once()
    transport.output.assert_called_once()


def test_websocket_transport_uses_legacy_pcm_contract():
    websocket = MagicMock()
    transport = websocket_transport(websocket)
    assert transport is not None
    assert transport._params.audio_in_enabled is True
    assert transport._params.audio_out_enabled is True
