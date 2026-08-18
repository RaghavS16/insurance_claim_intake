from datetime import date
import pytest
import uuid
from src.agents.policy_check import verify_policy_for_claim

def test_verify_policy_no_policy_id(db):
    res = verify_policy_for_claim(None, "2024-05-05", "user1", db)
    assert not res["valid"]
    assert res["reason"] == "no_policy_id"

def test_verify_policy_not_found(db):
    res = verify_policy_for_claim("MISSING", "2024-05-05", "user1", db)
    assert not res["valid"]
    assert res["reason"] == "policy_not_found"

def test_verify_policy_ownership_mismatch(db):
    res = verify_policy_for_claim("EXP-0001", "2024-05-05", "user1", db)
    assert not res["valid"]
    assert res["reason"] == "ownership_mismatch"

def test_verify_policy_missing_event_date(db):
    res = verify_policy_for_claim("XYZ123", None, "TEST_USER_ID", db)
    assert not res["valid"]
    assert res["reason"] == "missing_event_date"

def test_verify_policy_invalid_event_date(db):
    res = verify_policy_for_claim("XYZ123", "2024-13-45", "TEST_USER_ID", db)
    assert not res["valid"]
    assert res["reason"] == "invalid_event_date"

def test_verify_policy_inactive(db):
    res = verify_policy_for_claim("EXP-0001", "2021-05-05", str(uuid.uuid4()), db)
    assert not res["valid"]
    assert res["reason"] == "ownership_mismatch"

def test_verify_policy_not_active_on_event_date(db):
    res = verify_policy_for_claim("XYZ123", "2023-05-05", "TEST_USER_ID", db)
    assert not res["valid"]
    assert res["reason"] == "policy_not_active_on_event_date"

def test_verify_policy_valid(db):
    res = verify_policy_for_claim("XYZ123", "2025-05-05", "TEST_USER_ID", db)
    assert res["valid"]
    assert res["reason"] is None
