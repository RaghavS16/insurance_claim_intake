"""Tests for claimant chat history, multiple claim sessions, draft deletion, and transcript export."""
import pytest
from fastapi.testclient import TestClient


def test_claimant_chat_history_and_sessions(client: TestClient):
    headers = {"X-User-ID": "TEST-CLAIMANT-1"}

    # 1. Create a new claim session
    res = client.post("/api/v1/claims/new-session", headers=headers)
    assert res.status_code == 200
    data = res.json()
    ticket_id_1 = data["ticket_id"]
    assert ticket_id_1.startswith("CLAIM-")

    # 2. Add some chat turns
    turn1 = client.post(
        f"/api/v1/claims/{ticket_id_1}/text-turn",
        json={"text": "I had a car accident yesterday in Chennai and damage is around 15000."},
        headers=headers,
    )
    assert turn1.status_code == 200

    # 3. Create a second claim session
    res2 = client.post("/api/v1/claims/new-session", headers=headers)
    assert res2.status_code == 200
    ticket_id_2 = res2.json()["ticket_id"]
    assert ticket_id_2 != ticket_id_1

    # 4. List claims and verify both sessions exist in history
    list_res = client.get("/api/v1/claims", headers=headers)
    assert list_res.status_code == 200
    claims = list_res.json()["items"]
    assert len(claims) >= 2
    tickets = [c["ticket_id"] for c in claims]
    assert ticket_id_1 in tickets
    assert ticket_id_2 in tickets

    # 5. Verify conversation turns are returned with claim details
    detail_res = client.get(f"/api/v1/claims/{ticket_id_1}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert "conversation" in detail
    assert len(detail["conversation"]) >= 2
    assert detail["conversation"][0]["speaker"] == "user"
    assert "Chennai" in detail["conversation"][0]["text"]

    # 6. Export transcript dossier
    export_res = client.get(f"/api/v1/claims/{ticket_id_1}/export", headers=headers)
    assert export_res.status_code == 200
    export_data = export_res.json()
    assert "formatted_text" in export_data
    assert "INSURANCE CLAIM INTAKE DOSSIER" in export_data["formatted_text"]
    assert ticket_id_1 in export_data["formatted_text"]
    assert "Chennai" in export_data["formatted_text"]

    # 7. Delete draft session 2
    del_res = client.delete(f"/api/v1/claims/{ticket_id_2}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # 8. Verify session 2 is gone
    get_del = client.get(f"/api/v1/claims/{ticket_id_2}", headers=headers)
    assert get_del.status_code == 404
