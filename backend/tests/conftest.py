"""
Pytest configuration and test database fixtures.

Sets up a temporary SQLite database per test session, seeds canonical policies
and adjusters, and configures fast mock fallbacks for LLM calls during unit tests.
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

# 2. Import application models and session
from src.api.main import app  # noqa: E402
from src.database.models import Base, Policy, Adjuster  # noqa: E402
from src.database.session import get_db, engine as app_engine  # noqa: E402

# 3. Create tables using the test engine
Base.metadata.create_all(bind=app_engine)
TestingSessionLocal = sessionmaker(bind=app_engine, autoflush=False, autocommit=False)


def _seed_db(db):
    """Insert canonical test policies and adjusters."""
    if db.query(Policy).filter(Policy.policy_number == "XYZ123").first() is None:
        db.add(Policy(
            id=str(uuid.uuid4()),
            policy_number="XYZ123",
            customer_id=str(uuid.uuid4()),
            policy_type="auto",
            coverage_amount=500000,
            deductible=10000,
            effective_date=date(2024, 1, 1),
            expiry_date=date(2030, 12, 31),
            is_active=True,
        ))

    if db.query(Policy).filter(Policy.policy_number == "HOME456").first() is None:
        db.add(Policy(
            id=str(uuid.uuid4()),
            policy_number="HOME456",
            customer_id=str(uuid.uuid4()),
            policy_type="home",
            coverage_amount=1000000,
            deductible=10000,
            effective_date=date(2025, 3, 1),
            expiry_date=date(2026, 2, 28),
            is_active=True,
        ))

    if db.query(Policy).filter(Policy.policy_number == "AUTO789").first() is None:
        db.add(Policy(
            id=str(uuid.uuid4()),
            policy_number="AUTO789",
            customer_id=str(uuid.uuid4()),
            policy_type="auto",
            coverage_amount=300000,
            deductible=5000,
            effective_date=date(2020, 1, 1),
            expiry_date=date(2022, 12, 31),
            is_active=False,
        ))

    for spec, name, email in [
        ("auto",     "Priya Sharma",   "priya@insure.co"),
        ("home",     "Rohan Mehta",    "rohan@insure.co"),
        ("business", "Anjali Gupta",   "anjali@insure.co"),
        ("complex",  "Complex Review", "complex@insure.co"),
    ]:
        if db.query(Adjuster).filter(Adjuster.email == email).first() is None:
            db.add(Adjuster(
                id=str(uuid.uuid4()),
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


@pytest.fixture(autouse=True)
def mock_offline_llm(monkeypatch):
    """
    By default in unit tests, mock ChatOllama.invoke to trigger deterministic fallback extraction.
    Prevents 10s timeout delays when Ollama is offline.
    """
    def mock_invoke(self, prompt, *args, **kwargs):
        raise ConnectionError("Ollama offline in test runner")

    monkeypatch.setattr(ChatOllama, "invoke", mock_invoke)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c