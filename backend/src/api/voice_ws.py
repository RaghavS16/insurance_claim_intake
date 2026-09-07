"""Compatibility shim for the Pipecat voice implementation.

The legacy hand-built voice workers were removed. Existing imports continue to
resolve while the actual WebSocket endpoint lives in ``pipecat_voice_ws``.
"""

from src.agents.turn_processor import process_claimant_turn
from src.api.pipecat_voice_ws import router

__all__ = ["process_claimant_turn", "router"]
