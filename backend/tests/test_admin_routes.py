import io
from datetime import date
import pytest
from src.database.models import Adjuster, Policy, User


def test_admin_endpoints_forbidden_for_claimant(client):
    # Default TEST_USER_ID is a CLAIMANT
    response = client.get("/api/v1/admin/adjusters")
    assert response.status_code == 403

    response = client.post("/api/v1/admin/adjusters", json={
        "name": "Test Adjuster",
        "email": "test.adj@insure.co",
        "specialization": "motor",
    })
    assert response.status_code == 403


def test_admin_create_adjuster(client, db):
    email = "sarah.connor@insure.co"
    # Ensure clean state
    db.query(Adjuster).filter(Adjuster.email == email).delete()
    db.query(User).filter(User.email == email).delete()
    db.commit()

    response = client.post("/api/v1/admin/adjusters", json={
        "name": "Sarah Connor",
        "email": email,
        "specialization": "motor",
    }, headers={"X-User-ID": "TEST_ADMIN_ID"})

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Sarah Connor"
    assert data["email"] == email
    assert data["specialization"] == "motor"
    assert "temporary_password" in data
    assert len(data["temporary_password"]) > 6

    # Verify User and Adjuster in database
    user = db.query(User).filter(User.email == email).first()
    assert user is not None
    assert user.role == "ADJUSTER"

    adjuster = db.query(Adjuster).filter(Adjuster.email == email).first()
    assert adjuster is not None
    assert adjuster.specialization == "motor"


def test_admin_list_adjusters(client):
    response = client.get("/api/v1/admin/adjusters", headers={"X-User-ID": "TEST_ADMIN_ID"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    emails = [a["email"] for a in data]
    assert len(emails) >= 1


def test_admin_import_policies_csv(client, db):
    # Prepare CSV data:
    # 1. Update existing policy XYZ123 (which is linked to TEST_USER_ID)
    # 2. Insert new policy CSV-NEW-001
    csv_data = (
        "policy_number,policy_type,coverage_amount,deductible,effective_date,expiry_date,policyholder_name,policyholder_dob,policyholder_phone_last4,is_active\n"
        "XYZ123,motor,999999,5000,2024-01-01,2030-12-31,John Doe,1990-05-15,1234,true\n"
        "CSV-NEW-001,health,450000,1500,2025-01-01,2027-12-31,New Customer,1985-06-20,9999,true\n"
    )

    file_bytes = io.BytesIO(csv_data.encode("utf-8"))
    files = {"file": ("policies.csv", file_bytes, "text/csv")}

    response = client.post(
        "/api/v1/admin/policies/import",
        files=files,
        headers={"X-User-ID": "TEST_ADMIN_ID"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["imported"] >= 1
    assert data["updated"] >= 1

    # Verify XYZ123 was updated but customer_id was NOT overwritten
    pol_xyz = db.query(Policy).filter(Policy.policy_number == "XYZ123").first()
    assert pol_xyz is not None
    assert float(pol_xyz.coverage_amount) == 999999.0
    assert pol_xyz.customer_id == "TEST_USER_ID"  # Preserved!

    # Verify new policy was created with customer_id=None
    pol_new = db.query(Policy).filter(Policy.policy_number == "CSV-NEW-001").first()
    assert pol_new is not None
    assert pol_new.customer_id is None
    assert float(pol_new.coverage_amount) == 450000.0


def test_admin_list_all_policies(client):
    response = client.get("/api/v1/admin/policies", headers={"X-User-ID": "TEST_ADMIN_ID"})
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 2
