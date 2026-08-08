"""
Test configuration.

Uses a temporary SQLite database (file-based, unique per pytest session) so
tests are fully self-contained and do NOT require a running PostgreSQL instance.
Seed data (policies XYZ123/HOME456/AUTO789, all four adjusters) is inserted
once per test session.

R1-6: Previously all tests shared a SINGLE SQLite file on disk ('test_claims.db')
with no reset between runs — tests were order-dependent. This version:
  - Uses a temp file named after the pytest session (unique per run via a UUID suffix),
    so multiple parallel pytest processes don't collide.
  - Cleans up the temp file after the session.
  - The 'module'-scoped client fixture is retained for speed (avoids re-seeding
    between test files in the same module), but the DB is fresh each full run.

Why not sqlite:///:memory:?
  SQLite in-memory databases are connection-scoped. When FastAPI's get_db()
  yields a Session from a *different* engine (the one in session.py that was
  loaded before the override), it sees an empty schema. A temp file avoids
  this by letting all connections share the same on-disk state regardless of
  which engine/connection created it.
"""
import os
import uuid
import tempfile
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ------------------------------------------------------------------
# 1. Create a temporary SQLite file unique to this test session and
#    set DATABASE_URL *before* importing the app so session.py picks
#    it up correctly.
# ------------------------------------------------------------------
_tmp_db_path = Path(tempfile.gettempdir()) / f"test_claims_{uuid.uuid4().hex[:8]}.db"
SQLITE_URL = f"sqlite:///{_tmp_db_path}"
os.environ["DATABASE_URL"] = SQLITE_URL

# ------------------------------------------------------------------
# 2. Import app + ORM pieces AFTER the env override.
# ------------------------------------------------------------------
from src.api.main import app  # noqa: E402
from src.database.models import Base, Policy, Adjuster  # noqa: E402
from src.database.session import get_db, engine as app_engine  # noqa: E402

# ------------------------------------------------------------------
# 3. Create tables using the same engine that the app will use.
#    This guarantees the schema the app sees is the one we just created.
# ------------------------------------------------------------------
Base.metadata.create_all(bind=app_engine)
TestingSessionLocal = sessionmaker(bind=app_engine, autoflush=False, autocommit=False)


def _seed_db(db):
    """Insert canonical seed rows; idempotent (checks before inserting)."""
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

    # R4-7: HOME456 now in all three seed sources (schema.sql, seed.sql, conftest.py).
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


# ------------------------------------------------------------------
# 4. Override get_db dependency to use the same session factory.
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
@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """
    Session-scoped: seed DB once before any tests run, clean up the
    temp DB file after the entire session completes.
    """
    db = TestingSessionLocal()
    _seed_db(db)
    db.close()
    yield
    # Cleanup after session
    try:
        _tmp_db_path.unlink(missing_ok=True)
    except Exception:
        pass


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c