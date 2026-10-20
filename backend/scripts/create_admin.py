import os
import sys
import getpass
from datetime import datetime, timezone
from pathlib import Path

# Add backend directory to sys.path so it works locally and inside container
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if "/app" not in sys.path:
    sys.path.insert(0, "/app")

from src.database.session import SessionLocal
from src.database.models import User
from src.database.hardening_models import Tenant, TenantMembership
from src.utils.auth import get_password_hash
from src.utils.validators import validate_password_strength, validate_email, validate_full_name, validate_phone


def create_admin() -> None:
    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_name = os.environ.get("ADMIN_FULL_NAME")
    admin_phone = os.environ.get("ADMIN_PHONE")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if not admin_email:
        raise ValueError("ADMIN_EMAIL environment variable is required.")
    if not admin_name:
        raise ValueError("ADMIN_FULL_NAME environment variable is required.")
    if not admin_phone:
        raise ValueError("ADMIN_PHONE environment variable is required.")
    if not admin_password:
        if sys.stdin.isatty():
            admin_password = getpass.getpass("Enter admin password: ")
        else:
            raise ValueError("ADMIN_PASSWORD environment variable is required in non-interactive environments.")

    clean_email = validate_email(admin_email)
    clean_name = validate_full_name(admin_name)
    clean_phone = validate_phone(admin_phone)
    validate_password_strength(admin_password)

    default_tenant_id = "00000000-0000-0000-0000-000000000001"

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.id == default_tenant_id).first()
        if not tenant:
            tenant = Tenant(
                id=default_tenant_id,
                name="Default Workspace",
                status="active",
            )
            db.add(tenant)
            db.flush()

        admin = db.query(User).filter(User.email == clean_email).first()
        if not admin:
            admin = User(
                full_name=clean_name,
                email=clean_email,
                phone=clean_phone,
                password_hash=get_password_hash(admin_password),
                role="ADMIN",
                status="active",
                tenant_id=tenant.id,
                email_verified_at=datetime.now(timezone.utc),
            )
            db.add(admin)
            db.flush()
            db.add(TenantMembership(tenant_id=tenant.id, user_id=admin.id, role="ADMIN", status="active"))
            db.commit()
            print(f"Admin user '{clean_email}' created successfully.")
        else:
            admin.full_name = clean_name
            admin.phone = clean_phone
            admin.role = "ADMIN"
            admin.status = "active"
            admin.tenant_id = tenant.id
            admin.password_hash = get_password_hash(admin_password)
            admin.email_verified_at = datetime.now(timezone.utc)
            membership = db.query(TenantMembership).filter(
                TenantMembership.tenant_id == tenant.id,
                TenantMembership.user_id == admin.id,
            ).first()
            if not membership:
                db.add(TenantMembership(tenant_id=tenant.id, user_id=admin.id, role="ADMIN", status="active"))
            else:
                membership.role = "ADMIN"
                membership.status = "active"
            db.commit()
            print(f"Admin user '{clean_email}' already exists and was updated successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    create_admin()
