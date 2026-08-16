"""
Voice Activity Detection using WebRTC VAD (Google's open-source, BSD-licensed
VAD via the `webrtcvad` Python binding). Standardized on 16kHz mono audio.
"""
import collections
from typing import Generator, List

import webrtcvad

SAMPLE_RATE = 16000
FRAME_DURATION_MS = 30          # 10, 20, or 30 only
FRAME_BYTES = int(SAMPLE_RATE * (FRAME_DURATION_MS / 1000.0) * 2)  # 16-bit = 2 bytes/sample

# Give user 1400ms of natural silence before finalizing utterance (prevents interrupting pauses)
SILENCE_FRAMES_TO_END = int(1400 / FRAME_DURATION_MS)  # ~46 frames
# Ring buffer size for speech onset detection (300ms)
START_PADDING_FRAMES = 10
# Minimum speech duration to filter out clicks, coughs, and breath noise (450ms)
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


class UtteranceSegmenter:
    """
    Stateful segmenter: buffers incoming chunks, tracks voiced activity,
    and yields complete utterances only after user has finished speaking
    (1400ms trailing silence with minimum 450ms speech duration).
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
        Feed raw PCM16 bytes. Returns completed full utterances ready for STT.
        """
        self._leftover += chunk
        completed_utterances: List[bytes] = []

        # Consume complete frames
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
                # End of utterance: full silence window (~1400ms) is unvoiced
                if len(self._end_ring) == SILENCE_FRAMES_TO_END and num_unvoiced >= int(0.9 * SILENCE_FRAMES_TO_END):
                    if len(self._voiced_frames) >= MIN_SPEECH_FRAMES:
                        utterance_bytes = b"".join(f.bytes for f in self._voiced_frames)
                        completed_utterances.append(utterance_bytes)
                    self._triggered = False
                    self._voiced_frames = []
                    self._end_ring.clear()
                    self._start_ring.clear()

        return completed_utterances

    def flush(self) -> bytes | None:
        """Call on connection close to grab any in-progress utterance."""
        if self._triggered and len(self._voiced_frames) >= MIN_SPEECH_FRAMES:
            utterance_bytes = b"".join(f.bytes for f in self._voiced_frames)
            self._triggered = False
            self._voiced_frames = []
            return utterance_bytes
        return None
