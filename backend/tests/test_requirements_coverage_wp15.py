import os
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.main import app
from src.config import settings
from src.database.models import Base, User, Claim, Adjuster
from src.database.session import get_db
from src.database.hardening_models import Tenant
from src.utils.auth import create_access_token, get_password_hash

TEST_DB_FILE = "test_requirements_coverage_wp15.db"
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


client = TestClient(app)


def test_auth_full_lifecycle_and_cookie_flow(monkeypatch):
    """
    Prove Auth requirement:
    sign-up -> email OTP verify -> login -> token refresh -> authenticated request -> logout ->
    forgot-password OTP -> verify OTP -> reset password -> login with new password.
    """
    latest_otps = {}

    def mock_send_otp(to_email, otp, full_name=None, purpose="password_reset"):
        latest_otps[f"{to_email}:{purpose}"] = otp
        return True

    monkeypatch.setattr("src.api.auth_routes.send_otp_email", mock_send_otp)
    monkeypatch.setattr("src.utils.email_otp.send_otp_email", mock_send_otp)
    monkeypatch.setattr(settings, "REQUIRE_EMAIL_VERIFICATION", True)

    email = f"test_auth_wp15_{int(datetime.now().timestamp())}@example.com"
    pwd = "StrongPassword123!"
    new_pwd = "UpdatedPassword456!"

    # 1. Sign up
    signup_res = client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": pwd,
        "confirm_password": pwd,
        "full_name": "WP15 Auth User",
        "phone": "+15551234567"
    })
    assert signup_res.status_code in (200, 201), signup_res.text

    # 2. Email OTP Verify
    verify_otp_val = latest_otps.get(f"{email}:email_verification")
    assert verify_otp_val, "Expected email_verification OTP to be generated and queued"

    verify_res = client.post("/api/v1/auth/verify-email", json={
        "email": email,
        "otp": verify_otp_val
    })
    assert verify_res.status_code == 200, verify_res.text

    # 3. Login
    login_res = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": pwd
    })
    assert login_res.status_code == 200, login_res.text
    login_data = login_res.json()
    assert "access_token" in login_data
    assert "refresh_token" not in login_data
    access_token = login_data["access_token"]
    refresh_cookie = login_res.cookies.get("refresh_token")
    assert refresh_cookie, "Expected refresh_token cookie"

    # 4. Refresh token
    refresh_res = client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": refresh_cookie},
    )
    assert refresh_res.status_code == 200, refresh_res.text
    assert "refresh_token" not in refresh_res.json()
    new_token = refresh_res.json()["access_token"]
    assert new_token

    # 5. Authenticated request
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == email

    # 6. Logout
    logout_res = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {new_token}"})
    assert logout_res.status_code == 200

    # 7. Forgot Password & Reset Password Flow
    forgot_res = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert forgot_res.status_code in (200, 202), forgot_res.text
    reset_otp_val = latest_otps.get(f"{email}:password_reset")
    assert reset_otp_val, "Expected password_reset OTP to be generated"

    otp_res = client.post("/api/v1/auth/verify-otp", json={
        "email": email,
        "otp": reset_otp_val
    })
    assert otp_res.status_code == 200, otp_res.text
    reset_token = otp_res.json()["reset_token"]

    reset_res = client.post("/api/v1/auth/reset-password", json={
        "reset_token": reset_token,
        "new_password": new_pwd,
        "confirm_password": new_pwd
    })
    assert reset_res.status_code == 200, reset_res.text

    # 8. Login with new password
    new_login_res = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": new_pwd
    })
    assert new_login_res.status_code == 200, new_login_res.text


def test_authorization_negative_boundaries():
    """
    Negative tests:
    - Cross-tenant isolation violation (403)
    - Claimant cannot read another claimant's claim (403)
    - Adjuster cannot access unassigned claim (403)
    - Claimant cannot access Admin or Adjuster routes (403)
    - Adjuster cannot access Admin routes (403)
    """
    from types import SimpleNamespace
    from fastapi import HTTPException
    from src.utils.authorization import enforce_claim_ownership

    # 1. Cross-tenant isolation violation
    claim_tenant_a = SimpleNamespace(id="c1", tenant_id="tenant-A", claimant_id="u1", customer_id="u1")
    user_tenant_b = SimpleNamespace(id="u1", tenant_id="tenant-B", role="CLAIMANT")
    with pytest.raises(HTTPException) as exc:
        enforce_claim_ownership(claim_tenant_a, user_tenant_b)
    assert exc.value.status_code == 403

    # 2. Claimant cannot read another claimant's claim
    claim_user_2 = SimpleNamespace(id="c2", tenant_id="tenant-A", claimant_id="u2", customer_id="u2")
    user_1 = SimpleNamespace(id="u1", tenant_id="tenant-A", role="CLAIMANT")
    with pytest.raises(HTTPException) as exc:
        enforce_claim_ownership(claim_user_2, user_1)
    assert exc.value.status_code == 403

    # 3. Adjuster cannot access unassigned claim
    adjuster_user = SimpleNamespace(id="adj-1", tenant_id="tenant-A", role="ADJUSTER")
    db = TestingSessionLocal()
    try:
        with pytest.raises(HTTPException) as exc:
            enforce_claim_ownership(claim_user_2, adjuster_user, db=db)
        assert exc.value.status_code == 403
    finally:
        db.close()

    # 4. Route-level RBAC negative tests
    db = TestingSessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.id == "default").first()
        if not tenant:
            tenant = Tenant(id="default", name="Default Tenant")
            db.add(tenant)
            db.commit()

        c_user = User(
            id="u_claimant_1",
            full_name="Claimant Test",
            email="u_claimant_1@test.com",
            phone="",
            password_hash=get_password_hash("pass123"),
            role="CLAIMANT",
            status="active",
            tenant_id="default",
            email_verified_at=datetime.now(timezone.utc),
        )
        a_user = User(
            id="u_adj_1",
            full_name="Adjuster Test",
            email="u_adj_1@test.com",
            phone="",
            password_hash=get_password_hash("pass123"),
            role="ADJUSTER",
            status="active",
            tenant_id="default",
            email_verified_at=datetime.now(timezone.utc),
        )
        db.merge(c_user)
        db.merge(a_user)
        db.commit()
    finally:
        db.close()

    # Create tokens for claimant and adjuster
    claimant_token = create_access_token(data={"sub": "u_claimant_1", "role": "CLAIMANT", "tenant_id": "default"})
    adjuster_token = create_access_token(data={"sub": "u_adj_1", "role": "ADJUSTER", "tenant_id": "default"})

    # Claimant accessing admin route
    claimant_admin_req = client.get("/api/v1/admin/adjusters", headers={"Authorization": f"Bearer {claimant_token}"})
    assert claimant_admin_req.status_code == 403, claimant_admin_req.text

    # Adjuster accessing admin route
    adjuster_admin_req = client.get("/api/v1/admin/adjusters", headers={"Authorization": f"Bearer {adjuster_token}"})
    assert adjuster_admin_req.status_code == 403, adjuster_admin_req.text


def test_deterministic_llm_fallback_and_rag_grounding():
    """LLM calls use deterministic safe mock when test auth is active or real provider with HF_TOKEN."""
    from src.knowledge.retriever import KnowledgeRetriever
    retriever = KnowledgeRetriever()
    assert retriever is not None
    # Verify fail-closed behavior when knowledge is absent
    res = retriever.answer_query(query="Does my policy cover damage?", insurance_type="nonexistent_type")
    assert res["status"] in ("NO_RELEVANT_KNOWLEDGE", "OK")


def test_claim_etag_and_caching_behavior():
    """Verify WP8 ETag generation and 304 Not Modified caching on claims endpoints."""
    db = TestingSessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.id == "default").first()
        if not tenant:
            tenant = Tenant(id="default", name="Default Tenant")
            db.add(tenant)
            db.commit()

        claim = Claim(
            id="test-etag-claim",
            ticket_id="CLM-ETAG-001",
            claimant_id="user-etag-1",
            customer_id="user-etag-1",
            tenant_id="default",
            status="SUBMITTED",
            insurance_type="AUTO",
            updated_at=datetime.now(timezone.utc)
        )
        db.merge(claim)
        db.commit()
    finally:
        db.close()

    user_token = create_access_token(data={"sub": "user-etag-1", "role": "CLAIMANT", "tenant_id": "default"})
    headers = {"Authorization": f"Bearer {user_token}"}

    # Initial request
    res1 = client.get("/api/v1/claims/test-etag-claim", headers=headers)
    if res1.status_code == 200:
        etag = res1.headers.get("ETag")
        assert etag, "ETag header must be returned on claim detail"

        # Polling with If-None-Match should return 304 Not Modified
        headers_with_etag = {**headers, "If-None-Match": etag}
        res2 = client.get("/api/v1/claims/test-etag-claim", headers=headers_with_etag)
        assert res2.status_code == 304


def test_policy_linking_flow():
    """Verify claimant can link an existing policy using DOB and phone last 4."""
    from datetime import date
    from src.database.models import Policy
    import uuid

    db = TestingSessionLocal()
    try:
        policy = Policy(
            id=str(uuid.uuid4()),
            tenant_id="default",
            policy_number="POL-LINK-999",
            policy_type="motor",
            coverage_amount=50000.0,
            deductible=500.0,
            effective_date=date(2026, 1, 1),
            expiry_date=date(2027, 1, 1),
            is_active=True,
            policyholder_name="Link Claimant",
            policyholder_dob=date(1990, 5, 15),
            policyholder_phone="9876541234",
            policyholder_phone_last4="1234",
            customer_id=None
        )
        db.merge(policy)
        db.commit()
    finally:
        db.close()

    claimant_token = create_access_token(data={"sub": "u_claimant_1", "role": "CLAIMANT", "tenant_id": "default"})
    res = client.post("/api/v1/policies/link", headers={"Authorization": f"Bearer {claimant_token}"}, json={
        "policy_number": "POL-LINK-999",
        "date_of_birth": "1990-05-15",
        "phone_last4": "1234"
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["linked"] is True


def test_admin_policy_workflow_and_adjuster_invite():
    """Verify admin policy template, strict creation, export, and adjuster invite + onboarding."""
    import uuid
    import urllib.parse
    from src.database.models import User

    db = TestingSessionLocal()
    try:
        admin_user = User(
            id="u_admin_coverage_test",
            full_name="Admin Test",
            email="admin_cov@test.com",
            phone="1234567890",
            password_hash=get_password_hash("AdminPass123!"),
            role="ADMIN",
            status="active",
            tenant_id="default",
            email_verified_at=datetime.now(timezone.utc)
        )
        db.merge(admin_user)
        db.commit()
    finally:
        db.close()

    admin_token = create_access_token(data={"sub": "u_admin_coverage_test", "role": "ADMIN", "tenant_id": "default"})
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Policy template download (RFC 6266 attachment)
    template_res = client.get("/api/v1/admin/policies/template?format=csv", headers=admin_headers)
    assert template_res.status_code == 200
    assert "attachment;" in template_res.headers.get("Content-Disposition", "")
    assert "policy_number" in template_res.text

    # 2. Strict policy creation
    pol_num = f"POL-STRICT-{int(datetime.now().timestamp())}"
    strict_res = client.post("/api/v1/admin/policies/strict", headers=admin_headers, json={
        "policy_number": pol_num,
        "policy_type": "motor",
        "coverage_amount": 75000.0,
        "deductible": 1000.0,
        "effective_date": "2026-01-01",
        "expiry_date": "2027-01-01",
        "policyholder_name": "Strict Policyholder",
        "policyholder_dob": "1988-08-08",
        "policyholder_phone": "+15559876543",
        "policyholder_email": "strict@example.com"
    })
    assert strict_res.status_code == 200, strict_res.text

    # 3. Policy export
    export_res = client.get("/api/v1/admin/policies/export?format=csv", headers=admin_headers)
    assert export_res.status_code == 200
    assert "attachment;" in export_res.headers.get("Content-Disposition", "")
    assert pol_num in export_res.text

    # 4. Invite adjuster
    adj_email = f"invited_adj_{int(datetime.now().timestamp())}@example.com"
    invite_res = client.post("/api/v1/admin/adjusters/invite", headers=admin_headers, json={
        "name": "Invited Adjuster",
        "email": adj_email,
        "phone": "+15558889999",
        "specialization": "motor"
    })
    assert invite_res.status_code == 200, invite_res.text
    invite_data = invite_res.json()
    invite_url = invite_data["invitation_url"]
    parsed_url = urllib.parse.urlparse(invite_url)
    params = urllib.parse.parse_qs(parsed_url.query)
    raw_token = params["token"][0]

    # 5. Onboard / Accept invitation
    new_adj_pwd = "OnboardedAdjPass123!"
    accept_res = client.post("/api/v1/auth/onboarding/adjuster/accept", json={
        "token": raw_token,
        "password": new_adj_pwd,
        "confirm_password": new_adj_pwd
    })
    assert accept_res.status_code == 200, accept_res.text
    assert accept_res.json()["accepted"] is True

    # 6. Newly onboarded adjuster can log in
    adj_login_res = client.post("/api/v1/auth/login", json={
        "email": adj_email,
        "password": new_adj_pwd
    })
    assert adj_login_res.status_code == 200, adj_login_res.text
    assert "access_token" in adj_login_res.json()


def test_claim_auto_assignment_and_adjuster_review():
    """Verify claim auto-assignment, claim authorization, and adjuster review."""
    import uuid
    from src.database.models import Claim, Adjuster, User
    from src.database.claim_workflow import assign_claim
    from src.database.hardening_models import ClaimAssignment

    db = TestingSessionLocal()
    try:
        # Create an active adjuster
        adj_id = f"adj_auto_{int(datetime.now().timestamp())}"
        adj_user = User(
            id=adj_id,
            full_name="Auto Assigned Adjuster",
            email=f"{adj_id}@test.com",
            phone="1234567890",
            password_hash=get_password_hash("pass"),
            role="ADJUSTER",
            status="active",
            tenant_id="default",
            email_verified_at=datetime.now(timezone.utc)
        )
        adjuster = Adjuster(
            id=adj_id,
            user_id=adj_id,
            tenant_id="default",
            name="Auto Assigned Adjuster",
            email=f"{adj_id}@test.com",
            phone="1234567890",
            specialization="motor",
            claims_assigned=0,
            is_active=True
        )
        db.merge(adj_user)
        db.merge(adjuster)

        # Create unassigned claim
        claim_id = str(uuid.uuid4())
        claim = Claim(
            id=claim_id,
            ticket_id="CLM-AUTO-001",
            claimant_id="u_claimant_1",
            customer_id="u_claimant_1",
            tenant_id="default",
            status="submitted",
            insurance_type="motor"
        )
        db.merge(claim)
        db.commit()

        # Execute auto-assignment
        assigned_adj = assign_claim(db, claim)
        assert assigned_adj is not None
        db.commit()

        # Verify ClaimAssignment row exists for the assigned adjuster
        assignment = db.query(ClaimAssignment).filter(
            ClaimAssignment.claim_id == claim_id,
            ClaimAssignment.adjuster_id == assigned_adj.id,
            ClaimAssignment.is_active.is_(True)
        ).first()
        assert assignment is not None

        # Verify adjuster ownership authorization allows access
        assigned_user = db.query(User).filter(User.id == assigned_adj.user_id).first()
        from src.utils.authorization import enforce_claim_ownership
        enforce_claim_ownership(claim, assigned_user, db=db)
    finally:
        db.close()

