import os
from database._db_helpers import SessionLocal  # bootstraps sys.path automatically
from src.database.models import User
from src.utils.auth import get_password_hash


def seed_admin():
    db = SessionLocal()
    try:
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@insurance.com")
        admin_password = os.environ.get("ADMIN_PASSWORD", "InsuranceAdmin@0101")

        if not db.query(User).filter(User.email == admin_email).first():
            db.add(User(
                full_name="Ops Admin",
                email=admin_email,
                password_hash=get_password_hash(admin_password),
                role="ADMIN",
                status="active",
            ))
            db.commit()
            print("Admin created — change password immediately via a real reset flow.")
        else:
            print("Admin user already exists.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_admin()
