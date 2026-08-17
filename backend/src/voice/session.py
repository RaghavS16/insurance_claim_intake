"""
Per-connection voice session state.

Holds per-WebSocket-connection state for the duration of a voice session:
  - Sequence counter for transcript segments (claimant and agent tracked separately)
  - Echo-suppression flag: True while the agent TTS audio is playing on the client,
    allowing the ASR worker to discard mic audio that is likely TTS echo.
  - Turn counter (for conversation turn persistence)

This state is NOT persisted to the database — it only lives for the WebSocket lifetime.
"""
import time
from dataclasses import dataclass, field
from typing import Optional

from src.voice.vad import SpeechEndpointDetector, UtteranceSegmenter


@dataclass
class VoiceSession:
    ticket_id: str
    # Legacy segmenter — kept for backward compatibility, not used by new pipeline
    segmenter: UtteranceSegmenter = field(default_factory=UtteranceSegmenter)
    turn_number: int = 0

    # Separate sequence counters for claimant and agent transcript segments
    _claimant_seq: int = field(default=0, repr=False)
    _agent_seq: int = field(default=0, repr=False)

    # Echo-suppression: set to a future monotonic timestamp (time.monotonic() + duration)
    # while agent TTS is believed to be playing. The ASR worker skips mic audio until
    # this timestamp is exceeded.
    _echo_suppress_until: float = field(default=0.0, repr=False)

    def next_turn(self) -> int:
        self.turn_number += 1
        return self.turn_number

    def next_claimant_segment_id(self) -> tuple[str, int]:
        """Return (segment_id, sequence_number) for a new claimant transcript segment."""
        self._claimant_seq += 1
        return f"claimant-{self._claimant_seq}", self._claimant_seq

    def next_agent_segment_id(self) -> tuple[str, int]:
        """Return (segment_id, sequence_number) for a new agent transcript segment."""
        self._agent_seq += 1
        return f"agent-{self._agent_seq}", self._agent_seq

    def suppress_echo_for(self, duration_seconds: float) -> None:
        """
        Signal that agent TTS will be playing for approximately `duration_seconds`.
        The ASR worker should discard claimant mic audio until the suppression window expires.
        """
        self._echo_suppress_until = time.monotonic() + duration_seconds

    def is_echo_suppressed(self) -> bool:
        """Returns True if we are currently within the echo-suppression window."""
        return time.monotonic() < self._echo_suppress_until

    def clear_echo_suppression(self) -> None:
        """Immediately clear echo suppression (e.g., when claimant interrupts)."""
        self._echo_suppress_until = 0.0
