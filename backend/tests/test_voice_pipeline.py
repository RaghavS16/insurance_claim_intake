"""
Unit tests for Review 1 Voice Processing Pipeline:
- WebRTC VAD (frame generator & utterance segmenter)
- Faster-Whisper STT (WAV wrapping & silence handling)
- Piper TTS (error handling & parameter validation)
- VoiceSession state
"""
import pytest
from src.voice.vad import UtteranceSegmenter, frame_generator, FRAME_BYTES, SAMPLE_RATE
from src.voice.stt import _pcm16_to_wav_bytes, transcribe_pcm16
from src.voice.tts import synthesize, TTSError
from src.voice.session import VoiceSession


class TestVAD:
    def test_frame_generator_exact_chunks(self):
        # 30ms at 16kHz mono 16-bit = 960 bytes per frame
        audio = b"\x00" * (FRAME_BYTES * 3)
        frames = list(frame_generator(audio))
        assert len(frames) == 3
        for f in frames:
            assert len(f.bytes) == FRAME_BYTES
            assert f.duration == 0.03

    def test_utterance_segmenter_empty_chunk(self):
        segmenter = UtteranceSegmenter(aggressiveness=1)
        utterances = segmenter.feed(b"")
        assert utterances == []
        assert segmenter.flush() is None

    def test_utterance_segmenter_silence_does_not_trigger(self):
        segmenter = UtteranceSegmenter(aggressiveness=1)
        silence = b"\x00" * (SAMPLE_RATE * 2)
        utterances = segmenter.feed(silence)
        assert utterances == []


class TestSTT:
    def test_pcm16_to_wav_bytes_header(self):
        pcm = b"\x00\x00" * 100
        wav = _pcm16_to_wav_bytes(pcm, sample_rate=16000)
        assert wav.startswith(b"RIFF")
        assert b"WAVE" in wav
        assert len(wav) == len(pcm) + 44  # standard 44-byte WAV header

    def test_transcribe_pcm16_too_short_returns_empty(self):
        short_pcm = b"\x00" * 100
        result = transcribe_pcm16(short_pcm)
        assert result == ""


class TestTTS:
    def test_synthesize_empty_text_raises_error(self):
        with pytest.raises(TTSError, match="Cannot synthesize empty text"):
            synthesize("   ")

    def test_synthesize_missing_model_raises_error(self, monkeypatch):
        monkeypatch.delenv("PIPER_VOICE_MODEL", raising=False)
        with pytest.raises(TTSError, match="PIPER_VOICE_MODEL"):
            synthesize("Hello world")


class TestVoiceSession:
    def test_turn_increment(self):
        session = VoiceSession(ticket_id="CLAIM-12345678")
        assert session.turn_number == 0
        assert session.next_turn() == 1
        assert session.next_turn() == 2
        assert session.ticket_id == "CLAIM-12345678"
