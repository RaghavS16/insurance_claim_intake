"""Compatibility export for the canonical conversation turn processor.

Confirmation is intentionally not inferred here. The graph records a pending
confirmation state; only an explicit claimant confirmation followed by the
verification/submission API can advance the claim.
"""
from src.agents.nodes import conversation_turn_processor

__all__ = ["conversation_turn_processor"]
