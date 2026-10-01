from types import SimpleNamespace

from src.domain.readiness import calculate_readiness


def test_readiness_blocks_open_required_requirement():
    result = calculate_readiness(
        requirements=[
            SimpleNamespace(
                id="r1",
                requirement_key="police_report",
                label="Police report",
                status="open",
                required=True,
                evidence_type="police_report",
            )
        ],
        policy_verification={"valid": True, "identity_verified": True},
        evidence_rows=[],
        exceptions=[],
    )

    assert result.ready is False
    assert result.blocking_requirements[0]["key"] == "police_report"


def test_readiness_passes_when_requirements_and_policy_are_verified():
    result = calculate_readiness(
        requirements=[
            SimpleNamespace(
                id="r1",
                requirement_key="police_report",
                label="Police report",
                status="verified",
                required=True,
                evidence_type="police_report",
            )
        ],
        policy_verification={"valid": True, "identity_verified": True},
        evidence_rows=[
            SimpleNamespace(status="uploaded", verification_status="VERIFIED")
        ],
        exceptions=[],
    )

    assert result.ready is True
    assert result.blocking_requirements == []


def test_readiness_blocks_non_authoritative_requirement_plan():
    result = calculate_readiness(
        requirements=[
            SimpleNamespace(
                id="r2",
                requirement_key="provisional_item",
                label="Provisional item",
                status="satisfied",
                required=True,
                evidence_type=None,
                provenance_json={"authoritative": False},
            )
        ],
        policy_verification={"valid": True, "identity_verified": True},
        evidence_rows=[],
        exceptions=[],
    )

    assert result.ready is False
    assert result.blocking_requirements[0]["type"] == "KNOWLEDGE"


def test_readiness_blocks_open_exception():
    result = calculate_readiness(
        requirements=[],
        policy_verification={"valid": True, "identity_verified": True},
        evidence_rows=[],
        exceptions=[
            SimpleNamespace(
                id="ex1",
                event_type="document_conflict",
                reason="Conflicting evidence",
                blocking=True,
            )
        ],
    )

    assert result.ready is False
    assert result.exceptions[0]["type"] == "document_conflict"


def test_evidence_file_validation_rejects_mismatched_pdf():
    from src.evidence.verifier import validate_evidence_file
    ok, reason = validate_evidence_file(b"not-a-pdf", "invoice.pdf")
    assert ok is False
    assert "contents do not match" in reason


def test_evidence_file_validation_accepts_pdf_signature():
    from src.evidence.verifier import validate_evidence_file
    ok, reason = validate_evidence_file(b"%PDF-1.7\n", "invoice.pdf")
    assert ok is True
    assert reason == ""


def test_evidence_file_validation_rejects_empty_payload():
    from src.evidence.verifier import validate_evidence_file
    ok, reason = validate_evidence_file(b"", "invoice.pdf")
    assert ok is False
    assert "empty" in reason.lower()
