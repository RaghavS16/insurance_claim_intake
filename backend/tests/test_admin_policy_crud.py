

def test_link_policy_with_policyholder_name(claimant_token, db_session):
    client = TestClient(app); token, claimant_id = claimant_token; headers = {"Authorization": f"Bearer {token}"}; unique_pol = f"POL-{uuid.uuid4().hex[:6].upper()}"
    policy = Policy(id=str(uuid.uuid4()), policy_number=unique_pol, policy_type="health", coverage_amount=500000, deductible=2000, effective_date=date(2024, 1, 1), expiry_date=date(2027, 12, 31), is_active=True, policyholder_name="David Attenborough", policyholder_dob=date(1980, 5, 20), policyholder_phone_last4="9876", link_attempts=0)
    db_session.add(policy); db_session.commit()
    res = client.post("/api/v1/policies/link", json={"policy_number": unique_pol, "policyholder_name": "David Attenborough", "date_of_birth": "1980-05-20", "phone_last4": "9876"}, headers=headers)
    assert res.status_code == 200, res.text; assert res.json()["linked"] is True


def test_claim_patch_details(claimant_token):
    client = TestClient(app); token, claimant_id = claimant_token; headers = {"Authorization": f"Bearer {token}"}
    res = client.post("/api/v1/claims/voice-session", headers=headers); assert res.status_code == 200; ticket_id = res.json()["ticket_id"]
    res_patch = client.patch(f"/api/v1/claims/{ticket_id}", json={"policy_id": "MOT-5521", "insurance_type": "motor", "event_date": "2024-05-10", "estimated_claim_amount": 45000, "event_description": "Rear-end collision on highway"}, headers=headers)
    assert res_patch.status_code == 200, res_patch.text
    patched = res_patch.json(); assert patched["extracted_data"]["policy_id"] == "MOT-5521"; assert patched["insurance_type"] == "motor"; assert patched["event_date"] == "2024-05-10"; assert patched["estimated_claim_amount"] == 45000


def test_reject_invalid_claim_confirmation(claimant_token):
    client = TestClient(app); token, claimant_id = claimant_token; headers = {"Authorization": f"Bearer {token}"}
    res = client.post("/api/v1/claims/voice-session", headers=headers); assert res.status_code == 200; ticket_id = res.json()["ticket_id"]
    res_intake = client.post("/api/v1/claims/intake", json={"ticket_id": ticket_id, "claim_text": "I had a bike accident yesterday in Bengaluru. Policy FAKE-POLICY-9999. Repair cost is ₹10,000.", "input_mode": "text"}, headers=headers)
    assert res_intake.status_code == 200, res_intake.text
    state = res_intake.json(); assert state["awaiting_confirmation"] is True
    res_turn = client.post(f"/api/v1/claims/{ticket_id}/text-turn", json={"text": "Yes, everything looks correct."}, headers=headers)
    assert res_turn.status_code == 200, res_turn.text; assert res_turn.json()["confirmed"] is True
    res_conf_invalid = client.post(f"/api/v1/claims/{ticket_id}/confirm", headers=headers)
    assert res_conf_invalid.status_code == 400
    assert "Claim verification failed" in res_conf_invalid.json()["detail"]
