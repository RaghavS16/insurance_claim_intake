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


def test_admin_adjuster_crud_lifecycle(client, db):
    # 1. Create Adjuster
    create_res = client.post("/api/v1/admin/adjusters", json={
        "name": "Alex Murphy",
        "email": "alex.murphy@insure.co",
        "specialization": "cyber",
    }, headers={"X-User-ID": "TEST_ADMIN_ID"})
    assert create_res.status_code == 200
    adj_id = create_res.json()["id"]

    # 2. Get Single Adjuster
    get_res = client.get(f"/api/v1/admin/adjusters/{adj_id}", headers={"X-User-ID": "TEST_ADMIN_ID"})
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Alex Murphy"
    assert get_res.json()["specialization"] == "cyber"
    assert get_res.json()["is_active"] is True

    # 3. Update Adjuster (Change specialization and active status)
    update_res = client.put(f"/api/v1/admin/adjusters/{adj_id}", json={
        "name": "Alex J. Murphy",
        "specialization": "home",
        "is_active": False,
    }, headers={"X-User-ID": "TEST_ADMIN_ID"})
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Alex J. Murphy"
    assert update_res.json()["specialization"] == "home"
    assert update_res.json()["is_active"] is False

    # Check user model sync
    user = db.query(User).filter(User.id == adj_id).first()
    assert user is not None
    assert user.full_name == "Alex J. Murphy"
    assert user.status == "inactive"

    # 4. Reset Password
    reset_res = client.post(f"/api/v1/admin/adjusters/{adj_id}/reset-password", headers={"X-User-ID": "TEST_ADMIN_ID"})
    assert reset_res.status_code == 200
    assert "temporary_password" in reset_res.json()
    assert len(reset_res.json()["temporary_password"]) > 6

    # 5. Delete Adjuster (claims_assigned = 0)
    del_res = client.delete(f"/api/v1/admin/adjusters/{adj_id}", headers={"X-User-ID": "TEST_ADMIN_ID"})
    assert del_res.status_code == 200

    # Ensure deleted from DB
    assert db.query(Adjuster).filter(Adjuster.id == adj_id).first() is None
    assert db.query(User).filter(User.id == adj_id).first() is None


def test_admin_delete_adjuster_blocked_if_claims_assigned(client, db):
    # Create an adjuster and manually assign claims_assigned = 3
    create_res = client.post("/api/v1/admin/adjusters", json={
        "name": "Busy Adjuster",
        "email": "busy.adj@insure.co",
        "specialization": "motor",
    }, headers={"X-User-ID": "TEST_ADMIN_ID"})
    assert create_res.status_code == 200
    adj_id = create_res.json()["id"]

    adj = db.query(Adjuster).filter(Adjuster.id == adj_id).first()
    adj.claims_assigned = 3
    db.commit()

    # Attempt deletion -> should fail with 400
    del_res = client.delete(f"/api/v1/admin/adjusters/{adj_id}", headers={"X-User-ID": "TEST_ADMIN_ID"})
    assert del_res.status_code == 400
    assert "active assigned claims" in del_res.json()["detail"]

    # Cleanup
    adj.claims_assigned = 0
    db.commit()
    client.delete(f"/api/v1/admin/adjusters/{adj_id}", headers={"X-User-ID": "TEST_ADMIN_ID"})
