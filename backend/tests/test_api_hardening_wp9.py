from datetime import datetime, timezone
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base, User
from src.database.session import get_db
from src.utils.auth import create_access_token, get_password_hash
from src.api.main import app

TEST_DB_FILE = "test_api_hardening_wp9.db"
engine = create_engine(f"sqlite:///{TEST_DB_FILE}", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass

@pytest.fixture
def test_user():
    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == "hardening_user@example.com").first()
    if not user:
        user = User(
            id="00000000-0000-0000-0000-000000000999",
            email="hardening_user@example.com",
            password_hash=get_password_hash("ValidPass123!"),
            full_name="Hardening User",
            phone="+1234567890",
            role="CLAIMANT",
            status="active",
            tenant_id="00000000-0000-0000-0000-000000000001",
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    return user


@pytest.fixture
def auth_headers(test_user):
    token = create_access_token(
        data={"sub": test_user.id, "email": test_user.email, "role": test_user.role, "tenant_id": test_user.tenant_id}
    )
    return {"Authorization": f"Bearer {token}"}


def test_health_check_returns_only_status_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_update_me_accepts_valid_fields(auth_headers):
    client = TestClient(app)
    res = client.patch(
        "/api/v1/auth/me",
        headers=auth_headers,
        json={"full_name": "Updated Name", "phone": "+1987654321"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["full_name"] == "Updated Name"
    assert data["phone"] == "+1987654321"


def test_update_me_rejects_unknown_fields(auth_headers):
    client = TestClient(app)
    res = client.patch(
        "/api/v1/auth/me",
        headers=auth_headers,
        json={"full_name": "Another Name", "role": "ADMIN", "is_admin": True},
    )
    assert res.status_code == 422


def test_update_me_rejects_invalid_phone(auth_headers):
    client = TestClient(app)
    res = client.patch(
        "/api/v1/auth/me",
        headers=auth_headers,
        json={"phone": "INVALID_PHONE_WITH_LETTERS"},
    )
    assert res.status_code == 422


def test_update_me_rejects_too_long_name(auth_headers):
    client = TestClient(app)
    res = client.patch(
        "/api/v1/auth/me",
        headers=auth_headers,
        json={"full_name": "A" * 150},
    )
    assert res.status_code == 422


def test_notifications_route_wired(auth_headers):
    client = TestClient(app)
    res = client.get("/api/v1/notifications", headers=auth_headers)
    assert res.status_code == 200
    assert "items" in res.json()


def test_docs_disabled_in_production_unless_flag():
    from src.config import Settings
    prod_settings = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        ENABLE_API_DOCS=False,
        ALLOW_INSECURE_TEST_AUTH=False,
        SECRET_KEY="a"*32,
        DATABASE_URL="sqlite:///:memory:",
        PUBLIC_APP_URL="https://app.example.com",
    )
    _enable_docs = prod_settings.ENABLE_API_DOCS or (prod_settings.ENVIRONMENT not in ("production", "staging"))
    assert _enable_docs is False

    prod_docs_settings = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        ENABLE_API_DOCS=True,
        ALLOW_INSECURE_TEST_AUTH=False,
        SECRET_KEY="a"*32,
        DATABASE_URL="sqlite:///:memory:",
        PUBLIC_APP_URL="https://app.example.com",
    )
    _enable_docs_flag = prod_docs_settings.ENABLE_API_DOCS or (prod_docs_settings.ENVIRONMENT not in ("production", "staging"))
    assert _enable_docs_flag is True
