"""Deprecated compatibility module for the removed in-app audio pipeline."""
from src.api.realtime_voice import router as managed_voice_router
__all__ = ["managed_voice_router"]
