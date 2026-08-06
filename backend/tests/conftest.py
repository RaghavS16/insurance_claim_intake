"""
Test configuration.

Uses an in-memory SQLite database so tests are fully self-contained and do NOT
require a running PostgreSQL instance.  Seed data (policy XYZ123, adjusters)
is inserted once per test session so the integration tests can pass without
external infrastructure.
"""
import os
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ------------------------------------------------------------------
# 1. Point DATABASE_URL at SQLite *before* importing the app so that
#    session.py picks up the override.
# ------------------------------------------------------------------
SQLITE_URL = "sqlite:///./test_claims.db"
os.environ["DATABASE_URL"] = SQLITE_URL

# ------------------------------------------------------------------
# 2. Import app + ORM pieces AFTER the env override.
# ------------------------------------------------------------------
from src.api.main import app  # noqa: E402
from src.database.models import Base, Policy, Adjuster  # noqa: E402
from src.database.session import get_db  # noqa: E402

# ------------------------------------------------------------------
# 3. Create the SQLite engine + tables.
# ------------------------------------------------------------------
engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},  # needed for SQLite + threading
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base.metadata.create_all(bind=engine)


def _seed_db(db):
    """Insert seed rows only when they don't already exist."""
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
                is_active=True,
            ))

    db.commit()


# ------------------------------------------------------------------
# 4. Override get_db dependency with the SQLite session.
# ------------------------------------------------------------------
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


# ------------------------------------------------------------------
# 5. Fixtures
# ------------------------------------------------------------------
@pytest.fixture(scope="module")
def client():
    db = TestingSessionLocal()
    _seed_db(db)
    db.close()
    with TestClient(app) as c:
        yield c