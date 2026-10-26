import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.main import app
from src.config import settings
from src.database.models import User, Claim, Adjuster, Base
from src.database.hardening_models import Base as HardeningBase, ClaimAssignment
from src.database.session import get_db
from src.utils.auth import create_access_token

@pytest.fixture
def etag_test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "etag_test.db"
    db_url = f"sqlite:///{db_file}"
    monkeypatch.setattr(settings, "DATABASE_URL", db_url)

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    HardeningBase.metadata.create_all(bind=engine)

    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield Session
    app.dependency_overrides.pop(get_db, None)

def test_claimant_claim_etag_and_304(etag_test_db):
    db = etag_test_db()
    tenant_id = "00000000-0000-0000-0000-000000000001"
    user = User(
        full_name="ETag Claimant",
        email="etag_claimant@example.com",
        password_hash="mock_hash",
        role="CLAIMANT",
        tenant_id=tenant_id,
        status="active",
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    claim = Claim(
        ticket_id="CLAIM-ETAG01",
        claimant_id=user.id,
        customer_id=str(user.id),
        tenant_id=tenant_id,
        status="draft",
        updated_at=datetime.now(timezone.utc),
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)
    token = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": tenant_id})
    db.close()

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    # First fetch: should return 200 and an ETag header
    res1 = client.get("/api/v1/claims/CLAIM-ETAG01", headers=headers)
    assert res1.status_code == 200
    etag1 = res1.headers.get("etag")
    assert etag1 is not None
    assert len(etag1) > 0

    # Second fetch with If-None-Match: should return 304 Not Modified
    res2 = client.get(
        "/api/v1/claims/CLAIM-ETAG01",
        headers={**headers, "If-None-Match": etag1},
    )
    assert res2.status_code == 304
    assert res2.headers.get("etag") == etag1

    # Update claim status
    db = etag_test_db()
    c = db.query(Claim).filter(Claim.ticket_id == "CLAIM-ETAG01").first()
    c.status = "submitted"
    c.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.close()

    # Third fetch with old ETag: should return 200 with new ETag
    res3 = client.get(
        "/api/v1/claims/CLAIM-ETAG01",
        headers={**headers, "If-None-Match": etag1},
    )
    assert res3.status_code == 200
    etag3 = res3.headers.get("etag")
    assert etag3 is not None
    assert etag3 != etag1

def test_adjuster_claim_etag_and_304(etag_test_db):
    db = etag_test_db()
    tenant_id = "00000000-0000-0000-0000-000000000001"
    user = User(
        full_name="ETag Adjuster",
        email="etag_adjuster@example.com",
        password_hash="mock_hash",
        role="ADJUSTER",
        tenant_id=tenant_id,
        status="active",
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    adj = Adjuster(
        name="ETag Adjuster",
        email=user.email,
        phone="+1234567890",
        tenant_id=tenant_id,
        user_id=user.id,
        specialization="auto",
        is_active=True,
    )
    db.add(adj)
    db.commit()
    db.refresh(adj)

    claim = Claim(
        ticket_id="CLAIM-ADJETAG01",
        claimant_id=user.id,
        customer_id=str(user.id),
        tenant_id=tenant_id,
        status="submitted",
        updated_at=datetime.now(timezone.utc),
        pipeline_state={"assigned_adjuster_id": adj.id},
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)

    assign = ClaimAssignment(
        claim_id=claim.id,
        tenant_id=tenant_id,
        adjuster_id=adj.id,
        is_active=True,
    )
    db.add(assign)
    db.commit()

    token = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": tenant_id})
    db.close()

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    # First fetch: 200 with ETag
    res1 = client.get("/api/v1/adjuster/claims/CLAIM-ADJETAG01", headers=headers)
    assert res1.status_code == 200
    etag1 = res1.headers.get("etag")
    assert etag1 is not None

    # Second fetch: 304 Not Modified
    res2 = client.get(
        "/api/v1/adjuster/claims/CLAIM-ADJETAG01",
        headers={**headers, "If-None-Match": etag1},
    )
    assert res2.status_code == 304
    assert res2.headers.get("etag") == etag1
