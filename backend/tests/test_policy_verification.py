from datetime import date
import pytest
from src.agents.policy_check import verify_policy_for_claim

def test_verify_policy_no_policy_id(client):
    from src.database.session import TestingSessionLocal
    db = TestingSessionLocal()
    res = verify_policy_for_claim(None, "2024-05-05", "user1", db)
    assert not res["valid"]
    assert res["reason"] == "no_policy_id"
    db.close()

def test_verify_policy_not_found(client):
    from src.database.session import TestingSessionLocal
    db = TestingSessionLocal()
    res = verify_policy_for_claim("MISSING", "2024-05-05", "user1", db)
    assert not res["valid"]
    assert res["reason"] == "policy_not_found"
    db.close()

def test_verify_policy_ownership_mismatch(client):
    from src.database.session import TestingSessionLocal
    db = TestingSessionLocal()
    res = verify_policy_for_claim("XYZ123", "2024-05-05", "wrong_user", db)
    assert not res["valid"]
    assert res["reason"] == "ownership_mismatch"
    db.close()

def test_verify_policy_missing_event_date(client):
    from src.database.session import TestingSessionLocal
    db = TestingSessionLocal()
    res = verify_policy_for_claim("XYZ123", None, "00000000-0000-0000-0000-000000000001", db)
    assert not res["valid"]
    assert res["reason"] == "missing_event_date"
    db.close()

def test_verify_policy_invalid_event_date(client):
    from src.database.session import TestingSessionLocal
    db = TestingSessionLocal()
    res = verify_policy_for_claim("XYZ123", "not-a-date", "00000000-0000-0000-0000-000000000001", db)
    assert not res["valid"]
    assert res["reason"] == "invalid_event_date"
    db.close()

def test_verify_policy_not_active_on_event_date(client):
    from src.database.session import TestingSessionLocal
    db = TestingSessionLocal()
    res = verify_policy_for_claim("XYZ123", "2020-05-05", "00000000-0000-0000-0000-000000000001", db)
    assert not res["valid"]
    assert res["reason"] == "policy_not_active_on_event_date"
    db.close()

def test_verify_policy_valid(client):
    from src.database.session import TestingSessionLocal
    db = TestingSessionLocal()
    res = verify_policy_for_claim("XYZ123", "2025-05-05", "00000000-0000-0000-0000-000000000001", db)
    assert res["valid"]
    assert res["reason"] is None
    db.close()
