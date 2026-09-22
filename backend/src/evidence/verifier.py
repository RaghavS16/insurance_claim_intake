"""Claim evidence verification pipeline.

Uploaded evidence is never considered satisfying a requirement merely because a file
exists. The pipeline extracts readable content, classifies the document, compares it
to the requested evidence, and returns VERIFIED, REJECTED, REVIEW_REQUIRED, or
UNREADABLE without inventing facts.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
from typing import Any

from pydantic import BaseModel, Field

from src.agents.llm_factory import get_configured_llm
from src.knowledge.store import _extract_text

logger = logging.getLogger(__name__)


class EvidenceAnalysis(BaseModel):
    detected_document_type: str = Field(description="The actual document type visible in the uploaded evidence.")
    verification_status: str = Field(description="One of VERIFIED, REJECTED, REVIEW_REQUIRED, UNREADABLE.")
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=2000)
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    claim_consistency: str = Field(description="One of CONSISTENT, INCONSISTENT, UNKNOWN.")
    consistency_notes: list[str] = Field(default_factory=list)


def _extract_image_text(content: bytes, filename: str) -> str:
    """OCR raster evidence using the same local OCR stack used by knowledge ingestion."""
    try:
        from PIL import Image
        from rapidocr_onnxruntime import RapidOCR
        image = Image.open(io.BytesIO(content)).convert("RGB")
        # RapidOCR accepts an ndarray/PIL-compatible image in supported versions.
        import numpy as np
        result, _ = RapidOCR()(np.asarray(image))
        if not result:
            return ""
        return " ".join(str(row[1]) for row in result if isinstance(row, (list, tuple)) and len(row) > 1).strip()
    except Exception as exc:
        logger.warning("Evidence OCR failed for %s: %s", filename, exc)
        return ""


def validate_evidence_file(content: bytes, filename: str) -> tuple[bool, str]:
    """Validate payload signatures; never trust browser MIME or filename alone."""
    if not content:
        return False, "The uploaded file is empty."
    ext = os.path.splitext(filename or "")[1].lower()
    signatures = {
        ".pdf": content.startswith(b"%PDF-"),
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"),
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
    }
    if ext in signatures and not signatures[ext]:
        return False, "The file contents do not match the selected file type."
    if ext == ".docx" and not content.startswith(b"PK\x03\x04"):
        return False, "The Word document appears corrupted or is not a valid DOCX payload."
    return True, ""


def extract_evidence_text(content: bytes, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp"}:
        return _extract_image_text(content, filename)
    try:
        return (_extract_text(content, filename) or "").strip()
    except Exception as exc:
        logger.warning("Evidence text extraction failed for %s: %s", filename, exc)
        return ""


def verify_evidence(
    *,
    content: bytes,
    filename: str,
    requested_evidence: dict[str, Any],
    claim_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze one upload against one dynamic claim requirement.

    A verifier failure is deliberately REVIEW_REQUIRED rather than VERIFIED. This
    prevents an unavailable/uncertain model from satisfying a required document.
    """
    sha256 = hashlib.sha256(content).hexdigest()
    valid_file, file_reason = validate_evidence_file(content, filename)
    if not valid_file:
        return {
            "verification_status": "REJECTED",
            "detected_document_type": "invalid_file",
            "confidence": 1.0,
            "reason": file_reason,
            "extracted_fields": {},
            "claim_consistency": "UNKNOWN",
            "consistency_notes": [],
            "sha256": sha256,
            "extracted_text_length": 0,
        }
    text = extract_evidence_text(content, filename)
    if len(text.strip()) < 20:
        ext = os.path.splitext(filename)[1].lower()
        if ext in {".jpg", ".jpeg", ".png", ".webp"}:
            return {
                "verification_status": "REVIEW_REQUIRED",
                "detected_document_type": "photograph",
                "confidence": 0.0,
                "reason": "This image does not contain readable text and has been queued for manual review.",
                "extracted_fields": {},
                "claim_consistency": "UNKNOWN",
                "consistency_notes": ["No text detected; manual review required."],
                "sha256": sha256,
                "extracted_text_length": len(text),
            }
        else:
            return {
                "verification_status": "UNREADABLE",
                "detected_document_type": "unknown",
                "confidence": 0.0,
                "reason": "The uploaded evidence could not be read reliably. Please upload a clearer document or image.",
                "extracted_fields": {},
                "claim_consistency": "UNKNOWN",
                "consistency_notes": [],
                "sha256": sha256,
                "extracted_text_length": len(text),
            }

    prompt = f"""You are an insurance evidence verification service.
Determine what document the claimant actually uploaded and whether it satisfies the requested evidence requirement.
Do not trust the filename. Use the document content.

REQUESTED EVIDENCE REQUIREMENT:
{requested_evidence}

CLAIM CONTEXT (use only to assess relevance; do not invent missing facts):
{claim_context or {}}

UPLOADED DOCUMENT FILENAME (metadata only): {filename}
UPLOADED DOCUMENT CONTENT:
{text[:24000]}

Rules:
1. VERIFIED only when the content clearly represents the requested evidence and is relevant to the claim context.
1a. Do not use the filename, extension, MIME type, or requested label as evidence of document type.
1b. A renamed or mislabeled document must be classified by its actual contents.
1c. If the requested item is a bill/invoice/receipt, verify that the document itself contains bill-like evidence (issuer/provider, transaction/invoice information, line items or amount, and document identity where present); a ticket, itinerary, discharge summary, prescription, or unrelated form is not a bill.
2. REJECTED when the document is clearly a different evidence type.
3. REVIEW_REQUIRED when the type is plausible but ambiguous, conflicting, or insufficiently readable/complete.
4. UNREADABLE only when content cannot be reliably interpreted.
5. Never infer a field that is not present in the document.
6. Return the actual detected document type, not the requested type when they differ.
"""
    data: dict[str, Any] = {}
    try:
        result = get_configured_llm().with_structured_output(EvidenceAnalysis).invoke(prompt)
        if isinstance(result, EvidenceAnalysis):
            data = result.model_dump()
        elif isinstance(result, BaseModel) or hasattr(result, "model_dump"):
            data = EvidenceAnalysis.model_validate(result.model_dump()).model_dump()
        elif isinstance(result, dict):
            data = EvidenceAnalysis.model_validate(result).model_dump()
        else:
            if hasattr(result, "content") and result.content:
                import json
                try:
                    msg_content = str(result.content)
                    start = msg_content.find('{')
                    end = msg_content.rfind('}')
                    if start != -1 and end != -1:
                        data = EvidenceAnalysis.model_validate_json(msg_content[start:end+1]).model_dump()
                    else:
                        raise ValueError("No JSON found in response")
                except Exception:
                    raise ValueError("Evidence model returned an unsupported response type")
            else:
                raise ValueError("Evidence model returned an unsupported response type")
    except Exception as exc:
        logger.exception("Evidence verification failed for %s", filename)
        data = {
            "verification_status": "REVIEW_REQUIRED",
            "detected_document_type": "unknown",
            "confidence": 0.0,
            "reason": "Automatic evidence verification is temporarily unavailable; adjuster review is required.",
            "extracted_fields": {},
            "claim_consistency": "UNKNOWN",
            "consistency_notes": [type(exc).__name__],
        }
    status = str(data.get("verification_status", "REVIEW_REQUIRED")).upper()
    c = data.get("confidence")
    confidence = float(c) if c is not None else 0.0
    if status == "VERIFIED" and (confidence < 0.85 or str(data.get("claim_consistency", "UNKNOWN")).upper() == "INCONSISTENT"):
        status = "REVIEW_REQUIRED"
        data["reason"] = data.get("reason") or "Automatic verification confidence is not high enough for acceptance."
    if status not in {"VERIFIED", "REJECTED", "REVIEW_REQUIRED", "UNREADABLE"}:
        status = "REVIEW_REQUIRED"
    data["verification_status"] = status
    data["sha256"] = sha256
    data["extracted_text_length"] = len(text)
    data["requested_evidence_type"] = requested_evidence.get("evidence_type")
    data["requested_requirement_key"] = requested_evidence.get("key") or requested_evidence.get("requirement_key")
    return data
