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
    tts_cls.assert_called_once_with(base_url="http://localhost:5000", voice="en_US-lessac-medium")
    transport.input.assert_called_once()
    transport.output.assert_called_once()


def test_websocket_transport_uses_legacy_pcm_contract():
    websocket = MagicMock()
    transport = websocket_transport(websocket)
    assert transport is not None
    assert transport._params.audio_in_enabled is True
    assert transport._params.audio_out_enabled is True


def test_pipeline_uses_native_piper_when_model_exists():
    claim = MagicMock()
    transport = MagicMock()
    transport.input.return_value = MagicMock(name="input")
    transport.output.return_value = MagicMock(name="output")

    with patch("src.voice.pipecat.WhisperSTTService") as stt_cls, patch(
        "src.voice.pipecat.PiperNativeTTSService"
    ) as native_tts_cls, patch("src.voice.pipecat._find_piper_model_path", return_value="piper/en_US-ryan-medium.onnx"):
        worker = build_voice_pipeline(
            transport,
            claim,
            stt_model="small",
            piper_model_path="piper/en_US-ryan-medium.onnx",
        )

    assert worker is not None
    stt_cls.assert_called_once()
    native_tts_cls.assert_called_once_with(model_path="piper/en_US-ryan-medium.onnx")


def test_llm_factory_instantiates_configured_provider():
    from langchain_ollama import ChatOllama
    from langchain_openai import ChatOpenAI
    from src.agents.llm_factory import get_configured_llm
    from src.config import settings

    with patch.object(settings, "LLM_PROVIDER", "ollama"), patch.object(settings, "OLLAMA_MODEL", "qwen2.5:7b"):
        llm = get_configured_llm()
        assert isinstance(llm, ChatOllama)
        assert getattr(llm, "model", "") == "qwen2.5:7b"

    with patch.object(settings, "LLM_PROVIDER", "cloud"), patch.object(settings, "CLOUD_LLM_MODEL", "Qwen/Qwen3.5-27B"), patch.object(settings, "CLOUD_LLM_API_KEY", "test-key"), patch.object(settings, "CLOUD_LLM_BASE_URL", "https://openrouter.ai/api/v1"):
        cloud_llm = get_configured_llm()
        assert isinstance(cloud_llm, ChatOpenAI)
        assert getattr(cloud_llm, "model_name", "") == "Qwen/Qwen3.5-27B"
