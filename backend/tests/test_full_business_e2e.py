"""
Deterministic End-to-End Business Verification Suite across all 4 Core Business Pillars:
1. Authentication & Account Management
2. Admin Features (Dashboard, Policies, Adjusters, Exports)
3. Adjuster Knowledge Base Management — Source of Truth RAG
4. Claimant Features (Policy Linking, RAG Chatbot, Dynamic Intake, Auto-Assignment, Chat History)
5. Adjuster Features & Claimant Request-Response Loop (Copilot, Evidence Request/Response, Decisioning)
"""
from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import docx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.main import app
from src.config import settings
from src.database.models import (
    Base,
    User,
    Adjuster,
    Claim,
    KnowledgeDocument,
    KnowledgeChunk,
)
from src.database.hardening_models import (
    Base as HardeningBase,
    ClaimEvidence,
    ClaimDecision,
)
from src.database.session import get_db

E2E_DB_FILE = "e2e_business_verification.db"
engine = create_engine(
    f"sqlite:///{E2E_DB_FILE}",
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

captured_otps: dict[str, str] = {}


def mock_send_otp_email(to_email: str, otp: str, full_name: str | None = None, purpose: str = "password_reset") -> bool:
    captured_otps[f"{to_email}:{purpose}"] = otp
    return True


@pytest.fixture(scope="module", autouse=True)
def e2e_db_setup(monkeypatch_module=None):
    """Set up clean database, mock SMTP, override DB dependency, and seed demo baseline."""
    # Ensure fresh DB schema
    Base.metadata.drop_all(bind=engine)
    HardeningBase.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    HardeningBase.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Patch settings
    settings.ENVIRONMENT = "test"
    settings.ALLOW_INSECURE_TEST_AUTH = True
    settings.REQUIRE_EMAIL_VERIFICATION = True
    settings.ALLOWED_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"

    import src.utils.email_otp as email_otp_mod
    import src.api.auth_routes as auth_routes_mod
    email_otp_mod.send_otp_email = mock_send_otp_email
    auth_routes_mod.send_otp_email = mock_send_otp_email

    # Reconfigure SessionLocal in-place so all modules point to SQLite
    import database._db_helpers as db_helpers
    import src.database.session as session_mod
    import src.knowledge.store as kstore_mod
    import src.api.knowledge_routes as kroutes_mod

    orig_engine = session_mod.engine
    session_mod.engine = engine
    session_mod.SessionLocal.configure(bind=engine)
    db_helpers.SessionLocal.configure(bind=engine)
    kstore_mod.SessionLocal.configure(bind=engine)
    kroutes_mod.SessionLocal.configure(bind=engine)

    from database.seed_demo import seed_demo
    os.environ["DEMO_PASSWORD"] = "DemoPass123!"
    os.environ["SKIP_DOCRAG_SEED"] = "1"
    seed_demo()

    yield

    app.dependency_overrides.pop(get_db, None)
    session_mod.engine = orig_engine
    Base.metadata.drop_all(bind=engine)
    HardeningBase.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(E2E_DB_FILE):
        try:
            os.remove(E2E_DB_FILE)
        except Exception:
            pass


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# Shared state dictionary across the 5 sequential tests
shared: dict[str, any] = {}


def test_01_authentication_and_forgot_password_flow(client: TestClient):
    """
    1. Authentication & Account Management:
    - 1.1 Auth Flow: Sign-up (<1.0s, no refresh token in body) -> Email OTP verify -> Login (HttpOnly cookie)
                    -> /me (twice) -> Refresh (rotation) -> Logout -> 401 on old token.
    - 1.2 Forgot Password Flow: Request OTP (<1.0s) -> Verify recovery OTP -> Reset password -> Old password fails, new succeeds.
    """
    claimant_email = f"e2e.claimant.{int(time.time())}@example.com"
    raw_password = "StrongPass123!"
    updated_password = "NewStrongPass456!"

    # 1. Sign up
    t0 = time.perf_counter()
    signup_res = client.post("/api/v1/auth/signup", json={
        "full_name": "E2E Test Claimant",
        "email": claimant_email,
        "phone": "+919876543210",
        "password": raw_password,
        "confirm_password": raw_password,
    })
    elapsed_signup = time.perf_counter() - t0
    assert elapsed_signup < 1.0, f"Signup latency {elapsed_signup:.3f}s exceeded 1.0s SLA target."
    assert signup_res.status_code in (200, 201), signup_res.text
    signup_json = signup_res.json()
    assert "refresh_token" not in signup_json, "Security violation: raw refresh_token must never be exposed in JSON body"

    # 2. Email verification OTP
    verify_otp = captured_otps.get(f"{claimant_email}:email_verification")
    assert verify_otp and len(verify_otp) == 6, f"Expected 6-digit email verification OTP, got {verify_otp}"

    verify_res = client.post("/api/v1/auth/verify-email", json={
        "email": claimant_email,
        "otp": verify_otp,
    })
    assert verify_res.status_code == 200, verify_res.text

    # 3. Login
    login_res = client.post("/api/v1/auth/login", json={
        "email": claimant_email,
        "password": raw_password,
    })
    assert login_res.status_code == 200, login_res.text
    login_data = login_res.json()
    assert "access_token" in login_data
    assert "user" in login_data
    assert "refresh_token" not in login_data
    access_token = login_data["access_token"]
    refresh_cookie = login_res.cookies.get("refresh_token")
    assert refresh_cookie, "Expected HttpOnly refresh_token cookie on successful login."

    # 4. /me endpoint twice
    auth_headers = {"Authorization": f"Bearer {access_token}"}
    me_res1 = client.get("/api/v1/auth/me", headers=auth_headers)
    assert me_res1.status_code == 200
    assert me_res1.json()["email"] == claimant_email

    me_res2 = client.get("/api/v1/auth/me", headers=auth_headers)
    assert me_res2.status_code == 200
    assert me_res2.json()["full_name"] == "E2E Test Claimant"

    # 5. Token refresh rotation
    refresh_res = client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": refresh_cookie},
        headers={"Origin": "http://localhost:3000"},
    )
    assert refresh_res.status_code == 200, refresh_res.text
    refresh_data = refresh_res.json()
    assert "access_token" in refresh_data
    assert "user" in refresh_data
    rotated_access_token = refresh_data["access_token"]
    rotated_refresh_cookie = refresh_res.cookies.get("refresh_token") or refresh_cookie

    # 6. Logout and verify invalidation
    logout_res = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {rotated_access_token}"},
        cookies={"refresh_token": rotated_refresh_cookie},
    )
    assert logout_res.status_code == 200

    old_token_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {rotated_access_token}"})
    assert old_token_res.status_code == 401, "Revoked access token must be rejected with HTTP 401"

    # 1.2 Forgot Password Flow
    t0_fp = time.perf_counter()
    fp_res = client.post("/api/v1/auth/forgot-password", json={"email": claimant_email})
    elapsed_fp = time.perf_counter() - t0_fp
    assert elapsed_fp < 1.0, f"Forgot password latency {elapsed_fp:.3f}s exceeded 1.0s SLA target."
    assert fp_res.status_code == 200, fp_res.text

    reset_otp = captured_otps.get(f"{claimant_email}:password_reset")
    assert reset_otp and len(reset_otp) == 6, f"Expected 6-digit recovery OTP, got {reset_otp}"

    vo_res = client.post("/api/v1/auth/verify-otp", json={
        "email": claimant_email,
        "otp": reset_otp,
    })
    assert vo_res.status_code == 200, vo_res.text
    reset_token = vo_res.json().get("reset_token")
    assert reset_token, "verify-otp must return short-lived reset_token"

    rp_res = client.post("/api/v1/auth/reset-password", json={
        "reset_token": reset_token,
        "new_password": updated_password,
        "confirm_password": updated_password,
    })
    assert rp_res.status_code == 200, rp_res.text

    # Old password fails (401)
    old_login = client.post("/api/v1/auth/login", json={
        "email": claimant_email,
        "password": raw_password,
    })
    assert old_login.status_code == 401

    # New password succeeds (200)
    new_login = client.post("/api/v1/auth/login", json={
        "email": claimant_email,
        "password": updated_password,
    })
    assert new_login.status_code == 200
    assert "access_token" in new_login.json()


def test_02_admin_dashboard_policies_adjusters_and_exports(client: TestClient):
    """
    2. Admin Features:
    - 4.4 Adjuster Onboarding, invite token generation & patch active status.
    - 4.3 Policy Management (Single creation & Bulk CSV ingestion with per-row errors).
    - 4.2 Data Filtering & Export (CSV exports and template).
    - 4.1 Admin Dashboard Operational Metrics (policies, claims, settlement, workload).
    """
    # Login as Admin
    admin_login = client.post("/api/v1/auth/login", json={
        "email": "admin@insurance.com",
        "password": "DemoPass123!",
    })
    assert admin_login.status_code == 200, admin_login.text
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    shared["admin_headers"] = admin_headers

    # 4.4 Adjuster Onboarding
    new_adj_email = f"adjuster.e2e.{int(time.time())}@insurance.com"
    adj_create_res = client.post("/api/v1/admin/adjusters", headers=admin_headers, json={
        "name": "E2E Senior Adjuster",
        "email": new_adj_email,
        "phone": "+919876500099",
        "specialization": "motor",
    })
    assert adj_create_res.status_code in (200, 201), adj_create_res.text
    adj_id = adj_create_res.json()["id"]

    # Verify invite endpoint
    invite_res = client.post("/api/v1/admin/adjusters/invite", headers=admin_headers, json={
        "name": "Invited Specialist",
        "email": f"invited.{int(time.time())}@insurance.com",
        "phone": "+919876500098",
        "specialization": "motor",
    })
    assert invite_res.status_code in (200, 201), invite_res.text
    assert "invitation_url" in invite_res.json()

    # PATCH Adjuster role / status
    list_adjs = client.get("/api/v1/admin/adjusters", headers=admin_headers)
    assert list_adjs.status_code == 200
    adjs_data = list_adjs.json()
    adj_to_patch = (adjs_data[0]["id"] if isinstance(adjs_data, list) else adjs_data["items"][0]["id"])
    patch_adj_res = client.patch(f"/api/v1/admin/adjusters/{adj_to_patch}", headers=admin_headers, json={
        "specialization": "motor",
        "is_active": True,
    })
    assert patch_adj_res.status_code == 200, patch_adj_res.text
    assert patch_adj_res.json()["is_active"] is True

    # 4.3 Policy Management (Single)
    policy_num = "POL-E2E-MOTOR-999"
    create_pol_res = client.post("/api/v1/admin/policies", headers=admin_headers, json={
        "policy_number": policy_num,
        "policy_type": "motor",
        "coverage_amount": 2000000.0,
        "deductible": 5000.0,
        "effective_date": "2026-01-01",
        "expiry_date": "2027-01-01",
        "policyholder_name": "Riya Claimant",
        "policyholder_dob": "1994-06-15",
        "policyholder_phone": "9876500004",
        "policyholder_email": "riya.claimant@insurance.com",
        "is_active": True,
    })
    assert create_pol_res.status_code in (200, 201), create_pol_res.text
    shared["created_policy_number"] = policy_num

    # 4.3 Bulk Policy Ingestion with 1 malformed row
    bulk_csv = (
        "policy_number,policy_type,coverage_amount,deductible,effective_date,expiry_date,policyholder_name,policyholder_dob,policyholder_phone,policyholder_email\n"
        "POL-BULK-MOT-101,motor,1500000,10000,2026-01-01,2027-01-01,Bulk Motor Holder,1990-05-10,9876500021,bulk.mot@insurance.com\n"
        "POL-BULK-HLT-102,health,800000,5000,2026-01-01,2027-01-01,Bulk Health Holder,1985-08-20,9876500022,bulk.hlt@insurance.com\n"
        "POL-BULK-BAD-103,invalid_type,50000,0,2026-01-01,2027-01-01,Malformed Holder,1990-01-01,9876500023,bad@insurance.com\n"
    )
    bulk_res = client.post(
        "/api/v1/admin/policies/bulk",
        headers=admin_headers,
        files={"file": ("bulk_policies.csv", bulk_csv.encode("utf-8"), "text/csv")},
    )
    assert bulk_res.status_code == 200, bulk_res.text
    bulk_data = bulk_res.json()
    created_count = bulk_data.get("created_count", bulk_data.get("created", 0))
    assert created_count >= 2, f"Expected at least 2 valid rows created, got {created_count}"
    assert len(bulk_data.get("errors", [])) >= 1, "Expected at least 1 row error for malformed policy"
    err = bulk_data["errors"][0]
    assert "row" in err and "policy_number" in err and "error" in err

    # 4.2 Data Filtering & Export
    filter_res = client.get("/api/v1/admin/policies?policy_type=motor&status=active", headers=admin_headers)
    assert filter_res.status_code == 200, filter_res.text
    items = filter_res.json()["items"]
    assert len(items) > 0
    for it in items:
        assert it["policy_type"] == "motor"
        assert it["is_active"] is True

    pol_exp = client.get("/api/v1/admin/exports/policies?format=csv", headers=admin_headers)
    assert pol_exp.status_code == 200
    assert "policy_number" in pol_exp.text

    adj_exp = client.get("/api/v1/admin/exports/adjusters?format=csv", headers=admin_headers)
    assert adj_exp.status_code == 200
    assert "specialization" in adj_exp.text

    tpl_res = client.get("/api/v1/admin/policies/template", headers=admin_headers)
    assert tpl_res.status_code == 200
    assert "policy_number" in tpl_res.text

    # 4.1 Admin Dashboard Operational Metrics
    dash_res = client.get("/api/v1/admin/dashboard", headers=admin_headers)
    assert dash_res.status_code == 200, dash_res.text
    dash = dash_res.json()
    assert "policies" in dash and dash["policies"]["active"] > 0
    assert "claims" in dash and "stages" in dash["claims"]
    assert "settlement" in dash and "approved_volume" in dash["settlement"]
    assert "workload" in dash and dash["workload"]["active_adjusters"] > 0


def _build_test_policy_docx(custom_intake_field: str | None = None) -> bytes:
    """Construct an in-memory .docx with Section 5, Section 6.3, Section 6.5 and Section 6.6 tables."""
    doc = docx.Document()
    doc.add_heading("Motor Insurance Policy Wording — Standard Commercial & Private Vehicle", level=1)
    
    doc.add_heading("Section 5 Application Requirements", level=2)
    doc.add_paragraph("Applicants must provide valid identification, vehicle registration certificate, and driving license.")

    doc.add_heading("Section 6.3 IRDAI Timelines", level=2)
    doc.add_paragraph(
        "Per IRDAI Master Circular 2024: The insurer must appoint an independent surveyor within 24 hours of claim intimation. "
        "The surveyor must submit the final survey report within 15 days. "
        "The insurer must communicate approval or settlement offer within 7 days of report receipt. "
        "A compulsory deductible of Rs 1,000 applies to standard private car collision claims."
    )

    doc.add_heading("Section 6.5 Intake Fields", level=2)
    t1 = doc.add_table(rows=1, cols=3)
    h1 = t1.rows[0].cells
    h1[0].text, h1[1].text, h1[2].text = "Field Name", "Requirement", "Description"
    fields = [
        ("Date of Loss", "Mandatory", "Date and time when accident occurred"),
        ("Location of Incident", "Mandatory", "City and specific area of collision"),
        ("Description of Damage", "Mandatory", "Detailed narrative of collision impact"),
        ("Estimated Repair Cost", "Mandatory", "Preliminary repair quote in INR"),
    ]
    if custom_intake_field:
        fields.append((custom_intake_field, "Mandatory", "Vehicle dashcam serial number"))
    for row in fields:
        r = t1.add_row().cells
        r[0].text, r[1].text, r[2].text = row

    doc.add_heading("Section 6.6 Mandatory Documents", level=2)
    t2 = doc.add_table(rows=1, cols=3)
    h2 = t2.rows[0].cells
    h2[0].text, h2[1].text, h2[2].text = "Document / Evidence", "Requirement", "Description"
    docs = [
        ("Repair Estimate", "Mandatory", "Official authorized workshop repair quotation"),
        ("Driving License", "Mandatory", "Valid driving license of driver at wheel"),
        ("Registration Certificate", "Mandatory", "Vehicle registration certificate book"),
        ("Police FIR Copy", "Mandatory for third-party injury", "Police FIR or GD copy"),
    ]
    for row in docs:
        r = t2.add_row().cells
        r[0].text, r[1].text, r[2].text = row

    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()


def test_03_adjuster_knowledge_base_rag_lifecycle(client: TestClient):
    """
    3. Adjuster Knowledge Base Management — Source of Truth RAG:
    - 3.6 Upload .docx Policy Wording & Regulatory Guide.
    - Verify 'policy_regulatory' is normalized to 'regulation'.
    - Verify both auto-published, chunks embedded, requirement_manifest compiled.
    - Update content with custom field (dashcam_footage_serial_number) & re-index: older marked superseded, new published with updated manifest.
    """
    # Log in as Adjuster
    adj_login = client.post("/api/v1/auth/login", json={
        "email": "asha.adjuster@insurance.com",
        "password": "DemoPass123!",
    })
    assert adj_login.status_code == 200, adj_login.text
    adj_token = adj_login.json()["access_token"]
    adj_headers = {"Authorization": f"Bearer {adj_token}"}
    shared["adj_headers"] = adj_headers

    # Upload .docx Policy Wording
    docx_bytes = _build_test_policy_docx()
    up_wording_res = client.post(
        "/api/v1/knowledge/documents/upload",
        headers=adj_headers,
        data={
            "document_type": "policy_wording",
            "insurance_type": "motor",
            "policy_version": "1.0",
            "jurisdiction": "India",
        },
        files={
            "file": ("Motor_Insurance_Policy_Wording.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        },
    )
    assert up_wording_res.status_code == 200, up_wording_res.text
    wording_doc_id = up_wording_res.json()["document_id"]
    shared["wording_doc_id"] = wording_doc_id

    # Upload Regulatory Guide with document_type="policy_regulatory"
    reg_text = (
        "IRDAI Circular 2024 on Claim Settlement Turnaround Timelines:\n\n"
        "1. All motor claims must be assessed within 24 hours by an independent surveyor.\n"
        "2. The final survey report must be rendered within 15 days.\n"
        "3. Insurers must approve or reject the claim within 7 days of survey report receipt.\n"
        "4. Delayed settlement beyond 30 days incurs penal interest at Bank Rate + 2% per annum."
    )
    up_reg_res = client.post(
        "/api/v1/knowledge/documents/upload",
        headers=adj_headers,
        data={
            "document_type": "policy_regulatory",
            "insurance_type": "motor",
            "policy_version": "2024.1",
            "jurisdiction": "India",
        },
        files={
            "file": ("IRDAI_Motor_Regulatory_Guide.txt", reg_text.encode("utf-8"), "text/plain"),
        },
    )
    assert up_reg_res.status_code == 200, up_reg_res.text
    reg_doc_id = up_reg_res.json()["document_id"]

    # Verify DB state directly
    db = TestingSessionLocal()
    try:
        reg_doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == reg_doc_id).first()
        assert reg_doc is not None
        assert reg_doc.document_type == "regulation", f"Expected normalized 'regulation', got {reg_doc.document_type}"
        assert (reg_doc.metadata_json or {}).get("publication_status") == "published"

        wording_doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == wording_doc_id).first()
        assert wording_doc is not None
        assert (wording_doc.metadata_json or {}).get("publication_status") == "published"

        chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == wording_doc_id).all()
        assert len(chunks) > 0, "Expected chunks to be embedded and stored in knowledge_chunks"

        manifest = (wording_doc.metadata_json or {}).get("requirement_manifest") or []
        assert len(manifest) > 0, "Expected non-empty requirement_manifest compiled from .docx tables"
        manifest_keys = [str(r.get("key")) for r in manifest]
        assert any("repair_estimate" in k or "date" in k or "damage" in k for k in manifest_keys)
    finally:
        db.close()

    # Update content with custom field: Dashcam Footage Serial Number
    updated_docx_bytes = _build_test_policy_docx(custom_intake_field="Dashcam Footage Serial Number")
    replace_res = client.put(
        f"/api/v1/knowledge/documents/{wording_doc_id}/content",
        headers=adj_headers,
        data={"insurance_type": "motor", "document_type": "policy_wording"},
        files={
            "file": ("Motor_Insurance_Policy_Wording_v2.docx", updated_docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        },
    )
    assert replace_res.status_code == 200, replace_res.text
    replacement_id = replace_res.json().get("replacement_document_id") or wording_doc_id
    shared["replacement_wording_id"] = replacement_id

    # Re-index updated document
    reindex_res = client.post(f"/api/v1/knowledge/documents/{replacement_id}/reindex", headers=adj_headers)
    assert reindex_res.status_code == 200, reindex_res.text

    # Assert older version superseded and updated is published with custom field in manifest
    db = TestingSessionLocal()
    try:
        old_doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == wording_doc_id).first()
        new_doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == replacement_id).first()
        if old_doc.id != new_doc.id:
            assert (old_doc.metadata_json or {}).get("publication_status") == "superseded"
        assert (new_doc.metadata_json or {}).get("publication_status") == "published"

        new_manifest = (new_doc.metadata_json or {}).get("requirement_manifest") or []
        assert len(new_manifest) > 0
        new_keys = [str(r.get("key")).lower() for r in new_manifest]
        assert any("dashcam" in k for k in new_keys), f"Updated manifest must reflect new rule, got {new_keys}"
    finally:
        db.close()


def test_04_claimant_full_lifecycle(client: TestClient):
    """
    4. Claimant Features:
    - 2.3 Policy Linking: Link admin-created policy & verify in /my-policies.
    - 2.1 AI Chatbot Interaction:
        Turn 1: Pure Policy/Regulatory RAG Q&A (no claim filed yet). Assert motor inference, sources non-empty, grounded.
        Turn 2/3: Conversational claim intake driven by RAG manifest (event_date, event_location, amount, dynamic reqs).
        Evidence Upload: Upload PDF repair estimate with magic bytes.
        Two-Step Confirmation: Submit and verify auto-assignment to active motor adjuster.
    - 2.2 Chat History Management: List chat sessions (no N+1), turns log, transcript export, rename, delete draft.
    """
    # Login as Claimant
    claimant_login = client.post("/api/v1/auth/login", json={
        "email": "riya.claimant@insurance.com",
        "password": "DemoPass123!",
    })
    assert claimant_login.status_code == 200, claimant_login.text
    claimant_token = claimant_login.json()["access_token"]
    claimant_headers = {"Authorization": f"Bearer {claimant_token}"}
    shared["claimant_headers"] = claimant_headers

    # 2.3 Policy Linking
    pol_num = shared.get("created_policy_number", "POL-E2E-MOTOR-999")
    link_res = client.post("/api/v1/policies/link", headers=claimant_headers, json={
        "policy_number": pol_num,
        "policyholder_name": "Riya Claimant",
        "dob": "1994-06-15",
        "phone_last4": "0004",
    })
    assert link_res.status_code == 200, link_res.text
    assert link_res.json()["linked"] is True

    my_pols_res = client.get("/api/v1/policies/my-policies", headers=claimant_headers)
    assert my_pols_res.status_code == 200
    my_pol_nums = [p["policy_number"] for p in my_pols_res.json()]
    assert pol_num in my_pol_nums

    # 2.1 Turn 1: Pure Policy/Regulatory RAG Q&A
    turn1_res = client.post("/api/v1/claims", headers=claimant_headers, json={
        "claim_text": "What documents are required to apply for a new motor policy and what are the IRDAI claim settlement timelines?",
        "input_mode": "text",
    })
    assert turn1_res.status_code == 200, turn1_res.text
    t1_data = turn1_res.json()
    ticket_id = t1_data["ticket_id"]
    shared["ticket_id"] = ticket_id

    # Assert Turn 1 RAG Grounding
    assert t1_data.get("insurance_type") in ("motor", None)
    sources = t1_data.get("sources") or t1_data.get("citations") or []
    assert len(sources) > 0, "Turn 1 Q&A must cite retrieved knowledge sources"
    agent_msg = t1_data.get("agent_message") or t1_data.get("message") or ""
    assert "i don't have a relevant policy" not in agent_msg.lower()
    assert "chunk 0" not in agent_msg.lower()

    # 2.1 Turn 2 & 3: Conversational Intake with RAG manifest
    turn2_res = client.post(f"/api/v1/claims/{ticket_id}/turn", headers=claimant_headers, json={
        "claim_text": (
            f"I want to file a motor collision claim under policy {pol_num}. "
            "On 2026-10-20 in Chennai, my car bumper was damaged in a collision. "
            "Estimated repair cost is Rs 18,500. "
            "Dashcam footage serial number is CAM-2026-99."
        ),
    })
    assert turn2_res.status_code == 200, turn2_res.text
    t2_data = turn2_res.json()
    extracted = t2_data.get("extracted_data") or {}
    assert extracted.get("policy_id") == pol_num
    assert extracted.get("insurance_type") == "motor"
    assert "2026-10-20" in str(extracted.get("event_date"))
    assert "Chennai" in str(extracted.get("event_location"))
    assert float(extracted.get("estimated_claim_amount") or 0) == 18500.0
    assert len(t2_data.get("dynamic_requirements") or []) > 0

    # 2.1 Evidence Uploads
    def _create_test_pdf(text: str) -> bytes:
        import pymupdf
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 50), text)
        b = doc.tobytes()
        doc.close()
        return b

    est_pdf = _create_test_pdf(
        "Official Authorized Workshop Repair Estimate\n"
        "Repair Invoice #EST-9921\n"
        "Estimated Cost: Rs 18,500\n"
        "Parts: Front Bumper Replacement\n"
        "Labor: Rs 3,500\n"
        "Total: Rs 18,500\n"
        "Authorized Signatory"
    )
    dl_pdf = _create_test_pdf(
        "Official Driving Licence\n"
        "Licence Number: DL-2020-001234\n"
        "Name: Riya Claimant\n"
        "Valid Through: 2035-12-31\n"
        "Vehicle Class: LMV Private\n"
        "Issuing Authority: RTO Chennai"
    )
    rc_pdf = _create_test_pdf(
        "Vehicle Registration Certificate (RC)\n"
        "Registration Number: TN-01-AB-1234\n"
        "Owner Name: Riya Claimant\n"
        "Vehicle Make/Model: Honda City\n"
        "Chassis Number: CHASSIS-992193\n"
        "Engine Number: ENG-123891"
    )

    for fn, fcontent, ev_key in [
        ("repair_estimate.pdf", est_pdf, "repair_estimate"),
        ("driving_licence.pdf", dl_pdf, "driving_licence"),
        ("registration_certificate.pdf", rc_pdf, "rc_copy"),
    ]:
        upload_res = client.post(
            f"/api/v1/claims/{ticket_id}/evidence",
            headers=claimant_headers,
            params={"evidence_key": ev_key},
            files={"file": (fn, fcontent, "application/pdf")},
        )
        assert upload_res.status_code == 200, upload_res.text

    # Verify ClaimEvidence row created in DB
    db = TestingSessionLocal()
    try:
        ev_rows = db.query(ClaimEvidence).filter(ClaimEvidence.original_filename == "repair_estimate.pdf").all()
        assert len(ev_rows) > 0, "Expected ClaimEvidence record to be persisted in DB"
    finally:
        db.close()

    # 2.1 Two-Step Confirmation & Auto-Assignment
    confirm_res = client.post(f"/api/v1/claims/{ticket_id}/confirm", headers=claimant_headers, json={
        "confirmed": True,
    })
    assert confirm_res.status_code == 200, confirm_res.text
    conf_data = confirm_res.json()
    assert conf_data["status"] in ("submitted", "assigned")
    assert conf_data.get("assigned_adjuster") is not None or conf_data.get("assigned_adjuster_id") is not None

    # Verify Adjuster workload counter incremented
    db = TestingSessionLocal()
    try:
        c_row = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
        adj_id = (c_row.pipeline_state or {}).get("assigned_adjuster_id")
        assert adj_id is not None
        assigned_adj = db.query(Adjuster).filter(Adjuster.id == adj_id).first()
        assert assigned_adj is not None
        assert (assigned_adj.claims_assigned or 0) >= 1
    finally:
        db.close()

    # 2.2 Chat History Management
    list_claims_res = client.get("/api/v1/claims", headers=claimant_headers)
    claims_data = list_claims_res.json()
    claims_list = claims_data.get("items", claims_data) if isinstance(claims_data, dict) else claims_data
    assert any(c["ticket_id"] == ticket_id for c in claims_list)

    turns_res = client.get(f"/api/v1/claims/{ticket_id}/turns", headers=claimant_headers)
    assert turns_res.status_code == 200
    assert len(turns_res.json()["turns"]) >= 2

    export_res = client.get(f"/api/v1/claims/{ticket_id}/export", headers=claimant_headers)
    assert export_res.status_code == 200
    assert "formatted_text" in export_res.json()

    # Create draft, rename and delete
    draft_init = client.post("/api/v1/claims", headers=claimant_headers, json={
        "claim_text": "Draft session to test deletion",
    })
    assert draft_init.status_code == 200
    draft_ticket = draft_init.json()["ticket_id"]

    rename_res = client.patch(f"/api/v1/claims/{draft_ticket}", headers=claimant_headers, json={
        "event_description": "Renamed Draft Description",
    })
    assert rename_res.status_code == 200

    del_res = client.delete(f"/api/v1/claims/{draft_ticket}", headers=claimant_headers)
    assert del_res.status_code == 200


def test_05_adjuster_copilot_request_loop_and_decisioning(client: TestClient):
    """
    5. Adjuster Features & Claimant Request-Response Loop:
    - 3.1 Adjuster Dashboard & Queue: claim in assigned queue.
    - 3.3 Policy Database Lookup: policyholder name, validity, coverage, deductible.
    - 3.5 AI Copilot Assistance: Grounded report, cached second call in <50ms (0 extra tokens), copilot chat with citations.
    - 3.4 Adjuster Request <-> 2.5 Claimant Response Loop: request extra info -> pending_evidence -> claimant responds with note/file -> under_review.
    - 3.2 Final Human Decisioning: approve claim, approved_amount, audit trail, claimant real-time tracking reflects approved status.
    """
    claimant_headers = shared["claimant_headers"]
    ticket_id = shared["ticket_id"]
    pol_num = shared.get("created_policy_number", "POL-E2E-MOTOR-999")

    # Log in as the specifically assigned adjuster
    db = TestingSessionLocal()
    try:
        c_row = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
        adj_id = (c_row.pipeline_state or {}).get("assigned_adjuster_id")
        assigned_adj = db.query(Adjuster).filter(Adjuster.id == adj_id).first()
        user_row = db.query(User).filter(User.id == assigned_adj.user_id).first()
        assigned_email = user_row.email
    finally:
        db.close()

    adj_login = client.post("/api/v1/auth/login", json={
        "email": assigned_email,
        "password": "DemoPass123!",
    })
    assert adj_login.status_code == 200, adj_login.text
    adj_headers = {"Authorization": f"Bearer {adj_login.json()['access_token']}"}

    # 3.1 Adjuster Dashboard & Queue
    dash_res = client.get("/api/v1/adjuster/dashboard", headers=adj_headers)
    assert dash_res.status_code == 200, dash_res.text

    queue_res = client.get("/api/v1/adjuster/queue?scope=all", headers=adj_headers)
    assert queue_res.status_code == 200, queue_res.text
    queue_tickets = [it["ticket_id"] for it in queue_res.json()["items"]]
    assert ticket_id in queue_tickets

    # 3.3 Policy Database Lookup
    lookup_res = client.get(f"/api/v1/adjuster/policies?query={pol_num}", headers=adj_headers)
    assert lookup_res.status_code == 200, lookup_res.text
    policies_found = lookup_res.json()["items"]
    assert len(policies_found) > 0
    matched_pol = next((p for p in policies_found if p["policy_number"] == pol_num), policies_found[0])
    assert matched_pol["policyholder_name"] == "Riya Claimant"
    assert matched_pol["coverage_amount"] == 2000000.0
    assert matched_pol["deductible"] == 5000.0
    assert matched_pol["effective_date"] is not None and matched_pol["expiry_date"] is not None

    # 3.5 AI Copilot Analysis Generation
    copilot_res1 = client.get(f"/api/v1/adjuster/claims/{ticket_id}/copilot?refresh=true", headers=adj_headers)
    assert copilot_res1.status_code == 200, copilot_res1.text
    c1 = copilot_res1.json()
    assert c1["status"] == "ready"
    analysis = c1["analysis"]
    assert "executive_summary" in analysis
    assert "decision_recommendation" in analysis
    assert "actionable_suggestions" in analysis
    assert "coverage_observations" in analysis
    assert "citations" in analysis
    assert "fraud_score" in analysis or "risk_flags" in analysis

    # 3.5 Cached Copilot Call SLA (<50ms)
    t0_cache = time.perf_counter()
    copilot_res2 = client.get(f"/api/v1/adjuster/claims/{ticket_id}/copilot", headers=adj_headers)
    elapsed_cache = time.perf_counter() - t0_cache
    assert copilot_res2.status_code == 200
    assert copilot_res2.json().get("cached") is True
    assert elapsed_cache < 0.050, f"Cached copilot latency {elapsed_cache*1000:.2f}ms exceeded 50ms SLA target."

    # 3.5 Copilot Chat
    chat_res = client.post(f"/api/v1/adjuster/claims/{ticket_id}/copilot/chat", headers=adj_headers, json={
        "message": "Are there any policy exclusions or IRDAI timelines I should check before approving?",
    })
    assert chat_res.status_code == 200, chat_res.text
    chat_data = chat_res.json()
    assert "answer" in chat_data and len(chat_data["answer"]) > 10
    assert len(chat_data.get("citations", [])) > 0 or len(chat_data.get("sources", [])) > 0

    # 3.4 Adjuster Request Additional Info Loop
    req_res = client.post(f"/api/v1/adjuster/claims/{ticket_id}/request-info", headers=adj_headers, json={
        "request_text": "Please upload clear photos of the damaged bumper and FIR/GD copy.",
    })
    assert req_res.status_code == 200, req_res.text
    req_data = req_res.json()
    req_id = req_data["id"]

    # Claimant tracks claim and sees open request
    claimant_view = client.get(f"/api/v1/claims/{ticket_id}", headers=claimant_headers)
    assert claimant_view.status_code == 200
    cv_data = claimant_view.json()
    assert cv_data["status"] == "pending_evidence"
    assert cv_data.get("pending_request") is not None or len(cv_data.get("evidence_requests", [])) > 0

    # Claimant responds with document & note
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    respond_res = client.post(
        f"/api/v1/claims/{ticket_id}/evidence-requests/{req_id}/respond",
        headers=claimant_headers,
        data={"response_note": "Attached damaged bumper photograph and local GD entry copy."},
        files={"file": ("bumper_photo.png", png_bytes, "image/png")},
    )
    assert respond_res.status_code == 200, respond_res.text
    assert respond_res.json()["request"]["status"] == "responded"

    # Assert claim status automatically transitioned back to 'under_review'
    cv_after_resp = client.get(f"/api/v1/claims/{ticket_id}", headers=claimant_headers)
    assert cv_after_resp.json()["status"] == "under_review"

    # 3.2 Final Decisioning
    decision_res = client.post(f"/api/v1/adjuster/claims/{ticket_id}/decision", headers=adj_headers, json={
        "decision": "approve",
        "approved_amount": 17500.0,
        "notes": "Verified policy coverage and repair estimate less compulsory Rs 1,000 deductible.",
    })
    assert decision_res.status_code == 200, decision_res.text
    dec_data = decision_res.json()
    assert dec_data["decision"] == "approve"
    assert dec_data["status"] == "approved"

    # Verify Claimant real-time tracking reflects approved status & audit record
    final_claimant_view = client.get(f"/api/v1/claims/{ticket_id}", headers=claimant_headers)
    assert final_claimant_view.status_code == 200
    assert final_claimant_view.json()["status"] == "approved"

    db = TestingSessionLocal()
    try:
        dec_row = db.query(ClaimDecision).filter(ClaimDecision.claim_id == shared["ticket_id"]).first()
        if not dec_row:
            # check by string claim ticket
            c = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
            dec_row = db.query(ClaimDecision).filter(ClaimDecision.claim_id == c.id).first()
        assert dec_row is not None
        assert dec_row.decision == "approve"
        assert float(dec_row.approved_amount) == 17500.0
    finally:
        db.close()
