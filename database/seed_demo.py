"""Idempotent demo seed for one tenant, three operational roles, and sample policies."""
import os
import secrets
import uuid
from datetime import date, timedelta

from database._db_helpers import SessionLocal
from src.database.models import User, Policy, Adjuster
from src.database.hardening_models import Tenant, TenantMembership
from src.utils.auth import get_password_hash

TENANT_ID = "00000000-0000-0000-0000-000000000001"
USERS = [
    ("00000000-0000-0000-0000-000000000101", "Ops Admin", "admin@insurance.com", "ADMIN", "9876500001"),
    ("00000000-0000-0000-0000-000000000102", "Asha Adjuster", "asha.adjuster@insurance.com", "ADJUSTER", "9876500002"),
    ("00000000-0000-0000-0000-000000000103", "Vikram Adjuster", "vikram.adjuster@insurance.com", "ADJUSTER", "9876500003"),
    ("00000000-0000-0000-0000-000000000104", "Riya Claimant", "riya.claimant@insurance.com", "CLAIMANT", "9876500004"),
]

def seed_demo():
    db=SessionLocal()
    try:
        tenant=db.query(Tenant).filter(Tenant.id==TENANT_ID).first()
        if not tenant:
            tenant=Tenant(id=TENANT_ID,name="InsureClaim Demo Tenant",status="active")
            db.add(tenant)
            db.flush()

        demo_password=os.getenv("DEMO_PASSWORD") or secrets.token_urlsafe(18)
        users={}
        for uid,name,email,role,phone in USERS:
            user=db.query(User).filter(User.id==uid).first()
            if not user:
                user=User(id=uid,tenant_id=TENANT_ID,full_name=name,email=email,phone=phone,password_hash=get_password_hash(demo_password),role=role,status="active")
                db.add(user)
                db.flush()
            else:
                user.tenant_id=TENANT_ID; user.role=role; user.status="active"
            users[role,email]=user
            if not db.query(TenantMembership).filter(TenantMembership.tenant_id==TENANT_ID,TenantMembership.user_id==uid).first():
                db.add(TenantMembership(tenant_id=TENANT_ID,user_id=uid,role=role,status="active"))

        adjusters=[
            ("00000000-0000-0000-0000-000000000102","Asha Adjuster","asha.adjuster@insurance.com","9876500002","motor"),
            ("00000000-0000-0000-0000-000000000103","Vikram Adjuster","vikram.adjuster@insurance.com","9876500003","health"),
        ]
        for uid,name,email,phone,spec in adjusters:
            row=db.query(Adjuster).filter(Adjuster.id==uid).first()
            if not row:
                db.add(Adjuster(id=uid,user_id=uid,tenant_id=TENANT_ID,name=name,email=email,phone=phone,specialization=spec,claims_assigned=0,is_active=True))

        claimant=users[("CLAIMANT","riya.claimant@insurance.com")]
        policies=[
            ("POL-DEMO-MOTOR-001","motor",1500000,10000,date(2026,1,1),date(2027,1,1),"Riya Claimant",date(1994,6,15),"9876500004","riya.claimant@insurance.com"),
            ("POL-DEMO-HEALTH-001","health",800000,5000,date(2026,1,1),date(2027,1,1),"Riya Claimant",date(1994,6,15),"9876500004","riya.claimant@insurance.com"),
        ]
        for number,ptype,coverage,deductible,eff,exp,name,dob,phone,email in policies:
            row=db.query(Policy).filter(Policy.policy_number==number).first()
            if not row:
                row=Policy(id=str(uuid.uuid4()),tenant_id=TENANT_ID,policy_number=number,customer_id=None,policy_type=ptype,coverage_amount=coverage,deductible=deductible,effective_date=eff,expiry_date=exp,is_active=True,policyholder_name=name,policyholder_dob=dob,policyholder_phone=phone,policyholder_email=email,policyholder_phone_last4=phone[-4:],linked_at=None,link_attempts=0)
                db.add(row)
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
