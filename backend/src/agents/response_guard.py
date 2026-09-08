"""Safety gate for natural, model-authored conversational replies.

The extraction model may suggest a short spoken reply. This module only allows it
when it is clearly grounded in the already-normalized claim state; otherwise the
existing deterministic next-question planner remains authoritative.
"""
from __future__ import annotations

import re
from typing import Any


_FIELD_TOKENS = {
    "policy_id": r"policy|polic(?:y|ies)|number|id",
    "event_date": r"date|day|yesterday|today|tomorrow",
    "insurance_type": r"insurance|motor|health|travel|home|cyber",
    "event_description": r"happened|incident|accident|damage|injur|lost|stolen|claim",
    "event_location": r"where|location|place|city|area",
    "estimated_claim_amount": r"amount|cost|loss|damage|₹|rs\.?|rupees|inr",
}


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\b\d[\d,]*(?:\.\d+)?\b", text))


def _has_unsupported_numbers(reply: str, state: dict[str, Any]) -> bool:
    allowed_text = " ".join(str(v) for v in (state.get("extracted_data") or {}).values())
    allowed = _numbers(allowed_text)
    return bool(_numbers(reply) - allowed)


def _is_grounded(reply: str, state: dict[str, Any]) -> bool:
    text = " ".join(reply.split()).strip()
    if not text or len(text) < 8 or len(text.split()) > 32:
        return False
    if "\n" in reply or any(ch in reply for ch in ("•", "```", "<", ">")):
        return False
    if _has_unsupported_numbers(text, state):
        return False

    latest = str(state.get("last_user_utterance") or "").lower()
    known = state.get("extracted_data") or {}
    # A short acknowledgement/question is safe when it refers to the latest
    # utterance, a known field, or a normal intake action.
    if latest and any(word in text.lower() for word in latest.split() if len(word) >= 5):
        return True
    if any(re.search(pattern, text, re.I) for pattern in _FIELD_TOKENS.values()):
        return True
    if known and any(phrase in text.lower() for phrase in ("got it", "thanks", "tell me", "could you", "can you", "what", "which", "please")):
        return True
    return False


def safe_spoken_reply(state: dict[str, Any]) -> str | None:
    """Return the model reply only when it passes grounding and voice-style checks."""
    candidate = str(state.get("spoken_response") or "").strip()
    if _is_grounded(candidate, state):
        return " ".join(candidate.split())
    return None
