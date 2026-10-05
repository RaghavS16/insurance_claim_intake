import sys
import os
sys.path.insert(0, "/app")

from src.database.session import SessionLocal
from src.database.models import User
from src.database.hardening_models import Tenant, TenantMembership
from src.utils.auth import get_password_hash

db = SessionLocal()

# Check if admin exists
admin_email = "viratkohli.admin@insureclaim.com"
admin = db.query(User).filter(User.email == admin_email).first()

if not admin:
    tenant = Tenant(name="Admin Workspace", status="active")
    db.add(tenant)
    db.flush()
    
    admin = User(
        full_name="Virat Kohli",
        email="viratkohli.admin@insureclaim.com",
        phone="7584961838",
        password_hash=get_password_hash("AdminPassword123!"),
        role="ADMIN",
        status="active",
        tenant_id=tenant.id,
    )
    db.add(admin)
    db.flush()
    db.add(TenantMembership(tenant_id=tenant.id, user_id=admin.id, role="ADMIN", status="active"))
    db.commit()
    print("Admin user created successfully.")
    print("Email: viratkohli.admin@insureclaim.com")
    print("Password: [PASSWORD]")
else:
    print("Admin user already exists.")
    print("Email: viratkohli.admin@insureclaim.com")
    print("Password: (previously set)")

db.close()
