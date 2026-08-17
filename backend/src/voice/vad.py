"""
Voice Activity Detection using WebRTC VAD (Google's open-source, BSD-licensed
VAD via the `webrtcvad` Python binding). Standardized on 16kHz mono audio.

Two classes are provided:

UtteranceSegmenter — original segmenter kept for backward compatibility with tests.

SpeechEndpointDetector — new preferred class used by the streaming voice pipeline.
  Instead of blocking until a complete utterance is ready, it emits (audio_chunk, is_endpoint)
  tuples continuously. The ASR worker consumes these to build progressive partial transcripts.

  Silence threshold is configurable via settings.VAD_SILENCE_MS (default 800ms).
"""
import collections
import math
import struct
from typing import Generator, List, Optional, Tuple

import webrtcvad

from src.config import settings

SAMPLE_RATE = 16000
FRAME_DURATION_MS = 30          # 10, 20, or 30 ms only — WebRTC VAD constraint
FRAME_BYTES = int(SAMPLE_RATE * (FRAME_DURATION_MS / 1000.0) * 2)  # 16-bit = 2 bytes/sample

# Legacy constants kept for backward compat with existing tests
SILENCE_FRAMES_TO_END = int(1400 / FRAME_DURATION_MS)  # ~46 frames
START_PADDING_FRAMES = 10
MIN_SPEECH_FRAMES = int(450 / FRAME_DURATION_MS)


class Frame:
    __slots__ = ("bytes", "timestamp", "duration")

    def __init__(self, frame_bytes: bytes, timestamp: float, duration: float):
        self.bytes = frame_bytes
        self.timestamp = timestamp
        self.duration = duration


def frame_generator(audio_bytes: bytes) -> Generator[Frame, None, None]:
    """Slice raw PCM16 mono 16kHz audio into fixed-size VAD frames."""
    offset = 0
    timestamp = 0.0
    duration = FRAME_DURATION_MS / 1000.0
    while offset + FRAME_BYTES <= len(audio_bytes):
        yield Frame(audio_bytes[offset:offset + FRAME_BYTES], timestamp, duration)
        timestamp += duration
        offset += FRAME_BYTES


def calculate_rms(frame_bytes: bytes) -> float:
    """Calculate the Root Mean Square (RMS) energy of a 16-bit PCM mono audio frame."""
    if not frame_bytes:
        return 0.0
    count = len(frame_bytes) // 2
    if count == 0:
        return 0.0
    try:
        samples = struct.unpack(f"<{count}h", frame_bytes)
    except struct.error:
        return 0.0
    sum_squares = sum(s * s for s in samples)
    return math.sqrt(sum_squares / count)


class SpeechEndpointDetector:
    """
    Continuous speech endpoint detector for use in the streaming ASR pipeline.

    Unlike UtteranceSegmenter, this class does NOT block until a complete utterance is
    ready. Instead, it emits (audio_chunk, is_endpoint) pairs on every frame:

      - is_endpoint=False: speech is ongoing, chunk contains the audio accumulated so far.
        The ASR worker may run Whisper on this chunk to produce a partial transcript.
      - is_endpoint=True: silence window expired, chunk contains the complete utterance.
        The ASR worker should produce the final transcript and forward to the conversation
        pipeline. The internal buffer is then reset for the next utterance.

    Audio frames that are purely silent before any speech is detected are discarded.

    Parameters
    ----------
    aggressiveness : int (0-3)
        WebRTC VAD aggressiveness. Higher = more aggressive at filtering non-speech.
    silence_ms : int
        Duration of consecutive silence (ms) before endpoint is declared.
    """

    def __init__(
        self,
        aggressiveness: Optional[int] = None,
        silence_ms: Optional[int] = None,
    ):
        agg = aggressiveness if aggressiveness is not None else settings.VAD_AGGRESSIVENESS
        silence = silence_ms if silence_ms is not None else settings.VAD_SILENCE_MS
        self._vad = webrtcvad.Vad(agg)
        self._silence_frames = int(silence / FRAME_DURATION_MS)
        # Onset ring buffer: must have 80% voiced before entering speech
        self._start_ring: collections.deque = collections.deque(maxlen=10)
        # Silence ring buffer tracks trailing silence
        self._end_ring: collections.deque = collections.deque(maxlen=self._silence_frames)
        self._in_speech = False
        # Accumulated voiced frames for the current utterance
        self._voiced_frames: List[Frame] = []
        self._leftover = b""

    def feed(self, chunk: bytes, tts_active: bool = False) -> List[Tuple[bytes, bool]]:
        """
        Feed raw PCM16 bytes. Returns a list of (audio_chunk, is_endpoint) tuples.

        When is_endpoint is False the chunk is the audio accumulated so far (partial).
        When is_endpoint is True the chunk is the complete finalized utterance.

        Only events from speech-active periods are emitted — silent audio before speech
        onset does not generate any events.
        """
        self._leftover += chunk
        events: List[Tuple[bytes, bool]] = []

        frames = list(frame_generator(self._leftover))
        if frames:
            self._leftover = self._leftover[len(frames) * FRAME_BYTES:]

        for frame in frames:
            rms = calculate_rms(frame.bytes)
            rms_threshold = 350 if tts_active else 150
            is_speech = self._vad.is_speech(frame.bytes, SAMPLE_RATE) and (rms >= rms_threshold)

            if not self._in_speech:
                self._start_ring.append((frame, is_speech))
                voiced_count = sum(1 for _, s in self._start_ring if s)
                assert self._start_ring.maxlen is not None
                onset_threshold = 0.9 if tts_active else 0.8
                if voiced_count >= int(onset_threshold * self._start_ring.maxlen):
                    self._in_speech = True
                    # Include the onset ring buffer to avoid clipping
                    self._voiced_frames.extend(f for f, _ in self._start_ring)
                    self._start_ring.clear()
                    self._end_ring.clear()
            else:
                self._voiced_frames.append(frame)
                self._end_ring.append((frame, is_speech))
                unvoiced_count = sum(1 for _, s in self._end_ring if not s)

                # Endpoint: full silence ring is unvoiced (≥ 90%)
                if (
                    len(self._end_ring) == self._silence_frames
                    and unvoiced_count >= int(0.9 * self._silence_frames)
                ):
                    min_frames = int(200 / FRAME_DURATION_MS)  # 200ms minimum
                    if len(self._voiced_frames) >= min_frames:
                        utterance_bytes = b"".join(f.bytes for f in self._voiced_frames)
                        events.append((utterance_bytes, True))  # final
                    # Reset for next utterance
                    self._in_speech = False
                    self._voiced_frames = []
                    self._end_ring.clear()
                    self._start_ring.clear()

        return events

    def peek_partial(self) -> Optional[bytes]:
        """
        Return the audio accumulated so far without resetting state.
        Used by the ASR worker to get a chunk for a partial transcription.
        Returns None if no speech is currently being tracked.
        """
        if not self._in_speech or not self._voiced_frames:
            return None
        return b"".join(f.bytes for f in self._voiced_frames)

    def flush(self) -> Optional[bytes]:
        """
        Flush any in-progress utterance (called on connection close).
        Returns utterance bytes or None.
        """
        if self._in_speech and len(self._voiced_frames) >= int(200 / FRAME_DURATION_MS):
            utterance_bytes = b"".join(f.bytes for f in self._voiced_frames)
            self._in_speech = False
            self._voiced_frames = []
            return utterance_bytes
        return None

    @property
    def is_in_speech(self) -> bool:
        return self._in_speech


# ---------------------------------------------------------------------------
# UtteranceSegmenter — kept for backward compatibility with existing tests.
# New code should use SpeechEndpointDetector.
# ---------------------------------------------------------------------------
class UtteranceSegmenter:
    """
    Stateful segmenter (legacy): buffers incoming chunks, tracks voiced activity,
    and yields complete utterances only after claimant has finished speaking
    (configurable trailing silence with minimum 450ms speech duration).

    Kept for backward compatibility. New voice pipeline uses SpeechEndpointDetector.
    """

    def __init__(self, aggressiveness: Optional[int] = None):
        agg = aggressiveness if aggressiveness is not None else settings.VAD_AGGRESSIVENESS
        self._vad = webrtcvad.Vad(agg)
        self._start_ring: collections.deque = collections.deque(maxlen=START_PADDING_FRAMES)
        self._end_ring: collections.deque = collections.deque(maxlen=SILENCE_FRAMES_TO_END)
        self._triggered = False
        self._voiced_frames: List[Frame] = []
        self._leftover = b""

    def feed(self, chunk: bytes) -> List[bytes]:
        """Feed raw PCM16 bytes. Returns completed full utterances ready for STT."""
        self._leftover += chunk
        completed_utterances: List[bytes] = []

        frames = list(frame_generator(self._leftover))
        if frames:
            consumed = len(frames) * FRAME_BYTES
            self._leftover = self._leftover[consumed:]

        for frame in frames:
            rms = calculate_rms(frame.bytes)
            is_speech = self._vad.is_speech(frame.bytes, SAMPLE_RATE) and (rms >= 150)

            if not self._triggered:
                self._start_ring.append((frame, is_speech))
                num_voiced = len([f for f, speech in self._start_ring if speech])
                if num_voiced >= int(0.8 * START_PADDING_FRAMES):
                    self._triggered = True
                    self._voiced_frames.extend(f for f, _ in self._start_ring)
                    self._start_ring.clear()
                    self._end_ring.clear()
            else:
                self._voiced_frames.append(frame)
                self._end_ring.append((frame, is_speech))
                num_unvoiced = len([f for f, speech in self._end_ring if not speech])
                if len(self._end_ring) == SILENCE_FRAMES_TO_END and num_unvoiced >= int(0.9 * SILENCE_FRAMES_TO_END):
                    if len(self._voiced_frames) >= MIN_SPEECH_FRAMES:
                        utterance_bytes = b"".join(f.bytes for f in self._voiced_frames)
                        completed_utterances.append(utterance_bytes)
                    self._triggered = False
                    self._voiced_frames = []
                    self._end_ring.clear()
                    self._start_ring.clear()

        return completed_utterances

    def flush(self) -> Optional[bytes]:
        """Call on connection close to grab any in-progress utterance."""
        if self._triggered and len(self._voiced_frames) >= MIN_SPEECH_FRAMES:
            utterance_bytes = b"".join(f.bytes for f in self._voiced_frames)
            self._triggered = False
            self._voiced_frames = []
            return utterance_bytes
        return None
