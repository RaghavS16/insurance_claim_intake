"""Tests for grounded semantic extraction helpers."""
from datetime import date, timedelta

from src.agents import nodes


def test_confirmation_summary_is_grounded_and_not_transcript_length():
    text = nodes._confirmation_summary({
        "insurance_type": "motor",
        "event_date": "2026-09-07",
        "event_location": "Chennai",
        "estimated_claim_amount": 12000,
        "policy_id": "XYZ123",
        "event_description": "My bike was damaged in an accident",
    })
    assert "XYZ123" in text
    assert "Chennai" in text
    assert "12,000" in text
    assert len(text.split()) < 40
