from unittest.mock import Mock

from src.evidence.verifier import validate_evidence_file, verify_evidence


def test_validate_evidence_rejects_empty_payload():
    ok, reason = validate_evidence_file(b"", "hospital_bill.pdf")
    assert not ok
    assert reason


def test_validate_evidence_rejects_mismatched_pdf_signature():
    ok, reason = validate_evidence_file(b"not a pdf", "hospital_bill.pdf")
    assert not ok
    assert "file type" in reason.lower()


def test_verify_evidence_never_accepts_low_confidence(monkeypatch):
    class FakeResult:
        def model_dump(self):
            return {
                "detected_document_type": "hospital_bill",
                "verification_status": "VERIFIED",
                "confidence": 0.72,
                "reason": "Looks like a hospital bill.",
                "extracted_fields": {},
                "claim_consistency": "CONSISTENT",
                "consistency_notes": [],
            }

    fake_llm = Mock()
    fake_llm.with_structured_output.return_value.invoke.return_value = FakeResult()
    monkeypatch.setattr("src.evidence.verifier.get_configured_llm", lambda: fake_llm)
    monkeypatch.setattr("src.evidence.verifier.extract_evidence_text", lambda *_: "Hospital Invoice\nInvoice No 123\nTotal 12000")

    result = verify_evidence(
        content=b"%PDF-1.7 fake but sufficient for mocked extraction",
        filename="renamed.pdf",
        requested_evidence={"key": "hospital_bill", "label": "Hospital bill", "evidence_type": "document"},
        claim_context={"insurance_type": "health"},
    )
    assert result["verification_status"] == "REVIEW_REQUIRED"


def test_verify_evidence_accepts_clear_high_confidence_match(monkeypatch):
    class FakeResult:
        def model_dump(self):
            return {
                "detected_document_type": "hospital_bill",
                "verification_status": "VERIFIED",
                "confidence": 0.96,
                "reason": "The document clearly contains hospital billing information.",
                "extracted_fields": {"invoice_number": "123", "total": 12000},
                "claim_consistency": "CONSISTENT",
                "consistency_notes": [],
            }

    fake_llm = Mock()
    fake_llm.with_structured_output.return_value.invoke.return_value = FakeResult()
    monkeypatch.setattr("src.evidence.verifier.get_configured_llm", lambda: fake_llm)
    monkeypatch.setattr("src.evidence.verifier.extract_evidence_text", lambda *_: "Hospital Invoice\nInvoice No 123\nTotal 12000")

    result = verify_evidence(
        content=b"%PDF-1.7 fake but sufficient for mocked extraction",
        filename="anything.pdf",
        requested_evidence={"key": "hospital_bill", "label": "Hospital bill", "evidence_type": "document"},
        claim_context={"insurance_type": "health"},
    )
    assert result["verification_status"] == "VERIFIED"
    assert result["detected_document_type"] == "hospital_bill"
