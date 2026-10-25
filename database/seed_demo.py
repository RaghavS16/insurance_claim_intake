import os
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
_backend_path = _repo_root / "backend"
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

import secrets
import uuid
import hashlib
from datetime import date, datetime, timezone

from database._db_helpers import SessionLocal
from src.database.models import User, Policy, Adjuster, Claim, ConversationTurn, KnowledgeDocument, KnowledgeChunk
from src.database.hardening_models import Tenant, TenantMembership, ClaimAssignment, ClaimSubmission, ClaimEvidenceRequest
from src.utils.auth import get_password_hash
from src.knowledge.embeddings import embed_documents
from src.storage.s3 import put_bytes

TENANT_ID = "00000000-0000-0000-0000-000000000001"
USERS = [
    ("00000000-0000-0000-0000-000000000101", "Ops Admin", "admin@insurance.com", "ADMIN", "9876500001"),
    ("00000000-0000-0000-0000-000000000102", "Asha Adjuster", "asha.adjuster@insurance.com", "ADJUSTER", "9876500002"),
    ("00000000-0000-0000-0000-000000000103", "Vikram Adjuster", "vikram.adjuster@insurance.com", "ADJUSTER", "9876500003"),
    ("00000000-0000-0000-0000-000000000104", "Riya Claimant", "riya.claimant@insurance.com", "CLAIMANT", "9876500004"),
    ("00000000-0000-0000-0000-000000000105", "Meera Adjuster", "meera.adjuster@insurance.com", "ADJUSTER", "9876500005"),
    ("00000000-0000-0000-0000-000000000106", "Rajesh Adjuster", "rajesh.adjuster@insurance.com", "ADJUSTER", "9876500006"),
    ("00000000-0000-0000-0000-000000000107", "Priya Adjuster", "priya.adjuster@insurance.com", "ADJUSTER", "9876500007"),
    ("00000000-0000-0000-0000-000000000108", "Arjun Adjuster", "arjun.adjuster@insurance.com", "ADJUSTER", "9876500008"),
    ("00000000-0000-0000-0000-000000000109", "Dev Adjuster", "dev.adjuster@insurance.com", "ADJUSTER", "9876500009"),
]

def seed_demo():
    env = (os.getenv("ENVIRONMENT") or "development").lower().strip()
    if env in ("production", "staging", "prod"):
        sys.exit("Error: seed_demo is strictly forbidden in production or staging environments.")

    demo_password = os.getenv("DEMO_PASSWORD") or ("DemoPass123!" if env not in ("prod", "production") else None)
    if not demo_password:
        sys.exit("Error: DEMO_PASSWORD environment variable is required to run seed_demo.")

    db=SessionLocal()
    try:
        tenant=db.query(Tenant).filter(Tenant.id==TENANT_ID).first()
        if not tenant:
            tenant=Tenant(id=TENANT_ID,name="InsureClaim Demo Tenant",status="active")
            db.add(tenant)
            db.flush()

        users={}
        for uid,name,email,role,phone in USERS:
            user=db.query(User).filter(User.id==uid).first()
            if not user:
                user=User(id=uid,tenant_id=TENANT_ID,full_name=name,email=email,phone=phone,password_hash=get_password_hash(demo_password),role=role,status="active",email_verified_at=datetime.now(timezone.utc))
                db.add(user)
                db.flush()
            else:
                user.tenant_id=TENANT_ID; user.role=role; user.status="active"; user.password_hash=get_password_hash(demo_password); user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
            users[role,email]=user
            if not db.query(TenantMembership).filter(TenantMembership.tenant_id==TENANT_ID,TenantMembership.user_id==uid).first():
                db.add(TenantMembership(tenant_id=TENANT_ID,user_id=uid,role=role,status="active"))

        adjusters=[
            ("00000000-0000-0000-0000-000000000102","Asha Adjuster","asha.adjuster@insurance.com","9876500002","motor"),
            ("00000000-0000-0000-0000-000000000103","Vikram Adjuster","vikram.adjuster@insurance.com","9876500003","health"),
            ("00000000-0000-0000-0000-000000000105","Meera Adjuster","meera.adjuster@insurance.com","9876500005","senior_citizen_health"),
            ("00000000-0000-0000-0000-000000000106","Rajesh Adjuster","rajesh.adjuster@insurance.com","9876500006","home"),
            ("00000000-0000-0000-0000-000000000107","Priya Adjuster","priya.adjuster@insurance.com","9876500007","travel"),
            ("00000000-0000-0000-0000-000000000108","Arjun Adjuster","arjun.adjuster@insurance.com","9876500008","cyber"),
            ("00000000-0000-0000-0000-000000000109","Dev Adjuster","dev.adjuster@insurance.com","9876500009","all"),
        ]
        for uid,name,email,phone,spec in adjusters:
            row=db.query(Adjuster).filter(Adjuster.id==uid).first()
            if not row:
                db.add(Adjuster(id=uid,user_id=uid,tenant_id=TENANT_ID,name=name,email=email,phone=phone,specialization=spec,claims_assigned=0,is_active=True))

        claimant=users[("CLAIMANT","riya.claimant@insurance.com")]
        policies=[
            ("POL-DEMO-MOTOR-001","motor",1500000,10000,date(2026,1,1),date(2027,1,1),"Riya Claimant",date(1994,6,15),"9876500004","riya.claimant@insurance.com"),
            ("POL-DEMO-HEALTH-001","health",800000,5000,date(2026,1,1),date(2027,1,1),"Riya Claimant",date(1994,6,15),"9876500004","riya.claimant@insurance.com"),
            ("POL-DEMO-SENIOR-001","senior_citizen_health",500000,10000,date(2026,1,1),date(2027,1,1),"Riya Claimant",date(1960,3,10),"9876500004","riya.claimant@insurance.com"),
            ("POL-DEMO-HOME-001","home",5000000,25000,date(2026,1,1),date(2027,1,1),"Riya Claimant",date(1994,6,15),"9876500004","riya.claimant@insurance.com"),
            ("POL-DEMO-TRAVEL-001","travel",2000000,2500,date(2026,1,1),date(2027,1,1),"Riya Claimant",date(1994,6,15),"9876500004","riya.claimant@insurance.com"),
            ("POL-DEMO-CYBER-001","cyber",1000000,5000,date(2026,1,1),date(2027,1,1),"Riya Claimant",date(1994,6,15),"9876500004","riya.claimant@insurance.com"),
        ]
        for number,ptype,coverage,deductible,eff,exp,name,dob,phone,email in policies:
            row=db.query(Policy).filter(Policy.policy_number==number).first()
            linked_cid = claimant.id
            linked_ts = datetime.now(timezone.utc)
            if not row:
                row=Policy(id=str(uuid.uuid4()),tenant_id=TENANT_ID,policy_number=number,customer_id=linked_cid,policy_type=ptype,coverage_amount=coverage,deductible=deductible,effective_date=eff,expiry_date=exp,is_active=True,policyholder_name=name,policyholder_dob=dob,policyholder_phone=phone,policyholder_email=email,policyholder_phone_last4=phone[-4:],linked_at=linked_ts,link_attempts=0)
                db.add(row)
            elif not row.customer_id:
                row.customer_id = claimant.id
                row.linked_at = datetime.now(timezone.utc)
        # Published demo RAG sources make the sample environment immediately useful.
        demo_sources = [
            (
                "demo-motor-policy-wording.txt",
                "policy_wording",
                "motor",
                "DEMO-MOTOR-1.0",
                "Demo Motor Policy, Section 4, Clause 4.1",
                """DEMO POLICY WORDING — NOT AN ACTUAL INSURANCE CONTRACT.
Section 4. Motor Own-Damage Claims
Clause 4.1: A covered accidental collision may be reported for claim review when the incident occurs during the policy validity period.
Clause 4.2: The claimant should provide the incident date, location, a description of the damage, and available repair estimates or garage quotations.
Clause 4.3: The applicable deductible is applied to an approved covered loss. Final coverage and settlement remain subject to policy verification and adjuster review.
Clause 4.4: The insurer may request additional evidence when the submitted material is insufficient to establish the loss.
""",
            ),
            (
                "demo-claims-guidance.txt",
                "regulation",
                "motor",
                "DEMO-GUIDANCE-1.0",
                "Demo Claims Guidance, Section 2, Clause 2.1",
                """DEMO REGULATORY/PROCESS GUIDANCE — VERIFY AGAINST LIVE REGULATOR MATERIAL BEFORE PRODUCTION.
Section 2. Claims handling
Clause 2.1: Claim communications should identify the claim reference and clearly state any additional information required from the claimant.
Clause 2.2: Evidence requests should be recorded against the claim and the claimant should be able to respond with a note and supporting document.
Clause 2.3: Claim decisions should be recorded by an authorized human reviewer with a reason and supporting evidence.
""",
            ),
            (
                "demo-health-policy-wording.txt",
                "policy_wording",
                "health",
                "DEMO-HEALTH-1.0",
                "Demo Health Policy, Section 3, Clause 3.1",
                """DEMO HEALTH POLICY WORDING — NOT AN ACTUAL INSURANCE CONTRACT.
Section 3. Inpatient Hospitalization Claims
Clause 3.1: To submit an inpatient medical claim, the claimant must specify the active Health Policy Number for verification.
Clause 3.2: The claimant must provide the hospital name, hospital admission date, treating doctor or diagnosis description, and estimated hospital bills or treatment expense.
Clause 3.3: Inpatient admission must exceed 24 hours unless daycare procedures apply. A standard copayment or deductible applies to eligible room and pharmacy charges.
Clause 3.4: The claimant must furnish a copy of the hospital discharge summary and original medical receipts before claim settlement.
""",
            ),
        ]
        for filename, doc_type, insurance_type, version, citation, body in demo_sources:
            existing = db.query(KnowledgeDocument).filter(
                KnowledgeDocument.source_name == filename,
                KnowledgeDocument.tenant_id == TENANT_ID,
            ).first()
            if not existing:
                try:
                    vector = embed_documents([body])[0]
                    staged = put_bytes(
                        body.encode("utf-8"),
                        prefix="knowledge-demo",
                        filename=filename,
                        content_type="text/plain",
                    )
                    doc = KnowledgeDocument(
                        id=str(uuid.uuid4()),
                        source_name=filename,
                        source_uri=staged["uri"],
                        document_type=doc_type,
                        insurance_type=insurance_type,
                        content_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
                        tenant_id=TENANT_ID,
                        jurisdiction="India",
                        document_version=version,
                        uploaded_by=users[("ADJUSTER", "asha.adjuster@insurance.com")].id,
                        metadata_json={
                            "title": filename,
                            "policy_version": version,
                            "publication_status": "published",
                            "effective_from": "2026-01-01",
                            "effective_to": "2027-01-01",
                            "demo_source": True,
                            **(
                                {
                                    "requirement_manifest_version": 1,
                                    "requirement_manifest": [
                                        {"key": "policy_number", "label": "Policy Number", "question_hint": "Could you provide your Motor Policy Number to verify coverage?", "required": True, "evidence_type": None, "canonical_role": "policy_id", "citation_label": citation},
                                        {"key": "incident_date", "label": "Incident Date", "question_hint": "On what date did the collision or incident occur?", "required": True, "evidence_type": None, "canonical_role": "event_date", "citation_label": citation},
                                        {"key": "incident_location", "label": "Incident Location", "question_hint": "Where did the motor accident take place?", "required": True, "evidence_type": None, "canonical_role": "event_location", "citation_label": citation},
                                        {"key": "damage_description", "label": "Description of Damage", "question_hint": "Could you describe how the collision happened and the vehicle damage?", "required": True, "evidence_type": None, "canonical_role": "event_description", "citation_label": citation},
                                        {"key": "repair_estimate_amount", "label": "Repair Estimate Amount", "question_hint": "What is the estimated repair cost or garage quotation amount?", "required": True, "evidence_type": None, "canonical_role": "estimated_claim_amount", "citation_label": citation},
                                        {"key": "repair_quotation_document", "label": "Repair Estimate / Garage Quotation", "question_hint": "Please upload a copy of the repair estimate or garage quotation.", "required": True, "evidence_type": "document", "canonical_role": None, "citation_label": citation},
                                    ],
                                }
                                if insurance_type == "motor" and doc_type == "policy_wording"
                                else (
                                    {
                                        "requirement_manifest_version": 1,
                                        "requirement_manifest": [
                                            {"key": "policy_number", "label": "Health Policy Number", "question_hint": "Could you provide your active Health Policy Number for verification?", "required": True, "evidence_type": None, "canonical_role": "policy_id", "citation_label": citation},
                                            {"key": "hospital_name", "label": "Hospital Name", "question_hint": "Which hospital were you admitted to for treatment?", "required": True, "evidence_type": None, "canonical_role": "event_location", "citation_label": citation},
                                            {"key": "hospital_admission_date", "label": "Hospital Admission Date", "question_hint": "What was the date of inpatient hospital admission?", "required": True, "evidence_type": None, "canonical_role": "event_date", "citation_label": citation},
                                            {"key": "diagnosis_description", "label": "Diagnosis & Treatment Details", "question_hint": "What was the diagnosis or treatment described by the attending doctor?", "required": True, "evidence_type": None, "canonical_role": "event_description", "citation_label": citation},
                                            {"key": "estimated_hospital_bills", "label": "Estimated Hospital Bills", "question_hint": "What is the total estimated hospital bill or medical expense?", "required": True, "evidence_type": None, "canonical_role": "estimated_claim_amount", "citation_label": citation},
                                            {"key": "discharge_summary_and_receipts", "label": "Hospital Discharge Summary & Medical Receipts", "question_hint": "Please upload a copy of your hospital discharge summary and original medical receipts.", "required": True, "evidence_type": "document", "canonical_role": None, "citation_label": citation},
                                        ],
                                    }
                                    if insurance_type == "health" and doc_type == "policy_wording"
                                    else {}
                                )
                            ),
                        },
                    )
                    db.add(doc)
                    db.flush()
                    db.add(KnowledgeChunk(
                        id=str(uuid.uuid4()),
                        document_id=doc.id,
                        chunk_index=0,
                        text=body,
                        embedding=vector,
                        tenant_id=TENANT_ID,
                        page_number=1,
                        section_number=citation.split(",")[1].strip() if "," in citation else None,
                        clause_number=citation.split(",")[-1].strip() if "," in citation else None,
                        citation_label=citation,
                        metadata_json={"source_name": filename, "demo_source": True},
                    ))
                    db.commit()
                except Exception as exc:
                    db.rollback()
                    print(f"Warning: demo knowledge source '{filename}' could not be indexed: {type(exc).__name__}: {exc}")

        # Authoritative docrag/ source of truth ingestion (12 Indian IRDAI .docx across 6 lines)
        from src.knowledge.store import ingest_document
        candidate_dirs = [
            Path(os.getenv("DOCRAG_DIR", "")),
            Path(r"C:\Users\ragha\Desktop\docrag"),
            _repo_root / "database" / "docrag",
            _repo_root / "docrag",
        ]
        docrag_dir = next((d for d in candidate_dirs if d and d.exists() and list(d.glob("*.docx"))), None)

        if docrag_dir and docrag_dir.exists():
            for docx_file in sorted(docrag_dir.glob("*.docx")):
                fname = docx_file.name
                existing_doc = db.query(KnowledgeDocument).filter(
                    KnowledgeDocument.source_name == fname,
                    KnowledgeDocument.tenant_id == TENANT_ID,
                ).first()
                if not existing_doc:
                    try:
                        content_bytes = docx_file.read_bytes()
                        ingest_document(
                            content=content_bytes,
                            filename=fname,
                            uploaded_by=users[("ADMIN", "admin@insurance.com")].id,
                            tenant_id=TENANT_ID,
                            publication_status="published",
                            jurisdiction="India",
                        )
                        print(f"Successfully ingested authoritative docrag: {fname}")
                    except Exception as exc:
                        print(f"Warning: could not ingest '{fname}': {type(exc).__name__}: {exc}")

        motor_policy = db.query(Policy).filter(Policy.policy_number == "POL-DEMO-MOTOR-001", Policy.tenant_id == TENANT_ID).first()
        asha = db.query(Adjuster).filter(Adjuster.id == "00000000-0000-0000-0000-000000000102", Adjuster.tenant_id == TENANT_ID).first()
        demo_claim = db.query(Claim).filter(Claim.ticket_id == "CLM-DEMO-MOTOR-001", Claim.tenant_id == TENANT_ID).first()
        if motor_policy and asha:
            if not demo_claim:
                demo_claim = Claim(
                    id=str(uuid.uuid4()),
                    tenant_id=TENANT_ID,
                    ticket_id="CLM-DEMO-MOTOR-001",
                    claimant_id=claimant.id,
                    customer_id=claimant.id,
                    policy_id=motor_policy.id,
                    claim_date=date(2026, 9, 20),
                    event_date=date(2026, 9, 18),
                    insurance_type="motor",
                    input_mode="text",
                    event_description="Rear-end collision at a city intersection; no injuries reported.",
                    event_location="Chennai, Tamil Nadu",
                    estimated_claim_amount=125000,
                    extraction_confidence=0.99,
                    validation_status="verified",
                    status="under_review",
                    conversation_status="submitted",
                    pipeline_state={
                        "extracted_data": {
                            "policy_id": motor_policy.policy_number,
                            "insurance_type": "motor",
                            "event_date": "2026-09-18",
                            "event_description": "Rear-end collision at a city intersection; no injuries reported.",
                            "event_location": "Chennai, Tamil Nadu",
                            "estimated_claim_amount": 125000,
                        },
                        "policy_verification": {"valid": True, "policy_number": motor_policy.policy_number},
                        "assigned_adjuster_id": asha.id,
                        "assigned_adjuster_name": asha.name,
                        "conversation_phase": "5_submitted",
                    },
                    state_version=1,
                )
                db.add(demo_claim)
                db.flush()
                db.add(ClaimSubmission(
                    claim_id=demo_claim.id,
                    tenant_id=TENANT_ID,
                    idempotency_key="demo-submission-clm-demo-motor-001",
                    status="accepted",
                    submitted_by=claimant.id,
                    result_json={"demo": True, "ticket_id": demo_claim.ticket_id, "adjuster_id": asha.id},
                ))
                db.add(ConversationTurn(
                    claim_id=demo_claim.id,
                    turn_number=1,
                    speaker="user",
                    text="I had a rear-end collision and need to file a motor claim.",
                ))
                db.add(ConversationTurn(
                    claim_id=demo_claim.id,
                    turn_number=2,
                    speaker="agent",
                    text="I have recorded the incident details and submitted the claim for adjuster review.",
                ))
            if demo_claim:
                ps = dict(demo_claim.pipeline_state or {})
                ps["assigned_adjuster_id"] = asha.id
                ps["assigned_adjuster_name"] = asha.name
                demo_claim.pipeline_state = ps
                demo_claim.status = "under_review"
            assignment = db.query(ClaimAssignment).filter(
                ClaimAssignment.claim_id == demo_claim.id,
                ClaimAssignment.tenant_id == TENANT_ID,
                ClaimAssignment.adjuster_id == asha.id,
                ClaimAssignment.is_active.is_(True),
            ).first()
            if not assignment:
                db.add(ClaimAssignment(
                    claim_id=demo_claim.id,
                    tenant_id=TENANT_ID,
                    adjuster_id=asha.id,
                    assigned_by=users[("ADMIN", "admin@insurance.com")].id,
                    reason="Deterministic demo assignment",
                    is_active=True,
                ))
            asha.claims_assigned = max(1, int(asha.claims_assigned or 0))
            request_row = db.query(ClaimEvidenceRequest).filter(
                ClaimEvidenceRequest.claim_id == demo_claim.id,
                ClaimEvidenceRequest.tenant_id == TENANT_ID,
                ClaimEvidenceRequest.status == "open",
            ).first()
            if not request_row:
                db.add(ClaimEvidenceRequest(
                    claim_id=demo_claim.id,
                    tenant_id=TENANT_ID,
                    adjuster_id=asha.id,
                    request_text="Please provide the vehicle repair estimate or garage quotation for the reported damage.",
                    status="open",
                ))
                demo_claim.status = "pending_evidence"
        db.commit()
        print("Demo seed complete.")
        print(f"Tenant: {TENANT_ID}")
        print(f"Demo password for seeded users: {demo_password}")
        print("Admin: admin@insurance.com")
        print("Adjuster 1: asha.adjuster@insurance.com")
        print("Adjuster 2: vikram.adjuster@insurance.com")
        print("Claimant: riya.claimant@insurance.com")
        print("Policies: POL-DEMO-MOTOR-001, POL-DEMO-HEALTH-001")
    finally:
        db.close()

if __name__ == "__main__":
    seed_demo()
