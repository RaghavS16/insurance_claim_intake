"""
Production Database Initialization and Seeding Script.

Initializes production database with:
1. Default Tenant Workspace (if not present)
2. 2 Claimants with verified active accounts
3. 6 Adjusters (exactly 1 from each canonical type: motor, health, senior_health, home, travel, cyber)
4. 10 Realistic Master Insurance Policies across the 6 canonical lines:
   - Policies 1-4: Linked to Claimant 1 (Aarav Patel)
   - Policies 5-8: Linked to Claimant 2 (Ananya Verma)
   - Policies 9-10: Unlinked master policies with matching PII for live verification/linking testing
5. Ingestion of authoritative RAG documents from docrag/ (12 IRDAI docs across all 6 lines),
   attributed directly to the respective specialist Adjusters (knowledge management is adjuster-managed)
6. Admin creation is completely skipped (managed independently via seed_admin.py / create_admin.py)

Supports idempotent execution: safe to run multiple times without duplicating or corrupting data.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path Bootstrap
# ---------------------------------------------------------------------------
_this_file = Path(__file__).resolve()
_repo_root = _this_file.parent if (_this_file.parent / "backend").exists() else _this_file.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

_backend_path = _repo_root / "backend"
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

if "/app" not in sys.path:
    sys.path.insert(0, "/app")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("seed_initialization")

from src.database.session import SessionLocal
from src.database.models import User, Policy, Adjuster, KnowledgeDocument, KnowledgeChunk
from src.database.hardening_models import Tenant, TenantMembership
from src.utils.auth import get_password_hash
from src.utils.validators import validate_password_strength, validate_email
from src.knowledge.store import ingest_document

# ---------------------------------------------------------------------------
# Configuration Constants
# ---------------------------------------------------------------------------
DEFAULT_TENANT_ID = os.getenv("TENANT_ID", "00000000-0000-0000-0000-000000000001")
DEFAULT_TENANT_NAME = os.getenv("TENANT_NAME", "IntelliClaim Production")

DEFAULT_PASSWORD = os.getenv("SEED_USER_PASSWORD", "InitPass2026!")

# Canonical 6 Adjuster specializations
CANONICAL_ADJUSTER_SPECS = [
    "motor",
    "health",
    "senior_health",
    "home",
    "travel",
    "cyber",
]

DOCRAG_METADATA_MAP: Dict[str, Tuple[str, str]] = {
    "Motor_Insurance_Policy_Regulatory.docx": ("regulation", "motor"),
    "Motor_Insurance_Policy_Wording.docx": ("policy_wording", "motor"),
    "Health_Insurance_Policy_Regulatory.docx": ("regulation", "health"),
    "Health_Insurance_Policy_Wording.docx": ("policy_wording", "health"),
    "Senior_Citizen_Health_Insurance_Policy_Regulatory.docx": ("regulation", "senior_health"),
    "Senior_Citizen_Health_Insurance_Policy_Wording.docx": ("policy_wording", "senior_health"),
    "Home_Insurance_Policy_Regulatory.docx": ("regulation", "home"),
    "Home_Insurance_Policy_Wording.docx": ("policy_wording", "home"),
    "Travel_Insurance_Policy_Regulatory.docx": ("regulation", "travel"),
    "Travel_Insurance_Policy_Wording.docx": ("policy_wording", "travel"),
    "Cyber_Insurance_Policy_Regulatory.docx": ("regulation", "cyber"),
    "Cyber_Insurance_Policy_Wording.docx": ("policy_wording", "cyber"),
}


def ensure_tenant(db: Any) -> Tenant:
    """Ensure a workspace tenant exists for multi-tenant isolation."""
    tenant = db.query(Tenant).filter(Tenant.id == DEFAULT_TENANT_ID).first()
    if not tenant:
        # Check if any tenant exists in db
        tenant = db.query(Tenant).first()
    if not tenant:
        tenant = Tenant(
            id=DEFAULT_TENANT_ID,
            name=DEFAULT_TENANT_NAME,
            status="active",
        )
        db.add(tenant)
        db.flush()
        logger.info("Created production tenant: '%s' (%s)", tenant.name, tenant.id)
    else:
        logger.info("Using existing tenant: '%s' (%s)", tenant.name, tenant.id)
    return tenant


def seed_claimants(db: Any, tenant_id: str, default_password_hash: str) -> List[User]:
    """Seed 2 production claimants with verified active accounts."""
    claimant_defs = [
        {
            "id": "00000000-0000-0000-0000-000000000201",
            "name": os.getenv("CLAIMANT_1_NAME", "Aarav Patel"),
            "email": validate_email(os.getenv("CLAIMANT_1_EMAIL", "claimant1@insurance.com")),
            "phone": os.getenv("CLAIMANT_1_PHONE", "9876540001"),
            "dob": date(1990, 5, 15),
        },
        {
            "id": "00000000-0000-0000-0000-000000000202",
            "name": os.getenv("CLAIMANT_2_NAME", "Ananya Verma"),
            "email": validate_email(os.getenv("CLAIMANT_2_EMAIL", "claimant2@insurance.com")),
            "phone": os.getenv("CLAIMANT_2_PHONE", "9876540002"),
            "dob": date(1962, 8, 20),
        },
    ]

    seeded_claimants: List[User] = []
    now_utc = datetime.now(timezone.utc)

    for cdef in claimant_defs:
        user = db.query(User).filter(User.email == cdef["email"]).first()
        if not user:
            user = db.query(User).filter(User.id == cdef["id"]).first()

        if not user:
            user = User(
                id=cdef["id"],
                tenant_id=tenant_id,
                full_name=cdef["name"],
                email=cdef["email"],
                phone=cdef["phone"],
                password_hash=default_password_hash,
                role="CLAIMANT",
                status="active",
                email_verified_at=now_utc,
            )
            db.add(user)
            db.flush()
            logger.info("Created Claimant: '%s' <%s>", user.full_name, user.email)
        else:
            user.tenant_id = tenant_id
            user.role = "CLAIMANT"
            user.status = "active"
            if not user.email_verified_at:
                user.email_verified_at = now_utc
            logger.info("Claimant already exists: '%s' <%s>", user.full_name, user.email)

        # Ensure TenantMembership
        membership = db.query(TenantMembership).filter(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user.id,
        ).first()
        if not membership:
            db.add(TenantMembership(tenant_id=tenant_id, user_id=user.id, role="CLAIMANT", status="active"))

        seeded_claimants.append(user)

    db.commit()
    return seeded_claimants


def seed_adjusters(db: Any, tenant_id: str, default_password_hash: str) -> List[Adjuster]:
    """
    Seed 6 adjusters, exactly 1 for each canonical specialization:
    motor, health, senior_health, home, travel, cyber.
    """
    adjuster_defs = [
        {
            "id": "00000000-0000-0000-0000-000000000301",
            "spec": "motor",
            "name": os.getenv("ADJUSTER_MOTOR_NAME", "Aarush Motor"),
            "email": validate_email(os.getenv("ADJUSTER_MOTOR_EMAIL", "motor.adjuster@insurance.com")),
            "phone": os.getenv("ADJUSTER_MOTOR_PHONE", "9876530001"),
        },
        {
            "id": "00000000-0000-0000-0000-000000000302",
            "spec": "health",
            "name": os.getenv("ADJUSTER_HEALTH_NAME", "Bhavna Health"),
            "email": validate_email(os.getenv("ADJUSTER_HEALTH_EMAIL", "health.adjuster@insurance.com")),
            "phone": os.getenv("ADJUSTER_HEALTH_PHONE", "9876530002"),
        },
        {
            "id": "00000000-0000-0000-0000-000000000303",
            "spec": "senior_health",
            "name": os.getenv("ADJUSTER_SENIOR_NAME", "Chetan Senior"),
            "email": validate_email(os.getenv("ADJUSTER_SENIOR_EMAIL", "senior.adjuster@insurance.com")),
            "phone": os.getenv("ADJUSTER_SENIOR_PHONE", "9876530003"),
        },
        {
            "id": "00000000-0000-0000-0000-000000000304",
            "spec": "home",
            "name": os.getenv("ADJUSTER_HOME_NAME", "Deepa Home"),
            "email": validate_email(os.getenv("ADJUSTER_HOME_EMAIL", "home.adjuster@insurance.com")),
            "phone": os.getenv("ADJUSTER_HOME_PHONE", "9876530004"),
        },
        {
            "id": "00000000-0000-0000-0000-000000000305",
            "spec": "travel",
            "name": os.getenv("ADJUSTER_TRAVEL_NAME", "Esha Travel"),
            "email": validate_email(os.getenv("ADJUSTER_TRAVEL_EMAIL", "travel.adjuster@insurance.com")),
            "phone": os.getenv("ADJUSTER_TRAVEL_PHONE", "9876530005"),
        },
        {
            "id": "00000000-0000-0000-0000-000000000306",
            "spec": "cyber",
            "name": os.getenv("ADJUSTER_CYBER_NAME", "Farhan Cyber"),
            "email": validate_email(os.getenv("ADJUSTER_CYBER_EMAIL", "cyber.adjuster@insurance.com")),
            "phone": os.getenv("ADJUSTER_CYBER_PHONE", "9876530006"),
        },
    ]

    now_utc = datetime.now(timezone.utc)
    seeded_adjusters: List[Adjuster] = []

    for adef in adjuster_defs:
        user = db.query(User).filter(User.email == adef["email"]).first()
        if not user:
            user = db.query(User).filter(User.id == adef["id"]).first()

        if not user:
            user = User(
                id=adef["id"],
                tenant_id=tenant_id,
                full_name=adef["name"],
                email=adef["email"],
                phone=adef["phone"],
                password_hash=default_password_hash,
                role="ADJUSTER",
                status="active",
                email_verified_at=now_utc,
            )
            db.add(user)
            db.flush()
            logger.info("Created Adjuster User: '%s' <%s>", user.full_name, user.email)
        else:
            user.tenant_id = tenant_id
            user.role = "ADJUSTER"
            user.status = "active"
            if not user.email_verified_at:
                user.email_verified_at = now_utc
            logger.info("Adjuster User already exists: '%s' <%s>", user.full_name, user.email)

        # TenantMembership
        membership = db.query(TenantMembership).filter(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user.id,
        ).first()
        if not membership:
            db.add(TenantMembership(tenant_id=tenant_id, user_id=user.id, role="ADJUSTER", status="active"))

        # Adjuster table record
        adj_record = db.query(Adjuster).filter(
            (Adjuster.user_id == user.id) | (Adjuster.email == user.email)
        ).first()
        if not adj_record:
            adj_record = Adjuster(
                id=user.id,
                user_id=user.id,
                tenant_id=tenant_id,
                name=user.full_name,
                email=user.email,
                phone=user.phone,
                specialization=adef["spec"],
                claims_assigned=0,
                is_active=True,
            )
            db.add(adj_record)
            logger.info("  -> Registered Adjuster profile: spec='%s'", adef["spec"])
        else:
            adj_record.tenant_id = tenant_id
            adj_record.user_id = user.id
            adj_record.name = user.full_name
            adj_record.phone = user.phone
            adj_record.specialization = adef["spec"]
            adj_record.is_active = True
            logger.info("  -> Updated Adjuster profile: spec='%s'", adef["spec"])

        seeded_adjusters.append(adj_record)

    db.commit()
    return seeded_adjusters


def seed_master_policies_and_link(
    db: Any,
    tenant_id: str,
    claimants: List[User],
) -> List[Policy]:
    """
    Seeds 10 realistic insurance policies into the database master policy registry,
    then links policies to the claimant accounts.

    - Policies 1-4: Linked to Claimant 1 (Aarav Patel) across Motor, Health, Home, Travel.
    - Policies 5-8: Linked to Claimant 2 (Ananya Verma) across Senior Health, Health, Cyber, Motor.
    - Policies 9-10: Seeded as unlinked master policies with matching PII so that claimants can
      test/demonstrate the live policy linking flow via the API / UI.
    """
    if len(claimants) < 2:
        raise ValueError("At least 2 claimants are required to link policies.")

    claimant1 = claimants[0]
    claimant2 = claimants[1]
    now_utc = datetime.now(timezone.utc)

    # 10 Realistic Indian Insurance Policies
    policy_dataset = [
        # --- Policies for Claimant 1 (Aarav Patel) ---
        {
            "policy_number": "BAJAJ-MTR-2026-894102",
            "policy_type": "motor",
            "coverage_amount": 1500000.0,
            "deductible": 5000.0,
            "effective_date": date(2026, 1, 1),
            "expiry_date": date(2027, 1, 1),
            "policyholder_name": claimant1.full_name,
            "policyholder_dob": date(1990, 5, 15),
            "policyholder_phone": claimant1.phone,
            "policyholder_email": claimant1.email,
            "link_to_user": claimant1,  # Linked initially
        },
        {
            "policy_number": "HDFC-HLT-2026-302194",
            "policy_type": "health",
            "coverage_amount": 1000000.0,
            "deductible": 5000.0,
            "effective_date": date(2026, 1, 1),
            "expiry_date": date(2027, 1, 1),
            "policyholder_name": claimant1.full_name,
            "policyholder_dob": date(1990, 5, 15),
            "policyholder_phone": claimant1.phone,
            "policyholder_email": claimant1.email,
            "link_to_user": claimant1,  # Linked initially
        },
        {
            "policy_number": "ICICI-HOM-2026-771205",
            "policy_type": "home",
            "coverage_amount": 6000000.0,
            "deductible": 25000.0,
            "effective_date": date(2026, 1, 1),
            "expiry_date": date(2027, 1, 1),
            "policyholder_name": claimant1.full_name,
            "policyholder_dob": date(1990, 5, 15),
            "policyholder_phone": claimant1.phone,
            "policyholder_email": claimant1.email,
            "link_to_user": claimant1,  # Linked initially
        },
        {
            "policy_number": "TATA-TRV-2026-449102",
            "policy_type": "travel",
            "coverage_amount": 2500000.0,
            "deductible": 2500.0,
            "effective_date": date(2026, 1, 1),
            "expiry_date": date(2027, 1, 1),
            "policyholder_name": claimant1.full_name,
            "policyholder_dob": date(1990, 5, 15),
            "policyholder_phone": claimant1.phone,
            "policyholder_email": claimant1.email,
            "link_to_user": claimant1,  # Linked initially
        },

        # --- Policies for Claimant 2 (Ananya Verma) ---
        {
            "policy_number": "STAR-SRH-2026-118290",
            "policy_type": "senior_health",
            "coverage_amount": 750000.0,
            "deductible": 10000.0,
            "effective_date": date(2026, 1, 1),
            "expiry_date": date(2027, 1, 1),
            "policyholder_name": claimant2.full_name,
            "policyholder_dob": date(1962, 8, 20),
            "policyholder_phone": claimant2.phone,
            "policyholder_email": claimant2.email,
            "link_to_user": claimant2,  # Linked initially
        },
        {
            "policy_number": "CARE-HLT-2026-559103",
            "policy_type": "health",
            "coverage_amount": 800000.0,
            "deductible": 7500.0,
            "effective_date": date(2026, 1, 1),
            "expiry_date": date(2027, 1, 1),
            "policyholder_name": claimant2.full_name,
            "policyholder_dob": date(1962, 8, 20),
            "policyholder_phone": claimant2.phone,
            "policyholder_email": claimant2.email,
            "link_to_user": claimant2,  # Linked initially
        },
        {
            "policy_number": "SBI-CYB-2026-662810",
            "policy_type": "cyber",
            "coverage_amount": 1500000.0,
            "deductible": 5000.0,
            "effective_date": date(2026, 1, 1),
            "expiry_date": date(2027, 1, 1),
            "policyholder_name": claimant2.full_name,
            "policyholder_dob": date(1962, 8, 20),
            "policyholder_phone": claimant2.phone,
            "policyholder_email": claimant2.email,
            "link_to_user": claimant2,  # Linked initially
        },
        {
            "policy_number": "DIGIT-MTR-2026-901421",
            "policy_type": "motor",
            "coverage_amount": 900000.0,
            "deductible": 3000.0,
            "effective_date": date(2026, 1, 1),
            "expiry_date": date(2027, 1, 1),
            "policyholder_name": claimant2.full_name,
            "policyholder_dob": date(1962, 8, 20),
            "policyholder_phone": claimant2.phone,
            "policyholder_email": claimant2.email,
            "link_to_user": claimant2,  # Linked initially
        },

        # --- Master Unlinked Policies (Available for Link Policy Flow Verification) ---
        {
            "policy_number": "CHOLA-CYB-2026-880193",
            "policy_type": "cyber",
            "coverage_amount": 2000000.0,
            "deductible": 5000.0,
            "effective_date": date(2026, 1, 1),
            "expiry_date": date(2027, 1, 1),
            "policyholder_name": claimant1.full_name,
            "policyholder_dob": date(1990, 5, 15),
            "policyholder_phone": claimant1.phone,
            "policyholder_email": claimant1.email,
            "link_to_user": None,  # Unlinked master record
        },
        {
            "policy_number": "ROYAL-HOM-2026-991204",
            "policy_type": "home",
            "coverage_amount": 4500000.0,
            "deductible": 15000.0,
            "effective_date": date(2026, 1, 1),
            "expiry_date": date(2027, 1, 1),
            "policyholder_name": claimant2.full_name,
            "policyholder_dob": date(1962, 8, 20),
            "policyholder_phone": claimant2.phone,
            "policyholder_email": claimant2.email,
            "link_to_user": None,  # Unlinked master record
        },
    ]

    seeded_policies: List[Policy] = []
    logger.info("Seeding %d realistic master policies and linking to claimants...", len(policy_dataset))

    for pdata in policy_dataset:
        num = pdata["policy_number"]
        target_user = pdata["link_to_user"]
        phone_str = str(pdata["policyholder_phone"] or "")
        phone_last4 = phone_str[-4:] if len(phone_str) >= 4 else "0000"

        policy_row = db.query(Policy).filter(Policy.policy_number == num).first()
        if not policy_row:
            policy_row = Policy(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                policy_number=num,
                customer_id=target_user.id if target_user else None,
                policy_type=pdata["policy_type"],
                coverage_amount=pdata["coverage_amount"],
                deductible=pdata["deductible"],
                effective_date=pdata["effective_date"],
                expiry_date=pdata["expiry_date"],
                is_active=True,
                policyholder_name=pdata["policyholder_name"],
                policyholder_dob=pdata["policyholder_dob"],
                policyholder_phone=phone_str,
                policyholder_email=pdata["policyholder_email"],
                policyholder_phone_last4=phone_last4,
                linked_at=now_utc if target_user else None,
                link_attempts=0,
            )
            db.add(policy_row)
            if target_user:
                logger.info("  + Created & linked policy '%s' (%s) -> %s", num, pdata["policy_type"], target_user.full_name)
            else:
                logger.info("  + Created master unlinked policy '%s' (%s) -> PII matching %s (for Link Policy test)", num, pdata["policy_type"], pdata["policyholder_name"])
        else:
            # Policy already exists, update/preserve linkage
            policy_row.tenant_id = tenant_id
            policy_row.policy_type = pdata["policy_type"]
            policy_row.coverage_amount = pdata["coverage_amount"]
            policy_row.deductible = pdata["deductible"]
            policy_row.effective_date = pdata["effective_date"]
            policy_row.expiry_date = pdata["expiry_date"]
            policy_row.policyholder_name = pdata["policyholder_name"]
            policy_row.policyholder_dob = pdata["policyholder_dob"]
            policy_row.policyholder_phone = phone_str
            policy_row.policyholder_email = pdata["policyholder_email"]
            policy_row.policyholder_phone_last4 = phone_last4
            if target_user and not policy_row.customer_id:
                policy_row.customer_id = target_user.id
                policy_row.linked_at = now_utc
                logger.info("  * Linked existing policy '%s' -> %s", num, target_user.full_name)
            else:
                logger.info("  * Preserved existing policy '%s' (Customer ID: %s)", num, policy_row.customer_id or "Unlinked")

        seeded_policies.append(policy_row)

    db.commit()
    return seeded_policies


def find_docrag_directory() -> Optional[Path]:
    """Locate the authoritative docrag directory containing policy documents."""
    candidate_dirs = [
        Path(os.getenv("DOCRAG_DIR", "")),
        _repo_root / "docrag",
        Path(r"c:\Users\ragha\Desktop\insurance_claim_intake\docrag"),
        _repo_root / "database" / "docrag",
    ]
    for candidate in candidate_dirs:
        if candidate and candidate.exists() and any(candidate.glob("*.docx")):
            return candidate
    return None


def seed_rag_documents(
    db: Any,
    tenant_id: str,
    adjusters_by_spec: Dict[str, Adjuster],
    force: bool = False,
) -> Dict[str, Any]:
    """
    Ingest authoritative policy wording & regulatory documents from docrag/ into RAG store.
    
    Attributed directly to the specialist Adjuster for that domain line
    (knowledge management is strictly an adjuster capability in this system).
    """
    docrag_dir = find_docrag_directory()
    if not docrag_dir:
        logger.warning("No docrag directory found with .docx files. Checked repo root, DOCRAG_DIR, and database/docrag.")
        return {"total": 0, "ingested": 0, "skipped": 0, "failed": 0}

    logger.info("Found authoritative docrag directory: %s", docrag_dir)
    docx_files = sorted(list(docrag_dir.glob("*.docx")))
    total_files = len(docx_files)
    logger.info("Discovered %d documents to verify/ingest.", total_files)

    ingested = 0
    skipped = 0
    failed = 0

    for docx_path in docx_files:
        filename = docx_path.name
        doc_type, ins_type = DOCRAG_METADATA_MAP.get(filename, (None, None))

        # Select the specialist adjuster responsible for this line of business
        adjuster = adjusters_by_spec.get(ins_type or "") or list(adjusters_by_spec.values())[0]
        adjuster_user_id = str(adjuster.user_id or adjuster.id)

        existing_doc = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.source_name == filename,
            KnowledgeDocument.tenant_id == tenant_id,
        ).first()

        if existing_doc and not force:
            logger.info(
                "Document '%s' already indexed (ID: %s, Chunks: %d, Uploader: Adjuster %s). Skipping.",
                filename,
                existing_doc.id,
                len(existing_doc.chunks),
                adjuster.name,
            )
            skipped += 1
            continue

        try:
            content_bytes = docx_path.read_bytes()
            result = ingest_document(
                content=content_bytes,
                filename=filename,
                document_type=doc_type,
                insurance_type=ins_type,
                uploaded_by=adjuster_user_id,
                tenant_id=tenant_id,
                publication_status="published",
                jurisdiction="India",
            )
            ingested += 1
            logger.info(
                "Successfully ingested '%s': DocType='%s', Line='%s', Chunks=%s (Adjuster: %s <%s>)",
                filename,
                doc_type or "auto",
                ins_type or "auto",
                result.get("chunks", "N/A"),
                adjuster.name,
                adjuster.email,
            )
        except Exception as exc:
            failed += 1
            logger.error("Failed to ingest '%s': %s", filename, exc, exc_info=True)

    return {
        "total": total_files,
        "ingested": ingested,
        "skipped": skipped,
        "failed": failed,
    }


def seed_initialization(
    skip_rag: bool = False,
    force_rag: bool = False,
    custom_password: Optional[str] = None,
) -> None:
    """
    Main entry point for production DB seeding.
    """
    password_to_use = custom_password or DEFAULT_PASSWORD
    validate_password_strength(password_to_use)
    password_hash = get_password_hash(password_to_use)

    logger.info("=" * 70)
    logger.info("Starting IntelliClaim Production DB Initial Seeding")
    logger.info("=" * 70)

    db = SessionLocal()
    try:
        # 1. Tenant
        tenant = ensure_tenant(db)

        # 2. Seed 2 Claimants
        claimants = seed_claimants(db, tenant.id, password_hash)

        # 3. Seed 6 Adjusters (1 for each canonical specialization)
        adjusters = seed_adjusters(db, tenant.id, password_hash)
        adjusters_by_spec = {a.specialization: a for a in adjusters}

        # 4. Seed 10 Realistic Master Policies and link to claimants
        policies = seed_master_policies_and_link(db, tenant.id, claimants)

        # 5. Ingest RAG documents from docrag/ (attributed to specialist adjusters)
        rag_stats = {"total": 0, "ingested": 0, "skipped": 0, "failed": 0}
        if not skip_rag:
            rag_stats = seed_rag_documents(db, tenant.id, adjusters_by_spec=adjusters_by_spec, force=force_rag)
        else:
            logger.info("RAG document seeding skipped per flag.")

        logger.info("=" * 70)
        logger.info("Production DB Seeding Summary:")
        logger.info("  * Tenant: %s (%s)", tenant.name, tenant.id)
        logger.info("  * Admin: SKIPPED (Admin is managed independently via seed_admin.py)")
        logger.info("  * Claimants: %d created/verified", len(claimants))
        for c in claimants:
            logger.info("      - %s <%s>", c.full_name, c.email)
        logger.info("  * Adjusters: %d created/verified (6 specializations)", len(adjusters))
        for a in adjusters:
            logger.info("      - %s: %s <%s>", a.specialization, a.name, a.email)
        logger.info("  * Policies: %d realistic policies seeded/verified", len(policies))
        linked_count = sum(1 for p in policies if p.customer_id)
        unlinked_count = len(policies) - linked_count
        logger.info("      - %d linked to claimants, %d unlinked (ready for linking verification)", linked_count, unlinked_count)
        if not skip_rag:
            logger.info(
                "  * RAG Documents: %d total, %d ingested, %d skipped, %d failed (managed by Adjusters)",
                rag_stats["total"],
                rag_stats["ingested"],
                rag_stats["skipped"],
                rag_stats["failed"],
            )
        logger.info("=" * 70)
        logger.info("Seeding completed successfully!")

    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Production Database Initialization Seed Script")
    parser.add_argument("--skip-rag", action="store_true", help="Skip docrag document ingestion")
    parser.add_argument("--force-rag", action="store_true", help="Force re-ingestion of docrag documents")
    parser.add_argument("--password", type=str, default=None, help="Custom default password for seeded users")
    args = parser.parse_args()

    seed_initialization(
        skip_rag=args.skip_rag,
        force_rag=args.force_rag,
        custom_password=args.password,
    )


if __name__ == "__main__":
    main()
