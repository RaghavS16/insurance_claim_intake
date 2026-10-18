"""Tests for HttpOnly cookie session management, origin validation, and token family revocation."""
import pytest
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from src.config import settings
from src.api.main import app
from src.utils.auth import get_password_hash
from src.database.hardening_models import RefreshToken

client = TestClient(app)


@pytest.fixture
def cookie_test_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.database.models import Base
    from src.database.hardening_models import Base as HardeningBase
    from src.database.session import get_db

    db_file = tmp_path / "cookie_test.db"
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


def test_cookie_auth_lifecycle(cookie_test_db, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_TEST_AUTH", True)
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "http://localhost:3000,http://app.example.com")

    from src.database.models import User

    db = cookie_test_db()
    try:
        user_id = str(uuid.uuid4())
        tenant_id = "00000000-0000-0000-0000-000000000001"
        test_email = f"cookie_user_{user_id}@example.com"
        u = User(
            id=user_id,
            email=test_email,
            password_hash=get_password_hash("ValidPass123!"),
            full_name="Cookie User",
            role="CLAIMANT",
            status="active",
            email_verified_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
        )
        db.add(u)
        db.commit()

        # 1. Login sets HttpOnly refresh_token cookie
        login_res = client.post("/api/v1/auth/login", json={"email": test_email, "password": "ValidPass123!"})
        assert login_res.status_code == 200
        assert "access_token" in login_res.json()
        assert "refresh_token" in login_res.cookies

        cookie_header = login_res.headers.get("set-cookie", "")
        assert "HttpOnly" in cookie_header
        assert "Path=/api/v1/auth" in cookie_header
        assert "SameSite=strict" in cookie_header or "samesite=strict" in cookie_header

        refresh_cookie_val = login_res.cookies["refresh_token"]

        # 2. Refresh using cookie succeeds and rotates cookie
        refresh_res = client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": refresh_cookie_val},
            headers={"Origin": "http://localhost:3000"},
        )
        assert refresh_res.status_code == 200
        assert "access_token" in refresh_res.json()
        assert "refresh_token" in refresh_res.cookies
        new_refresh_cookie = refresh_res.cookies["refresh_token"]
        assert new_refresh_cookie != refresh_cookie_val

        # 3. Cross-origin refresh is forbidden
        evil_res = client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": new_refresh_cookie},
            headers={"Origin": "http://malicious-site.com"},
        )
        assert evil_res.status_code == 403
        assert "Cross-origin" in evil_res.json()["detail"]

        # 4. Logout clears the cookie and revokes the family
        logout_res = client.post(
            "/api/v1/auth/logout",
            cookies={"refresh_token": new_refresh_cookie},
            headers={"Authorization": f"Bearer {refresh_res.json()['access_token']}"},
        )
        assert logout_res.status_code == 200

        # After logout, old or new refresh token fails
        dead_res = client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": new_refresh_cookie},
        )
        assert dead_res.status_code == 401
    finally:
        db.close()


def test_refresh_token_body_fallback_in_non_production(cookie_test_db, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_TEST_AUTH", True)

    from src.database.models import User

    db = cookie_test_db()
    try:
        user_id = str(uuid.uuid4())
        tenant_id = "00000000-0000-0000-0000-000000000001"
        test_email = f"body_user_{user_id}@example.com"
        u = User(
            id=user_id,
            email=test_email,
            password_hash=get_password_hash("ValidPass123!"),
            full_name="Body User",
            role="CLAIMANT",
            status="active",
            email_verified_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
        )
        db.add(u)
        db.commit()

        login_res = client.post("/api/v1/auth/login", json={"email": test_email, "password": "ValidPass123!"})
        refresh_token = login_res.json()["refresh_token"]

        # Send via body without cookies in test environment
        res = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert res.status_code == 200
        assert "access_token" in res.json()
    finally:
        db.close()
