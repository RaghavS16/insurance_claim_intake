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

def ingest_document(
    *,
    content: bytes,
    filename: str,
    document_type: str | None = None,
    insurance_type: str | None = None,
    policy_number: str | None = None,
    effective_from: str | None = None,
    effective_to: str | None = None,
    uploaded_by: str | None = None,
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
        existing = db.query(KnowledgeDocument).filter(KnowledgeDocument.content_sha256 == content_sha256).first()
        if existing:
            logger.info("[Knowledge] Document '%s' already indexed (SHA: %s).", filename, content_sha256[:8])
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

    chunks = _chunks(text)
    logger.info("[Knowledge] Document partitioned into %d semantic chunks. Generating embeddings...", len(chunks))
    
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
            source_name=filename,
            source_uri=s3["uri"],
            document_type=document_type or meta.document_type or "unknown",
            insurance_type=insurance_type,
            content_sha256=content_sha256,
            uploaded_by=uploaded_by,
            metadata_json={"title": meta.title, "scope": meta.document_scope},
        )
        db.add(doc)
        db.flush()
        
        for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
            db.add(
                KnowledgeChunk(
                    id=str(uuid.uuid4()),
                    document_id=doc.id,
                    chunk_index=idx,
                    text=chunk,
                    embedding=vector,
                    metadata_json={"source_name": filename},
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

def search(
    query: str,
    insurance_type: str | None = None,
    policy_number: str | None = None,
    document_types: list[str] | None = None,
    incident_date: date | None = None,
    limit: int = 12,
) -> list[dict]:
    vector = embed_documents([query])[0]
    db = SessionLocal()
    try:
        conditions: list[Any] = []
        if insurance_type:
            conditions.append((KnowledgeDocument.insurance_type == insurance_type) | (KnowledgeDocument.insurance_type.is_(None)))
        if document_types:
            conditions.append(KnowledgeDocument.document_type.in_(document_types))
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
                "score": round(1 - float(dist), 6),
            }
            for c, d, dist in rows
        ]
    finally:
        db.close()

