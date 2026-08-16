"""
Voice Activity Detection using WebRTC VAD (Google's open-source, BSD-licensed
VAD via the `webrtcvad` Python binding). Chosen over ML-based VAD (e.g.
silero-vad) for Review 1 because it's CPU-only, dependency-light, and more
than sufficient for detecting end-of-utterance in a turn-based conversation —
we don't need barge-in/overlap detection for Review 1's UX.

Frame requirements are strict: webrtcvad only accepts 16-bit mono PCM at
8000/16000/32000/48000 Hz, in 10/20/30ms frames. faster-whisper also wants
16kHz mono, so we standardize the whole voice pipeline on 16kHz.
"""
import collections
from typing import Generator, List

import webrtcvad

SAMPLE_RATE = 16000
FRAME_DURATION_MS = 30          # 10, 20, or 30 only
FRAME_BYTES = int(SAMPLE_RATE * (FRAME_DURATION_MS / 1000.0) * 2)  # 16-bit = 2 bytes/sample

# How many consecutive silent frames end an utterance. 800ms of natural silence.
SILENCE_FRAMES_TO_END = int(800 / FRAME_DURATION_MS)  # ~26 frames
# Ring buffer size for the "is this actually speech starting" check (300ms).
START_PADDING_FRAMES = 10


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


class UtteranceSegmenter:
    """
    Stateful segmenter: feed it audio chunks as they arrive from the
    WebSocket, it buffers, runs VAD frame-by-frame, and yields complete
    utterances (as raw PCM16 bytes) once it detects ~800ms of trailing
    silence after speech has started.

    Aggressiveness 0-3 (3 = most aggressive at filtering non-speech).
    1 or 2 is a reasonable default: filters background noise without cutting
    off quiet speech.
    """

    def __init__(self, aggressiveness: int = 1):
        self._vad = webrtcvad.Vad(aggressiveness)
        self._start_ring: collections.deque = collections.deque(maxlen=START_PADDING_FRAMES)
        self._end_ring: collections.deque = collections.deque(maxlen=SILENCE_FRAMES_TO_END)
        self._triggered = False
        self._voiced_frames: List[Frame] = []
        self._leftover = b""  # bytes that didn't fill a complete frame yet

    def feed(self, chunk: bytes) -> List[bytes]:
        """
        Feed raw PCM16 bytes (any chunk size). Returns a list of completed
        utterances (usually 0 or 1) as raw PCM16 bytes ready for STT.
        """
        self._leftover += chunk
        completed_utterances: List[bytes] = []

        # Consume as many complete frames as we have bytes for.
        frames = list(frame_generator(self._leftover))
        if frames:
            consumed = len(frames) * FRAME_BYTES
            self._leftover = self._leftover[consumed:]

        for frame in frames:
            is_speech = self._vad.is_speech(frame.bytes, SAMPLE_RATE)

            if not self._triggered:
                self._start_ring.append((frame, is_speech))
                num_voiced = len([f for f, speech in self._start_ring if speech])
                # Start of an utterance: 80% of start ring buffer is voiced
                if num_voiced >= int(0.8 * START_PADDING_FRAMES):
                    self._triggered = True
                    self._voiced_frames.extend(f for f, _ in self._start_ring)
                    self._start_ring.clear()
                    self._end_ring.clear()
            else:
                self._voiced_frames.append(frame)
                self._end_ring.append((frame, is_speech))
                num_unvoiced = len([f for f, speech in self._end_ring if not speech])
                # End of utterance: full silence window (~800ms) is unvoiced
                if len(self._end_ring) == SILENCE_FRAMES_TO_END and num_unvoiced >= int(0.9 * SILENCE_FRAMES_TO_END):
                    utterance_bytes = b"".join(f.bytes for f in self._voiced_frames)
                    completed_utterances.append(utterance_bytes)
                    self._triggered = False
                    self._voiced_frames = []
                    self._end_ring.clear()
                    self._start_ring.clear()

        return completed_utterances

    def flush(self) -> bytes | None:
        """Call on connection close to grab any in-progress utterance."""
        if self._triggered and self._voiced_frames:
            utterance_bytes = b"".join(f.bytes for f in self._voiced_frames)
            self._triggered = False
            self._voiced_frames = []
            return utterance_bytes
        return None
