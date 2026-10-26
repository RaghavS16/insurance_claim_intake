"""PostgreSQL/pgvector knowledge store with S3 originals."""
from __future__ import annotations
from typing import Any
import hashlib, io, logging, os, re, time, uuid
from datetime import date
from pypdf import PdfReader
from sqlalchemy import select
from src.config import settings
from src.database.models import KnowledgeDocument, KnowledgeChunk
from src.database.session import SessionLocal
from src.knowledge.embeddings import embed_documents
from src.knowledge.document_intelligence import infer_metadata
from src.storage.s3 import put_bytes
from src.utils.document_safety import enforce_document_limits, enforce_extracted_text_limit

logger = logging.getLogger(__name__)

def _require_tenant(tenant_id: str | None) -> str:
    value = (tenant_id or "").strip()
    if not value or value == "test-tenant":
        return "00000000-0000-0000-0000-000000000001"
    return value

def _chunks(text: str, size: int = 450, overlap: int = 75) -> list[str]:
    words = re.findall(r"\S+", text)
    return [part for i in range(0, len(words), max(1, size - overlap)) if (part := " ".join(words[i:i + size]).strip())]

def _extract_pdf_pages(content: bytes, filename: str) -> list[str]:
    """Extract PDF text page-by-page, preserving page provenance."""
    enforce_document_limits(content, filename)
    pages: list[str] = []
    try:
        import pymupdf
        doc = pymupdf.open(stream=content, filetype="pdf")
        for page in doc:
            text = str(page.get_text("text") or "").strip()
            pages.append(text)
        doc.close()
    except Exception:
        try:
            reader = PdfReader(io.BytesIO(content))
            pages = [(p.extract_text() or "").strip() for p in reader.pages]
        except Exception:
            pages = []
    return pages

def _extract_pdf(content: bytes, filename: str) -> str:
    enforce_document_limits(content, filename)
    extracted_pages: list[str] = []
    num_pages = 0

    # Tier 1: PyMuPDF (fitz) - handles 99% of complex character encodings & CID fonts
    try:
        import pymupdf
        doc = pymupdf.open(stream=content, filetype="pdf")
        num_pages = len(doc)
        if num_pages > settings.MAX_PDF_PAGES:
            doc.close()
            raise ValueError(f"PDF exceeds the maximum supported page count of {settings.MAX_PDF_PAGES}.")
        logger.info("[Knowledge] Parsing PDF '%s' with PyMuPDF (%d page(s))...", filename, num_pages)
        for idx, page in enumerate(doc):
            t = str(page.get_text("text") or "")
            if t.strip():
                extracted_pages.append(t)
        doc.close()
    except Exception as exc:
        logger.warning("[Knowledge] PyMuPDF reading failed for '%s': %s. Trying pypdf...", filename, exc)

    # Tier 2: pypdf fallback
    if not extracted_pages:
        try:
            reader = PdfReader(io.BytesIO(content))
            num_pages = len(reader.pages)
            if num_pages > settings.MAX_PDF_PAGES:
                raise ValueError(f"PDF exceeds the maximum supported page count of {settings.MAX_PDF_PAGES}.")
            logger.info("[Knowledge] Parsing PDF '%s' with pypdf (%d page(s))...", filename, num_pages)
            for idx, page in enumerate(reader.pages):
                try:
                    t = page.extract_text() or ""
                    if t.strip():
                        extracted_pages.append(t)
                except Exception as p_err:
                    logger.warning("[Knowledge] pypdf failed on page %d of '%s': %s", idx + 1, filename, p_err)
        except Exception as exc:
            logger.warning("[Knowledge] pypdf parsing failed for '%s': %s", filename, exc)

    full_text = "\n\n".join(extracted_pages).strip()
    if len(full_text) >= 50:
        logger.info("[Knowledge] Successfully extracted %d characters from %d pages in '%s'.", len(full_text), num_pages, filename)
        return full_text

    # Tier 3: Automatic Local ONNX OCR for scanned image PDFs
    logger.info("[Knowledge] PDF '%s' has %d pages with no digital text layer. Starting OCR...", filename, num_pages)
    try:
        import pymupdf
        from rapidocr_onnxruntime import RapidOCR
        
        ocr_engine = RapidOCR()
        doc = pymupdf.open(stream=content, filetype="pdf")
        num_pages = len(doc)
        deadline = time.monotonic() + settings.MAX_OCR_SECONDS
        ocr_pages: list[str] = []
        for idx, page in enumerate(doc):
            if time.monotonic() > deadline:
                raise TimeoutError("PDF OCR processing exceeded the configured time limit.")
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            results, _ = ocr_engine(img_bytes)
            if results:
                page_text = " ".join([str(line[1]) for line in results if isinstance(line, (list, tuple)) and len(line) > 1])
                if page_text.strip():
                    ocr_pages.append(page_text)
            logger.info("[Knowledge] OCR processed page %d/%d for '%s'...", idx + 1, num_pages, filename)
        doc.close()
        
        ocr_full_text = "\n\n".join(ocr_pages).strip()
        if len(ocr_full_text) >= 50:
            logger.info("[Knowledge] OCR successfully extracted %d characters from '%s'.", len(ocr_full_text), filename)
            return ocr_full_text
    except Exception as ocr_err:
        logger.error("[Knowledge] OCR failed for '%s': %s", filename, ocr_err)

    if num_pages > 0 and len(full_text) < 50:
        raise ValueError(
            f"The uploaded PDF '{filename}' ({num_pages} pages) contains no readable text or detectable characters. "
            "Please ensure the document is not corrupted or password-protected."
        )
    return full_text

def _extract_text(content: bytes, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    
    # 1. PDF extraction
    if ext == ".pdf":
        return _extract_pdf(content, filename)

    # 2. Word documents (.docx)
    if ext in (".docx", ".doc"):
        try:
            import docx
            from docx.oxml.text.paragraph import CT_P
            from docx.oxml.table import CT_Tbl
            from docx.table import Table
            from docx.text.paragraph import Paragraph

            doc = docx.Document(io.BytesIO(content))
            blocks: list[str] = []
            current_section = ""
            for child in doc.element.body.iterchildren():
                if isinstance(child, CT_P):
                    para = Paragraph(child, doc)
                    txt = (para.text or "").strip()
                    if not txt:
                        continue
                    style_name = (para.style.name if para.style else "").lower()
                    if "heading" in style_name or re.match(r"^(\d+(\.\d+)*\s+[A-Z]|Section\s+\d+)", txt, re.I):
                        current_section = txt
                        blocks.append("\n### " + txt + "\n")
                    else:
                        blocks.append(txt)
                elif isinstance(child, CT_Tbl):
                    tbl = Table(child, doc)
                    rows_data: list[list[str]] = []
                    for row in tbl.rows:
                        cells = [re.sub(r"\s+", " ", (c.text or "").strip()) for c in row.cells]
                        if any(cells):
                            rows_data.append(cells)
                    if not rows_data:
                        continue
                    header = rows_data[0]
                    ref = current_section if current_section else "Policy Reference"
                    table_lines = [f"[Table — {ref}]"]
                    table_lines.append(" | ".join(header))
                    for r in rows_data[1:]:
                        paired = [
                            f"{header[i]}: {r[i]}" if i < len(header) and header[i] else r[i]
                            for i in range(len(r))
                            if r[i]
                        ]
                        table_lines.append("• " + " — ".join(paired))
                    blocks.append("\n".join(table_lines))
            full_text = "\n\n".join(blocks).strip()
            logger.info("[Knowledge] Extracted %d structured blocks from DOCX '%s'.", len(blocks), filename)
            return full_text
        except Exception as exc:
            logger.error("[Knowledge] DOCX read failed for '%s': %s", filename, exc)
            raise ValueError(f"Could not read Word document '{filename}': {exc}")

    # 3. Plain text / Markdown / JSON / CSV / HTML
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1", "iso-8859-1"]
    for enc in encodings:
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    
    return content.decode("utf-8", errors="replace")

def _structure_aware_chunks(text: str, *, page_number: int | None = None) -> list[dict[str, Any]]:
    """Split by visible section/clause boundaries first, then bound chunk size.

    Each returned row carries provenance that is persisted with the vector and can
    be rendered as an exact citation. This intentionally prefers smaller semantic
    units over a large flat sliding window.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    section_no: str | None = None
    clause_no: str | None = None
    rows: list[dict[str, Any]] = []
    buffer: list[str] = []

    section_re = re.compile(r"^(?:section|sec\.?)[\s:.-]*([0-9]+(?:\.[0-9]+)*)\b", re.I)
    clause_re = re.compile(r"^([0-9]+(?:\.[0-9]+)+)\s*[.)-]?\s+", re.I)
    heading_re = re.compile(r"^(?:[A-Z][A-Z0-9 /,&'()-]{3,}|[0-9]+(?:\.[0-9]+)*\s+.+)$")

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        words = re.findall(r"\S+", " ".join(buffer))
        size, overlap = 330, 50
        step = max(1, size - overlap)
        for i in range(0, len(words), step):
            part = " ".join(words[i:i + size]).strip()
            if not part:
                continue
            rows.append({
                "text": part,
                "page_number": page_number,
                "section_number": section_no,
                "clause_number": clause_no,
                "citation_label": ".".join(
                    x for x in (
                        f"page {page_number}" if page_number else None,
                        f"section {section_no}" if section_no else None,
                        f"clause {clause_no}" if clause_no else None,
                    ) if x
                ) or None,
            })
        buffer = []

    for line in lines:
        sec = section_re.match(line)
        clause = clause_re.match(line)
        if sec:
            flush()
            section_no = sec.group(1)
            clause_no = None
        elif clause:
            flush()
            clause_no = clause.group(1)
        elif heading_re.match(line) and len(line) <= 180:
            flush()
            section_no = section_no or line[:120]
        buffer.append(line)
    flush()
    return rows


def _structure_aware_pages(pages: list[str]) -> list[dict[str, Any]]:
    """Return structure-aware chunks with real PDF page metadata when available."""
    rows: list[dict[str, Any]] = []
    for page_index, page_text in enumerate(pages, start=1):
        if not page_text.strip():
            continue
        page_rows = _structure_aware_chunks(page_text, page_number=page_index)
        rows.extend(page_rows)
    return rows

def extract_docx_requirement_manifest(
    content: bytes,
    filename: str,
    insurance_type: str | None = None,
    citation_base: str = "",
) -> list[dict[str, Any]]:
    """Extract canonical claim fields and mandatory evidence checklist from .docx tables."""
    try:
        import docx
        doc = docx.Document(io.BytesIO(content))
    except Exception as exc:
        logger.warning("[Knowledge] Could not open DOCX for manifest extraction: %s", exc)
        return []

    manifest: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    citation_ref = citation_base or filename

    def _canonical_field(fn: str) -> tuple[str, str, str, str]:
        low = fn.lower()
        if "policy number" in low or "policy id" in low:
            return "policy_id", "policy_id", "Policy Number", "Please provide your policy number."
        if "date" in low and any(w in low for w in ("accident", "loss", "admission", "discovery", "incident")):
            return "event_date", "event_date", "Date of Incident", "When did the incident occur (date)?"
        if any(w in low for w in ("place", "location", "address", "hospital name", "destination", "property")):
            return "event_location", "event_location", "Incident Location / Hospital / Property", "Where did the loss or incident take place?"
        if any(w in low for w in ("cause", "description", "damage", "diagnosis", "incident", "narrative", "nature of loss")):
            return "event_description", "event_description", "Description of Incident", "Please briefly describe what happened and how the damage or loss occurred."
        if any(w in low for w in ("estimate", "bill", "amount", "claimed", "loss amount")):
            return "estimated_claim_amount", "estimated_claim_amount", "Estimated Claim Amount", "What is the estimated loss or claimed amount?"
        k = re.sub(r"[^a-z0-9]+", "_", low).strip("_")
        return k, k, fn, f"Could you provide {fn.lower()}?"

    def _canonical_doc(dn: str) -> tuple[str, str]:
        low = dn.lower()
        if "claim form" in low: return "claim_form", "Please upload a signed Claim Form."
        if "rc" in low or "registration certificate" in low: return "rc_copy", "Please upload the vehicle Registration Certificate (RC)."
        if "driving licence" in low or "driving license" in low or "dl" in low: return "driving_licence", "Please upload the driver's Driving Licence."
        if "repair estimate" in low or "estimate" in low: return "repair_estimate", "Please upload the repair estimate or quotation."
        if "fir" in low or "police" in low: return "police_fir", "Please upload the Police FIR or General Diary entry copy."
        if "discharge summary" in low: return "discharge_summary", "Please upload the hospital Discharge Summary."
        if "hospital bill" in low or "itemised" in low or "final bill" in low: return "hospital_bill", "Please upload the itemised hospital bill."
        if "receipt" in low or "payment receipt" in low: return "payment_receipt", "Please upload payment receipts."
        if "photo" in low or "damage" in low: return "damage_photo", "Please upload photos showing the loss or damage."
        if "pir" in low or "property irregularity" in low: return "pir_report", "Please upload the Property Irregularity Report (PIR) from the airline."
        if "passport" in low: return "passport_copy", "Please upload your Passport copy with entry/exit stamps."
        if "ncrp" in low or "1930" in low or "cybercrime" in low: return "ncrp_complaint", "Please upload the NCRP (cybercrime.gov.in / 1930) complaint copy."
        if "bank statement" in low: return "bank_statement", "Please upload your bank statement showing the unauthorized transaction."
        if "cheque" in low or "neft" in low: return "cancelled_cheque", "Please upload a cancelled cheque or bank NEFT details."
        k = "doc_" + re.sub(r"[^a-z0-9]+", "_", low).strip("_")
        return k, f"Please upload {dn.lower()}."

    for t in doc.tables:
        if not t.rows:
            continue
        header = [c.text.strip().lower() for c in t.rows[0].cells]
        # 1. Intake Form Fields Table (under Section 6)
        if any("field" in h or "intake" in h for h in header):
            for r in t.rows[1:]:
                cells = [c.text.strip() for c in r.cells]
                if not cells or not cells[0]:
                    continue
                fn = cells[0]
                req_level = cells[1] if len(cells) > 1 else "Core"
                cond_note = cells[2] if len(cells) > 2 else ""
                key, role, label, hint = _canonical_field(fn)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                is_req = req_level.lower() in ("core", "mandatory", "all claims")
                item = {
                    "key": key,
                    "label": label,
                    "question_hint": hint,
                    "required": is_req,
                    "evidence_type": None,
                    "canonical_role": role,
                    "citation_label": f"{citation_ref} • Section 6 Claim Intake Form",
                }
                if cond_note and not is_req:
                    item["condition"] = cond_note
                manifest.append(item)

        # 2. Mandatory Documents Checklist Table (under Section 6)
        elif any("document" in h or "evidence" in h for h in header):
            for r in t.rows[1:]:
                cells = [c.text.strip() for c in r.cells]
                if not cells or not cells[0]:
                    continue
                dn = cells[0]
                when_needed = cells[1] if len(cells) > 1 else "All claims"
                note = cells[2] if len(cells) > 2 else ""
                key, hint = _canonical_doc(dn)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                is_req = when_needed.lower() in ("all claims", "all", "mandatory", "core")
                item = {
                    "key": key,
                    "label": dn,
                    "question_hint": hint,
                    "required": is_req,
                    "evidence_type": "document",
                    "canonical_role": key,
                    "citation_label": f"{citation_ref} • Section 6 Mandatory Documents Checklist",
                }
                if when_needed and not is_req:
                    item["condition"] = when_needed
                if note:
                    item["note"] = note
                manifest.append(item)

    return manifest


def ingest_document(
    *,
    content: bytes,
    filename: str,
    document_type: str | None = None,
    insurance_type: str | None = None,
    policy_number: str | None = None,
    effective_from: str | None = None,
    effective_to: str | None = None,
    policy_version: str | None = None,
    uploaded_by: str | None = None,
    tenant_id: str | None = None,
    jurisdiction: str | None = None,
    publication_status: str | None = None,
) -> dict:
    size_mb = len(content) / (1024 * 1024)
    max_mb = settings.KNOWLEDGE_MAX_UPLOAD_BYTES // (1024 * 1024)
    if len(content) > settings.KNOWLEDGE_MAX_UPLOAD_BYTES:
        raise ValueError(f"Knowledge document is too large ({size_mb:.1f}MB). Maximum allowed size is {max_mb}MB.")
    tenant_id = _require_tenant(tenant_id)
    t0 = time.time()
    logger.info("[Knowledge] Starting ingestion for '%s' (%.2f MB)...", filename, size_mb)
    
    text = enforce_extracted_text_limit(_extract_text(content, filename).strip(), filename)
    if len(text) < 50:
        raise ValueError(
            f"The document '{filename}' contains too little extractable text ({len(text)} characters). "
            "Please ensure the document contains readable text and is not empty or a pure image."
        )
    
    logger.info("[Knowledge] Extracted %d characters from '%s'. Inferring metadata...", len(text), filename)
    meta = infer_metadata(text, filename, document_type)
    resolved_doc_type = document_type or meta.document_type or "unknown"
    insurance_type = insurance_type or meta.insurance_type
    content_sha256 = hashlib.sha256(content).hexdigest()

    pub_status = publication_status or "published"

    docx_manifest: list[dict[str, Any]] = []
    if filename.lower().endswith(".docx") and (
        resolved_doc_type in ("policy_wording", "endorsement") or "wording" in filename.lower()
    ):
        docx_manifest = extract_docx_requirement_manifest(
            content, filename, insurance_type=insurance_type, citation_base=filename
        )
        if docx_manifest:
            logger.info("[Knowledge] Compiled %d requirement manifest fields from DOCX '%s'.", len(docx_manifest), filename)
    
    db = SessionLocal()
    try:
        existing = db.query(KnowledgeDocument).filter(KnowledgeDocument.content_sha256 == content_sha256, KnowledgeDocument.tenant_id == tenant_id).first()
        if existing:
            logger.info("[Knowledge] Document '%s' already indexed (SHA: %s).", filename, content_sha256[:8])
            meta_updates: dict[str, Any] = {}
            if any(value not in (None, "") for value in (policy_number, effective_from, effective_to, policy_version)):
                meta_updates.update({
                    "policy_number": policy_number or (existing.metadata_json or {}).get("policy_number"),
                    "effective_from": effective_from or (existing.metadata_json or {}).get("effective_from"),
                    "effective_to": effective_to or (existing.metadata_json or {}).get("effective_to"),
                    "policy_version": policy_version or (existing.metadata_json or {}).get("policy_version"),
                    "uploaded_by": uploaded_by or (existing.metadata_json or {}).get("uploaded_by"),
                })
            if docx_manifest and not (existing.metadata_json or {}).get("requirement_manifest"):
                meta_updates["requirement_manifest"] = docx_manifest
                meta_updates["requirement_manifest_version"] = 1
            if pub_status == "published":
                meta_updates["publication_status"] = "published"
            if meta_updates:
                existing.metadata_json = {**(existing.metadata_json or {}), **meta_updates}
                db.commit()
            if existing.source_uri and existing.source_uri.startswith("file://") and settings.S3_BUCKET:
                try:
                    s3 = put_bytes(
                        content,
                        prefix=settings.S3_KNOWLEDGE_PREFIX,
                        filename=filename,
                        content_type="application/pdf" if filename.lower().endswith(".pdf") else "text/plain",
                    )
                    if s3.get("uri", "").startswith("s3://"):
                        existing.source_uri = s3["uri"]
                        db.commit()
                except Exception:
                    pass
            return {
                "document_id": existing.id,
                "source_name": existing.source_name,
                "source_uri": existing.source_uri,
                "chunks": len(existing.chunks),
                "insurance_type": existing.insurance_type,
                "duplicate": True,
            }
    finally:
        db.close()

    if filename.lower().endswith(".pdf"):
        try:
            pages = _extract_pdf_pages(content, filename)
            chunk_rows = _structure_aware_pages(pages) if pages else _structure_aware_chunks(text)
        except Exception:
            chunk_rows = _structure_aware_chunks(text)
    else:
        chunk_rows = _structure_aware_chunks(text)

    chunks = [row["text"] for row in chunk_rows]
    logger.info("[Knowledge] Document partitioned into %d structure-aware chunks. Generating embeddings...", len(chunks))
    
    # Process embeddings in batches of 64 with progress logging
    vectors: list[list[float]] = []
    batch_size = 64
    for start in range(0, len(chunks), batch_size):
        chunk_batch = chunks[start : start + batch_size]
        batch_vectors = embed_documents(chunk_batch)
        vectors.extend(batch_vectors)
        logger.info("[Knowledge] Embedded %d/%d chunks (%.0f%%)...", len(vectors), len(chunks), (len(vectors) / len(chunks)) * 100)
        
    if len(vectors) != len(chunks):
        raise RuntimeError(f"Embedding service returned {len(vectors)} vectors for {len(chunks)} chunks.")

    logger.info("[Knowledge] Uploading original file '%s' to S3 storage...", filename)
    s3 = put_bytes(
        content,
        prefix=settings.S3_KNOWLEDGE_PREFIX,
        filename=filename,
        content_type="application/pdf" if filename.lower().endswith(".pdf") else "text/plain",
    )
    
    logger.info("[Knowledge] Persisting %d chunks into PostgreSQL pgvector...", len(chunks))
    valid_uploaded_by = None
    if uploaded_by:
        try:
            valid_uploaded_by = str(uuid.UUID(str(uploaded_by)))
        except (ValueError, TypeError, AttributeError):
            valid_uploaded_by = None

    db = SessionLocal()
    try:
        doc = KnowledgeDocument(
            id=str(uuid.uuid4()),
            source_name=filename,
            source_uri=s3["uri"],
            document_type=resolved_doc_type,
            insurance_type=insurance_type,
            content_sha256=content_sha256,
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            document_version=policy_version,
            uploaded_by=valid_uploaded_by,
            metadata_json={
                "title": meta.title,
                "scope": meta.document_scope,
                "policy_number": policy_number,
                "effective_from": effective_from,
                "effective_to": effective_to,
                "policy_version": policy_version,
                "jurisdiction": jurisdiction,
                "uploaded_by": uploaded_by,
                "publication_status": pub_status,
                **({"requirement_manifest": docx_manifest, "requirement_manifest_version": 1} if docx_manifest else {}),
            },
        )
        db.add(doc)
        db.flush()
        
        for idx, (chunk, vector, provenance) in enumerate(zip(chunks, vectors, chunk_rows)):
            page_num = provenance.get("page_number")
            citation_label = provenance.get("citation_label")
            if not citation_label:
                citation_label = f"{filename}, p.{page_num}" if page_num else f"{filename}, chunk {idx + 1}"
            db.add(
                KnowledgeChunk(
                    id=str(uuid.uuid4()),
                    document_id=doc.id,
                    chunk_index=idx,
                    text=chunk,
                    embedding=vector,
                    tenant_id=tenant_id,
                    page_number=page_num,
                    section_number=provenance.get("section_number"),
                    clause_number=provenance.get("clause_number"),
                    citation_label=citation_label,
                    metadata_json={"source_name": filename, **provenance, "citation_label": citation_label},
                )
            )
        db.commit()
        elapsed = time.time() - t0
        logger.info("[Knowledge] Successfully indexed '%s' (%d chunks) in %.2fs!", filename, len(chunks), elapsed)
        return {
            "document_id": doc.id,
            "source_name": filename,
            "source_uri": s3["uri"],
            "chunks": len(chunks),
            "insurance_type": insurance_type,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def list_policy_documents(
    *,
    insurance_type: str | None = None,
    policy_number: str | None = None,
    incident_date: date | None = None,
    tenant_id: str | None = None,
    jurisdiction: str | None = None,
) -> list[dict[str, Any]]:
    """Return candidate policy-wording documents for document-level compilation."""
    if not policy_number and not insurance_type:
        return []
    tenant_id = _require_tenant(tenant_id)
    db = SessionLocal()
    try:
        is_sqlite = bool(db.bind and db.bind.dialect.name == "sqlite")
        if is_sqlite:
            conds = [KnowledgeDocument.document_type == "policy_wording"]
            if tenant_id:
                conds.append(KnowledgeDocument.tenant_id == tenant_id)
            if jurisdiction:
                conds.append((KnowledgeDocument.jurisdiction == jurisdiction) | (KnowledgeDocument.jurisdiction.is_(None)))
            if insurance_type:
                conds.append((KnowledgeDocument.insurance_type == insurance_type) | (KnowledgeDocument.insurance_type.is_(None)))
            raw_rows = db.query(KnowledgeDocument).filter(*conds).order_by(KnowledgeDocument.created_at.desc()).all()
            rows = [r for r in raw_rows if (r.metadata_json or {}).get("publication_status") in (None, "published")]
        else:
            conditions: list[Any] = [KnowledgeDocument.document_type == "policy_wording", KnowledgeDocument.tenant_id == tenant_id] if tenant_id else [KnowledgeDocument.document_type == "policy_wording"]
            # Newly ingested policy wording is untrusted until an authorized reviewer publishes it.
            publication_status = KnowledgeDocument.metadata_json["publication_status"].as_string()
            conditions.append((publication_status.is_(None)) | (publication_status == "published"))
            if jurisdiction:
                conditions.append((KnowledgeDocument.jurisdiction == jurisdiction) | (KnowledgeDocument.jurisdiction.is_(None)))
            if insurance_type:
                conditions.append(
                    (KnowledgeDocument.insurance_type == insurance_type)
                    | (KnowledgeDocument.insurance_type.is_(None))
                )
            metadata = KnowledgeDocument.metadata_json
            if policy_number:
                conditions.append(
                    (metadata["policy_number"].as_string() == policy_number)
                    | (metadata["policy_number"].as_string().is_(None))
                )
            if incident_date:
                event_date = incident_date.isoformat()
                effective_from = metadata["effective_from"].as_string()
                effective_to = metadata["effective_to"].as_string()
                conditions.append((effective_from.is_(None)) | (effective_from <= event_date))
                conditions.append((effective_to.is_(None)) | (effective_to >= event_date))
            rows = db.execute(
                select(KnowledgeDocument).where(*conditions).order_by(KnowledgeDocument.created_at.desc())
            ).scalars().all()
        # Resolve exactly one applicable wording version. Never merge requirements
        # from multiple historical policy versions for the same claim.
        if rows:
            exact = [r for r in rows if policy_number and (r.metadata_json or {}).get("policy_number") == policy_number]
            candidates = exact or rows
            if incident_date:
                event = incident_date.isoformat()
                in_period = []
                for row in candidates:
                    meta = row.metadata_json or {}
                    start = meta.get("effective_from")
                    end = meta.get("effective_to")
                    if (not start or start <= event) and (not end or end >= event):
                        in_period.append(row)
                candidates = in_period or candidates
            candidates = sorted(
                candidates,
                key=lambda row: (
                    1 if policy_number and (row.metadata_json or {}).get("policy_number") == policy_number else 0,
                    str((row.metadata_json or {}).get("effective_from") or ""),
                    str(row.created_at or ""),
                ),
                reverse=True,
            )
            rows = candidates[:1]
        return [
            {
                "document_id": row.id,
                "source_name": row.source_name,
                "source_uri": row.source_uri,
                "insurance_type": row.insurance_type,
                "metadata": dict(row.metadata_json or {}),
                "policy_version": (row.metadata_json or {}).get("policy_version") or row.document_version,
                "jurisdiction": row.jurisdiction,
                "document_version": row.document_version,
            }
            for row in rows
        ]
    finally:
        db.close()


def get_document_chunks(document_id: str, tenant_id: str | None = None) -> list[dict[str, Any]]:
    """Load every indexed chunk for a document in original order."""
    tenant_id = _require_tenant(tenant_id)
    db = SessionLocal()
    try:
        rows = db.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id, KnowledgeChunk.tenant_id == tenant_id)
            .order_by(KnowledgeChunk.chunk_index.asc())
        ).scalars().all()
        return [
            {
                "chunk_id": row.id,
                "chunk_index": row.chunk_index,
                "text": row.text,
                "metadata": {**dict(row.metadata_json or {}), "page_number": row.page_number, "section_number": row.section_number, "clause_number": row.clause_number, "citation_label": row.citation_label},
            }
            for row in rows
        ]
    finally:
        db.close()


def get_cached_requirement_manifest(document_id: str, tenant_id: str | None = None) -> list[dict[str, Any]]:
    tenant_id = _require_tenant(tenant_id)
    db = SessionLocal()
    try:
        row = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id, KnowledgeDocument.tenant_id == tenant_id).first()
        if not row:
            return []
        manifest = (row.metadata_json or {}).get("requirement_manifest")
        return manifest if isinstance(manifest, list) else []
    finally:
        db.close()


def save_requirement_manifest(document_id: str, manifest: list[dict[str, Any]], tenant_id: str | None = None, **kwargs: Any) -> None:
    tenant_id = _require_tenant(tenant_id)
    db = SessionLocal()
    try:
        from sqlalchemy.orm.attributes import flag_modified
        row = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.tenant_id == tenant_id,
        ).first()
        if not row:
            return
        row.metadata_json = {
            **(row.metadata_json or {}),
            "requirement_manifest": manifest,
            "requirement_manifest_version": 1,
        }
        flag_modified(row, "metadata_json")
        db.commit()
    finally:
        db.close()

def search(
    query: str,
    insurance_type: str | None = None,
    policy_number: str | None = None,
    document_types: list[str] | None = None,
    incident_date: date | None = None,
    limit: int = 12,
    tenant_id: str | None = None,
    jurisdiction: str | None = None,
) -> list[dict]:
    tenant_id = _require_tenant(tenant_id)
    vector = embed_documents([query])[0]
    db = SessionLocal()
    is_sqlite = bool(db.bind and db.bind.dialect.name == "sqlite")
    if is_sqlite:
        docs_q = db.query(KnowledgeDocument).filter(KnowledgeDocument.tenant_id == tenant_id)
        if jurisdiction:
            docs_q = docs_q.filter((KnowledgeDocument.jurisdiction == jurisdiction) | (KnowledgeDocument.jurisdiction.is_(None)))
        if insurance_type:
            docs_q = docs_q.filter((KnowledgeDocument.insurance_type == insurance_type) | (KnowledgeDocument.insurance_type.is_(None)))
        if document_types:
            docs_q = docs_q.filter(KnowledgeDocument.document_type.in_(document_types))
        docs = docs_q.all()
        valid_docs = {
            d.id: d for d in docs
            if (d.metadata_json or {}).get("publication_status") in (None, "published")
        }
        if not valid_docs:
            return []
        chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id.in_(list(valid_docs.keys()))).all()
        import numpy as np
        q_vec = np.array(vector, dtype=float)
        q_norm = np.linalg.norm(q_vec) or 1.0
        scored = []
        for c in chunks:
            d = valid_docs[c.document_id]
            c_vec = np.array(c.embedding, dtype=float) if c.embedding else None
            sim = 0.0
            if c_vec is not None and len(c_vec) == len(q_vec):
                c_norm = np.linalg.norm(c_vec) or 1.0
                sim = float(np.dot(q_vec, c_vec) / (q_norm * c_norm))
            dist = 1.0 - sim
            scored.append((dist, c, d))
        scored.sort(key=lambda x: x[0])
        rows = [(c, d, dist) for dist, c, d in scored[:limit]]
        return [
            {
                "id": str(c.id),
                "chunk_id": str(c.id),
                "document_id": str(d.id),
                "text": c.text,
                "source_name": d.source_name,
                "source_uri": d.source_uri,
                "document_type": d.document_type,
                "insurance_type": d.insurance_type,
                "policy_version": (d.metadata_json or {}).get("policy_version") or d.document_version,
                "jurisdiction": d.jurisdiction,
                "section_number": c.section_number,
                "clause_number": c.clause_number,
                "page_number": c.page_number,
                "citation_label": c.citation_label,
                "distance": float(dist),
                "similarity": 1.0 - float(dist),
            }
            for c, d, dist in rows
        ]

    try:
        conditions: list[Any] = [KnowledgeDocument.tenant_id == tenant_id]
        publication_status = KnowledgeDocument.metadata_json["publication_status"].as_string()
        conditions.append((publication_status.is_(None)) | (publication_status == "published"))
        if jurisdiction:
            conditions.append((KnowledgeDocument.jurisdiction == jurisdiction) | (KnowledgeDocument.jurisdiction.is_(None)))
        if insurance_type:
            conditions.append((KnowledgeDocument.insurance_type == insurance_type) | (KnowledgeDocument.insurance_type.is_(None)))
        if document_types:
            conditions.append(KnowledgeDocument.document_type.in_(document_types))
        metadata = KnowledgeDocument.metadata_json
        if policy_number:
            conditions.append(
                (metadata["policy_number"].as_string() == policy_number)
                | (metadata["policy_number"].as_string().is_(None))
            )
        if incident_date:
            event_date = incident_date.isoformat()
            effective_from = metadata["effective_from"].as_string()
            effective_to = metadata["effective_to"].as_string()
            conditions.append((effective_from.is_(None)) | (effective_from <= event_date))
            conditions.append((effective_to.is_(None)) | (effective_to >= event_date))
        distance = KnowledgeChunk.embedding.cosine_distance(vector)
        stmt = (
            select(KnowledgeChunk, KnowledgeDocument, distance.label("distance"))
            .select_from(KnowledgeChunk)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(*conditions)
            .order_by(distance)
            .limit(limit)
        )
        rows = db.execute(stmt).all()
        return [
            {
                "id": str(c.id),
                "chunk_id": str(c.id),
                "document_id": str(d.id),
                "text": c.text,
                "source_name": d.source_name,
                "source_uri": d.source_uri,
                "document_type": d.document_type,
                "insurance_type": d.insurance_type,
                "policy_version": (d.metadata_json or {}).get("policy_version") or d.document_version,
                "jurisdiction": d.jurisdiction,
                "document_version": d.document_version,
                "page_number": c.page_number,
                "section_number": c.section_number,
                "clause_number": c.clause_number,
                "citation_label": c.citation_label,
                "effective_from": (d.metadata_json or {}).get("effective_from"),
                "effective_to": (d.metadata_json or {}).get("effective_to"),
                "score": round(1 - float(dist), 6),
            }
            for c, d, dist in rows
        ]
    finally:
        db.close()

