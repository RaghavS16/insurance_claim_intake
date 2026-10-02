"""PostgreSQL/pgvector knowledge store with S3 originals."""
from __future__ import annotations
from typing import Any
import hashlib, io, logging, os, re, time, uuid
from datetime import date
from dataclasses import dataclass
from pypdf import PdfReader
from sqlalchemy import select
from src.config import settings
from src.database.models import KnowledgeDocument, KnowledgeChunk
from src.database.session import SessionLocal
from src.knowledge.embeddings import embed_documents
from src.knowledge.document_intelligence import infer_metadata
from src.storage.s3 import put_bytes

logger = logging.getLogger(__name__)

def _extract_pdf(content: bytes, filename: str) -> str:
    extracted_pages: list[str] = []
    num_pages = 0

    # Tier 1: PyMuPDF (fitz) - handles 99% of complex character encodings & CID fonts
    try:
        import pymupdf
        doc = pymupdf.open(stream=content, filetype="pdf")
        num_pages = len(doc)
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
        ocr_pages: list[str] = []
        for idx, page in enumerate(doc):
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
            doc = docx.Document(io.BytesIO(content))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_text:
                        paragraphs.append(row_text)
            full_text = "\n\n".join(paragraphs).strip()
            logger.info("[Knowledge] Extracted %d paragraphs from DOCX '%s'.", len(paragraphs), filename)
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

def _chunks(text: str, size: int = 450, overlap: int = 75) -> list[str]:
    words = re.findall(r"\S+", text)
    return [part for i in range(0, len(words), max(1, size - overlap)) if (part := " ".join(words[i : i + size]).strip())]


def _structure_aware_chunks(units: list[dict[str, Any]], size: int = 450, overlap: int = 75) -> list[dict[str, Any]]:
    """Chunk document units while preserving page/section/clause provenance."""
    heading_re = re.compile(
        r"^\s*(?:(?:section|sec\.?)\s+([A-Za-z0-9.()\-]+)\s*[:\-.]?\s*(.*)|"
        r"(?:clause)\s+([A-Za-z0-9.()\-]+)\s*[:\-.]?\s*(.*))$",
        re.IGNORECASE,
    )
    number_heading_re = re.compile(r"^\s*(\d+(?:\.\d+){0,4})\s+(.{2,140})$")
    chunks: list[dict[str, Any]] = []
    buffer: list[str] = []
    state = {"section_number": None, "section_title": None, "clause_number": None,
             "page_start": None, "page_end": None}

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        words = buffer[:]
        step = max(1, size - overlap)
        for offset in range(0, len(words), step):
            part = " ".join(words[offset:offset + size]).strip()
            if not part:
                continue
            chunks.append({
                "text": part,
                "page_number": state["page_start"] if state["page_start"] == state["page_end"] else None,
                "page_start": state["page_start"],
                "page_end": state["page_end"],
                "section_number": state["section_number"],
                "section_title": state["section_title"],
                "clause_number": state["clause_number"],
            })
            if offset + size >= len(words):
                break
        buffer = []

    for unit in units:
        page = unit.get("page_number")
        text = str(unit.get("text") or "").strip()
        if not text:
            continue
        if state["page_start"] is None:
            state["page_start"] = page
        state["page_end"] = page
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            heading = heading_re.match(line)
            numbered = number_heading_re.match(line)
            if heading:
                flush()
                if heading.group(1):
                    state["section_number"] = heading.group(1)
                    state["section_title"] = (heading.group(2) or "").strip() or None
                    state["clause_number"] = None
                else:
                    state["clause_number"] = heading.group(3)
                continue
            if numbered and len(line) <= 180 and not line.endswith("."):
                flush()
                state["section_number"] = numbered.group(1)
                state["section_title"] = numbered.group(2).strip()
                state["clause_number"] = None
                continue
            buffer.extend(re.findall(r"\S+", line))
            if len(buffer) >= size:
                flush()
                state["page_start"] = page
                state["page_end"] = page
    flush()
    return chunks

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
    jurisdiction: str | None = None,
    uploaded_by: str | None = None,
    tenant_id: str | None = None,
) -> dict:
    t0 = time.time()
    size_mb = len(content) / (1024 * 1024)
    max_mb = settings.KNOWLEDGE_MAX_UPLOAD_BYTES // (1024 * 1024)
    logger.info("[Knowledge] Starting ingestion for '%s' (%.2f MB)...", filename, size_mb)
    
    if len(content) > settings.KNOWLEDGE_MAX_UPLOAD_BYTES:
        raise ValueError(f"Knowledge document is too large ({size_mb:.1f}MB). Maximum allowed size is {max_mb}MB.")
    
    text = _extract_text(content, filename).strip()
    if len(text) < 50:
        raise ValueError(
            f"The document '{filename}' contains too little extractable text ({len(text)} characters). "
            "Please ensure the document contains readable text and is not empty or a pure image."
        )
    
    logger.info("[Knowledge] Extracted %d characters from '%s'. Inferring metadata...", len(text), filename)
    meta = infer_metadata(text, filename, document_type)
    insurance_type = insurance_type or meta.insurance_type
    content_sha256 = hashlib.sha256(content).hexdigest()
    
    db = SessionLocal()
    try:
        existing = db.query(KnowledgeDocument).filter(KnowledgeDocument.content_sha256 == content_sha256, *([KnowledgeDocument.tenant_id == tenant_id] if tenant_id else [])).first()
        if existing:
            logger.info("[Knowledge] Document '%s' already indexed (SHA: %s).", filename, content_sha256[:8])
            if any(value not in (None, "") for value in (policy_number, effective_from, effective_to, policy_version)):
                existing.metadata_json = {
                    **(existing.metadata_json or {}),
                    "policy_number": policy_number or (existing.metadata_json or {}).get("policy_number"),
                    "effective_from": effective_from or (existing.metadata_json or {}).get("effective_from"),
                    "effective_to": effective_to or (existing.metadata_json or {}).get("effective_to"),
                    "policy_version": policy_version or (existing.metadata_json or {}).get("policy_version"),
                    "uploaded_by": uploaded_by or (existing.metadata_json or {}).get("uploaded_by"),
                }
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
                "document_id": str(existing.id),
                "source_name": existing.source_name,
                "source_uri": existing.source_uri,
                "chunks": len(existing.chunks),
                "insurance_type": existing.insurance_type,
                "duplicate": True,
            }
    finally:
        db.close()

    if filename.lower().endswith(".pdf"):
        page_units = []
        try:
            import pymupdf
            pdf = pymupdf.open(stream=content, filetype="pdf")
            for idx, page in enumerate(pdf):
                page_units.append({"page_number": idx + 1, "text": page.get_text("text") or ""})
            pdf.close()
        except Exception:
            page_units = []
        if not page_units:
            page_units = [{"page_number": None, "text": text}]
    else:
        page_units = [{"page_number": None, "text": text}]
    chunk_rows = _structure_aware_chunks(page_units)
    if not chunk_rows:
        chunk_rows = [{"text": chunk, "page_number": None, "page_start": None, "page_end": None,
                       "section_number": None, "section_title": None, "clause_number": None}
                      for chunk in _chunks(text)]
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
    db = SessionLocal()
    try:
        doc = KnowledgeDocument(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            source_name=filename,
            source_uri=s3["uri"],
            document_type=document_type or meta.document_type or "unknown",
            insurance_type=insurance_type,
            content_sha256=content_sha256,
            uploaded_by=uploaded_by,
            metadata_json={
                "title": meta.title,
                "scope": meta.document_scope,
                "policy_number": policy_number,
                "effective_from": effective_from,
                "effective_to": effective_to,
                "policy_version": policy_version,
                "uploaded_by": uploaded_by,
                "publication_status": "pending_review",
                "jurisdiction": jurisdiction,
            },
        )
        db.add(doc)
        db.flush()
        
        for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
            row_meta = chunk_rows[idx]
            db.add(
                KnowledgeChunk(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    document_id=doc.id,
                    chunk_index=idx,
                    text=chunk,
                    embedding=vector,
                    metadata_json={**row_meta, "source_name": filename, "jurisdiction": jurisdiction, "policy_version": policy_version},
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
    jurisdiction: str | None = None,
    tenant_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return candidate policy-wording documents for document-level compilation."""
    db = SessionLocal()
    try:
        conditions: list[Any] = [KnowledgeDocument.document_type == "policy_wording"]
        if tenant_id:
            conditions.append(KnowledgeDocument.tenant_id == tenant_id)
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
                "document_id": str(row.id),
                "source_name": row.source_name,
                "source_uri": row.source_uri,
                "insurance_type": row.insurance_type,
                "metadata": dict(row.metadata_json or {}),
                "policy_version": (row.metadata_json or {}).get("policy_version"),
            }
            for row in rows
        ]
    finally:
        db.close()


def get_document_chunks(document_id: str, tenant_id: str | None = None) -> list[dict[str, Any]]:
    """Load every indexed chunk for a document in original order."""
    db = SessionLocal()
    try:
        rows = db.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id, *([KnowledgeChunk.tenant_id == tenant_id] if tenant_id else []))
            .order_by(KnowledgeChunk.chunk_index.asc())
        ).scalars().all()
        return [
            {
                "chunk_id": str(row.id),
                "chunk_index": row.chunk_index,
                "text": row.text,
                "metadata": dict(row.metadata_json or {}),
            }
            for row in rows
        ]
    finally:
        db.close()


def get_cached_requirement_manifest(document_id: str, tenant_id: str | None = None) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        row = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id, *([KnowledgeDocument.tenant_id == tenant_id] if tenant_id else [])).first()
        if not row:
            return []
        manifest = (row.metadata_json or {}).get("requirement_manifest")
        return manifest if isinstance(manifest, list) else []
    finally:
        db.close()


def save_requirement_manifest(document_id: str, manifest: list[dict[str, Any]], tenant_id: str | None = None) -> None:
    db = SessionLocal()
    try:
        row = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id, *([KnowledgeDocument.tenant_id == tenant_id] if tenant_id else [])).first()
        if not row:
            return
        row.metadata_json = {
            **(row.metadata_json or {}),
            "requirement_manifest": manifest,
            "requirement_manifest_version": 1,
        }
        db.commit()
    finally:
        db.close()

def search(
    query: str,
    insurance_type: str | None = None,
    policy_number: str | None = None,
    document_types: list[str] | None = None,
    incident_date: date | None = None,
    jurisdiction: str | None = None,
    tenant_id: str | None = None,
    limit: int = 12,
) -> list[dict]:
    vector = embed_documents([query])[0]
    db = SessionLocal()
    try:
        conditions: list[Any] = []
        if tenant_id:
            conditions.append(KnowledgeDocument.tenant_id == tenant_id)
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
                "policy_version": (d.metadata_json or {}).get("policy_version"),
                "effective_from": (d.metadata_json or {}).get("effective_from"),
                "effective_to": (d.metadata_json or {}).get("effective_to"),
                "jurisdiction": d.jurisdiction or (d.metadata_json or {}).get("jurisdiction"),
                "section_number": (c.metadata_json or {}).get("section_number"),
                "section_title": (c.metadata_json or {}).get("section_title"),
                "clause_number": (c.metadata_json or {}).get("clause_number"),
                "page_number": (c.metadata_json or {}).get("page_number"),
                "page_start": (c.metadata_json or {}).get("page_start"),
                "page_end": (c.metadata_json or {}).get("page_end"),
                "score": round(1 - float(dist), 6),
            }
            for c, d, dist in rows
        ]
    finally:
        db.close()

