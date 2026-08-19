"""
Pytest configuration and test database fixtures for Phase 1.

Sets up an isolated temporary SQLite database per test session, seeds canonical policies
and adjusters for all 6 supported insurance types, and configures mock fallbacks.
"""
import os
import uuid
import tempfile
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_ollama import ChatOllama
from sqlalchemy.orm import sessionmaker

# 1. Setup isolated temporary SQLite test database
_tmp_db_path = Path(tempfile.gettempdir()) / f"test_claims_{uuid.uuid4().hex[:8]}.db"
SQLITE_URL = f"sqlite:///{_tmp_db_path}"
os.environ["DATABASE_URL"] = SQLITE_URL
os.environ["ENVIRONMENT"] = "test"

# 2. Import application models and session
from src.config import settings  # noqa: E402
from src.api.main import app  # noqa: E402
from src.database.models import Base, Policy, Adjuster, User  # noqa: E402
from src.database.session import get_db, engine as app_engine  # noqa: E402
from src.utils.auth import get_password_hash  # noqa: E402

# 3. Create tables using the test engine
Base.metadata.create_all(bind=app_engine)
TestingSessionLocal = sessionmaker(bind=app_engine, autoflush=False, autocommit=False)


def _seed_db(db):
    """Insert canonical test policies and adjusters for the 6 supported insurance types."""
    test_policies = [
        ("XYZ123", "motor", 500000, 10000, date(2024, 1, 1), date(2030, 12, 31), True),
        ("MOT-5521", "motor", 500000, 5000, date(2024, 1, 1), date(2030, 12, 31), True),
        ("HOME456", "home", 1000000, 10000, date(2025, 3, 1), date(2026, 2, 28), True),
        ("HLT-7789", "health", 800000, 2000, date(2024, 6, 1), date(2026, 5, 31), True),
        ("SNR-9912", "senior_health", 600000, 3000, date(2024, 1, 1), date(2027, 12, 31), True),
        ("TRV-3301", "travel", 200000, 1000, date(2025, 1, 1), date(2025, 12, 31), True),
        ("CYB-8820", "cyber", 1500000, 15000, date(2024, 1, 1), date(2026, 12, 31), True),
        ("EXP-0001", "motor", 300000, 5000, date(2020, 1, 1), date(2022, 12, 31), False),
    ]

    claimant_id = "TEST_USER_ID"
    if not db.query(User).filter(User.id == claimant_id).first():
        db.add(User(
            id=claimant_id,
            full_name="Test Claimant",
            email="claimant@test.com",
            password_hash=get_password_hash("password123"),
            role="CLAIMANT",
            status="active"
        ))

    admin_id = "TEST_ADMIN_ID"
    if not db.query(User).filter(User.id == admin_id).first():
        db.add(User(
            id=admin_id,
            full_name="Test Admin",
            email="admin@test.com",
            password_hash=get_password_hash("AdminPassword123!"),
            role="ADMIN",
            status="active"
        ))

    for pol_num, ptype, cov, ded, eff, exp, active in test_policies:
        if db.query(Policy).filter(Policy.policy_number == pol_num).first() is None:
            c_id = claimant_id if pol_num == "XYZ123" else (None if pol_num == "MOT-5521" else str(uuid.uuid4()))
            db.add(Policy(
                id=str(uuid.uuid4()),
                policy_number=pol_num,
                customer_id=c_id,
                policy_type=ptype,
                coverage_amount=cov,
                deductible=ded,
                effective_date=eff,
                expiry_date=exp,
                is_active=active,
                policyholder_name="Test Policyholder",
                policyholder_dob=date(1990, 5, 15),
                policyholder_phone_last4="1234",
                link_attempts=0,
            ))

    test_adjusters = [
        ("motor",         "Priya Sharma",   "priya@insure.co"),
        ("home",          "Rohan Mehta",    "rohan@insure.co"),
        ("health",        "Dr. Anita Roy",  "anita@insure.co"),
        ("senior_health", "Dr. V. Rao",     "rao@insure.co"),
        ("travel",        "Vikram Sen",     "vikram@insure.co"),
        ("cyber",         "Neha Kapoor",    "neha@insure.co"),
    ]

    for spec, name, email in test_adjusters:
        adj = db.query(Adjuster).filter(Adjuster.email == email).first()
        uid = adj.id if adj else str(uuid.uuid4())
        
        usr = db.query(User).filter(User.email == email).first()
        if not usr:
            db.add(User(
                id=uid,
                full_name=name,
                email=email,
                password_hash=get_password_hash("AdjusterPassword123!"),
                role="ADJUSTER",
                status="active"
            ))
        
        if not adj:
            db.add(Adjuster(
                id=uid,
                name=name,
                email=email,
                specialization=spec,
                claims_assigned=0,
                is_active=True,
            ))

    db.commit()


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Seed test DB before running test suite and clean up temporary SQLite file afterwards."""
    db = TestingSessionLocal()
    _seed_db(db)
    db.close()
    yield
    try:
        _tmp_db_path.unlink(missing_ok=True)
    except Exception:
        pass


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def mock_offline_llm(monkeypatch):
    """
    Mock ChatOllama.invoke to test deterministic rule-based fallback extraction during unit tests.
    """
    def mock_invoke(self, prompt, *args, **kwargs):
        raise ConnectionError("Ollama offline in test runner")

    monkeypatch.setattr(ChatOllama, "invoke", mock_invoke)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c