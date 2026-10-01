"""Compatibility module; production voice transport is WebRTC + managed realtime."""
from src.agents.turn_processor import process_claimant_turn
from src.api.realtime_voice import router
__all__ = ["router", "process_claimant_turn"]
