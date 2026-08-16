"""
Per-connection voice session state. Holds the UtteranceSegmenter for the life
of a WebSocket connection — deliberately NOT persisted to DB (it's just audio
buffering state), unlike ClaimState which lives in claims.pipeline_state.
"""
from dataclasses import dataclass, field

from src.voice.vad import UtteranceSegmenter


@dataclass
class VoiceSession:
    ticket_id: str
    segmenter: UtteranceSegmenter = field(default_factory=UtteranceSegmenter)
    turn_number: int = 0

    def next_turn(self) -> int:
        self.turn_number += 1
        return self.turn_number
