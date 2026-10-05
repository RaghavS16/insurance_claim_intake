"""Policy/regulatory knowledge ingestion and semantic retrieval endpoints."""
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from src.api.deps import require_role
from src.database.models import User, KnowledgeDocument
from src.database.session import SessionLocal
from src.database.session import get_db
from sqlalchemy.orm import Session
from src.knowledge.store import ingest_document, search
from src.storage.s3 import get_bytes
from src.utils.upload_limits import read_limited
from src.utils.clamav import scan_bytes
from src.services.ai_governance import tenant_ai_guard
from src.services.outbox import enqueue
from src.database.hardening_models import OutboxEvent
from src.storage.s3 import put_bytes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge"])

class IngestRequest(BaseModel):
    text: str = Field(..., min_length=20, max_length=500000)
    source_name: str = Field(..., min_length=1, max_length=255)
    document_type: str | None = None
    insurance_type: str | None = None
    policy_number: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    policy_version: str | None = None
    jurisdiction: str | None = Field(None, max_length=120)

@router.post("/documents")
async def add_document(payload: IngestRequest, user: User = Depends(require_role(["ADJUSTER"]))):
    try:
        return await asyncio.to_thread(
            ingest_document,
            content=payload.text.encode("utf-8"),
            filename=payload.source_name,
            document_type=payload.document_type,
            insurance_type=payload.insurance_type,
            policy_number=payload.policy_number,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            policy_version=payload.policy_version,
            uploaded_by=str(user.id),
            tenant_id=str(user.tenant_id or ""),
            jurisdiction=payload.jurisdiction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Knowledge text indexing failed: %s", exc)
        raise HTTPException(status_code=502, detail="Knowledge indexing is temporarily unavailable.")

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str | None = Form(None),
    insurance_type: str | None = Form(None),
    policy_number: str | None = Form(None),
    effective_from: str | None = Form(None),
    effective_to: str | None = Form(None),
    policy_version: str | None = Form(None),
    jurisdiction: str | None = Form(None),
    user: User = Depends(require_role(["ADJUSTER"])),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="A document file is required.")
    try:
        raw = await read_limited(file, 150 * 1024 * 1024)
        clean, scan_reason = await asyncio.to_thread(scan_bytes, raw)
        if not clean:
            raise HTTPException(status_code=422, detail="The document failed security scanning.")
    except ValueError as exc:
        raise HTTPException(status_code=413, detail="Knowledge document is too large.") from exc
    try:
        staged = await asyncio.to_thread(
            put_bytes,
            raw,
            prefix="knowledge-ingest",
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            metadata={"tenant_id": str(user.tenant_id or ""), "uploaded_by": str(user.id), "ingestion_status": "pending"},
        )
        db = SessionLocal()
        try:
            event = enqueue(
                db,
                event_type="knowledge.ingest",
                aggregate_type="knowledge_document",
                aggregate_id=staged["key"],
                payload={
                    "key": staged["key"],
                    "filename": file.filename,
                    "document_type": document_type,
                    "insurance_type": insurance_type,
                    "policy_number": policy_number,
                    "effective_from": effective_from,
                    "effective_to": effective_to,
                    "policy_version": policy_version,
                    "uploaded_by": str(user.id),
                    "tenant_id": str(user.tenant_id or ""),
                    "jurisdiction": jurisdiction,
                },
                tenant_id=str(user.tenant_id or ""),
                idempotency_key=f"knowledge-ingest:{staged['key']}",
            )
            db.commit()
            return {"status": "queued", "job_id": str(event.id), "source_name": file.filename}
        finally:
            db.close()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Knowledge document staging failed for '%s': %s", file.filename, exc)
        raise HTTPException(status_code=502, detail="Knowledge ingestion could not be queued.")

@router.get("/ingestion/{job_id}")
def ingestion_status(job_id: str, user: User = Depends(require_role(["ADJUSTER", "ADMIN"])), db: Session = Depends(get_db)):
    event = db.query(OutboxEvent).filter(OutboxEvent.id == job_id, OutboxEvent.tenant_id == str(user.tenant_id or "")).first()
    if not event:
        raise HTTPException(status_code=404, detail="Ingestion job not found.")
    return {"job_id": str(event.id), "status": event.status, "attempts": int(event.attempts or 0), "error": event.last_error}


@router.get("/search")
async def retrieve(
    q: str,
    user: User = Depends(require_role(["ADJUSTER"])),
    insurance_type: str | None = None,
    document_type: str | None = None,
    policy_number: str | None = None,
    incident_date: str | None = None,
    jurisdiction: str | None = None,
):
    try:
        async with tenant_ai_guard(str(user.tenant_id or ""), operation="rag_search"):
            items = await asyncio.to_thread(
                search,
                query=q,
                insurance_type=insurance_type,
                document_types=[document_type] if document_type else None,
                policy_number=policy_number,
                incident_date=__import__("datetime").date.fromisoformat(incident_date) if incident_date else None,
                tenant_id=str(user.tenant_id or ""),
                jurisdiction=jurisdiction,
            )
        return {"items": items, "query": q}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Knowledge search failed: %s", exc)
        raise HTTPException(status_code=502, detail="Knowledge retrieval is temporarily unavailable.")




@router.get("/documents")
def list_documents(
    user: User = Depends(require_role(["ADJUSTER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    docs = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.tenant_id == str(user.tenant_id or "")
    ).order_by(KnowledgeDocument.created_at.desc()).limit(500).all()
    return {"items": [
        {
            "id": str(doc.id),
            "source_name": doc.source_name,
            "document_type": doc.document_type,
            "insurance_type": doc.insurance_type,
            "policy_number": (doc.metadata_json or {}).get("policy_number"),
            "policy_version": (doc.metadata_json or {}).get("policy_version") or doc.document_version,
            "jurisdiction": doc.jurisdiction,
            "publication_status": (doc.metadata_json or {}).get("publication_status", "pending_review"),
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "source_uri": doc.source_uri,
            "chunks": len(doc.chunks or []),
        }
        for doc in docs
    ]}


class UpdateDocumentRequest(BaseModel):
    source_name: str | None = Field(None, min_length=1, max_length=255)
    insurance_type: str | None = None
    policy_number: str | None = None
    policy_version: str | None = None
    jurisdiction: str | None = Field(None, max_length=120)
    effective_from: str | None = None
    effective_to: str | None = None
    publication_status: str | None = None


@router.put("/documents/{document_id}")
def update_document(
    document_id: str,
    payload: UpdateDocumentRequest,
    user: User = Depends(require_role(["ADJUSTER"])),
    db: Session = Depends(get_db),
):
    doc = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.tenant_id == str(user.tenant_id or ""),
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Knowledge document not found.")
    allowed_statuses = {"pending_review", "published", "superseded", "archived"}
    if payload.publication_status and payload.publication_status not in allowed_statuses:
        raise HTTPException(status_code=400, detail="Invalid publication status.")
    if payload.source_name is not None:
        doc.source_name = payload.source_name.strip()
    if payload.insurance_type is not None:
        doc.insurance_type = payload.insurance_type.strip() or None
    if payload.policy_version is not None:
        doc.document_version = payload.policy_version.strip() or None
    if payload.jurisdiction is not None:
        doc.jurisdiction = payload.jurisdiction.strip() or None
    meta = dict(doc.metadata_json or {})
    for key in ("policy_number", "effective_from", "effective_to", "policy_version"):
        value = getattr(payload, key)
        if value is not None:
            meta[key] = value.strip() or None
    if payload.publication_status:
        meta["publication_status"] = payload.publication_status
    meta["updated_by"] = str(user.id)
    doc.metadata_json = meta
    db.commit()
    return {"document_id": str(doc.id), "updated": True, "publication_status": meta.get("publication_status")}


@router.put("/documents/{document_id}/content")
async def replace_document_content(
    document_id: str,
    file: UploadFile = File(...),
    document_type: str | None = Form(None),
    insurance_type: str | None = Form(None),
    policy_number: str | None = Form(None),
    policy_version: str | None = Form(None),
    jurisdiction: str | None = Form(None),
    effective_from: str | None = Form(None),
    effective_to: str | None = Form(None),
    user: User = Depends(require_role(["ADJUSTER"])),
    db: Session = Depends(get_db),
):
    old = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.tenant_id == str(user.tenant_id or ""),
    ).first()
    if not old:
        raise HTTPException(status_code=404, detail="Knowledge document not found.")
    if not file.filename:
        raise HTTPException(status_code=400, detail="A document file is required.")
    try:
        raw = await read_limited(file, 150 * 1024 * 1024)
        clean, _scan_reason = await asyncio.to_thread(scan_bytes, raw)
        if not clean:
            raise HTTPException(status_code=422, detail="The document failed security scanning.")
        result = await asyncio.to_thread(
            ingest_document,
            content=raw,
            filename=file.filename,
            document_type=document_type or old.document_type,
            insurance_type=insurance_type or old.insurance_type,
            policy_number=policy_number or (old.metadata_json or {}).get("policy_number"),
            effective_from=effective_from or (old.metadata_json or {}).get("effective_from"),
            effective_to=effective_to or (old.metadata_json or {}).get("effective_to"),
            policy_version=policy_version or (old.metadata_json or {}).get("policy_version") or old.document_version,
            uploaded_by=str(user.id),
            tenant_id=str(user.tenant_id or ""),
            jurisdiction=jurisdiction or old.jurisdiction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Knowledge document replacement failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Knowledge document replacement is temporarily unavailable.") from exc

    new_id = str(result.get("document_id"))
    meta = dict(old.metadata_json or {})
    meta["publication_status"] = "superseded"
    meta["superseded_by"] = new_id
    meta["updated_by"] = str(user.id)
    old.metadata_json = meta
    db.commit()
    return {
        "document_id": str(old.id),
        "replacement_document_id": new_id,
        "status": "completed",
        "chunks": result.get("chunks", 0),
    }

@router.post("/documents/{document_id}/reindex")
async def reindex_document(
    document_id: str,
    user: User = Depends(require_role(["ADJUSTER"])),
    db: Session = Depends(get_db),
):
    doc = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.tenant_id == str(user.tenant_id or ""),
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Knowledge document not found.")

    source_uri = str(doc.source_uri or "")
    key = source_uri
    if source_uri.startswith("s3://"):
        parts = source_uri[5:].split("/", 1)
        if len(parts) != 2:
            raise HTTPException(status_code=409, detail="Stored knowledge object has an invalid URI.")
        key = parts[1]
    elif source_uri.startswith("file://"):
        from urllib.parse import urlparse, unquote
        key = unquote(urlparse(source_uri).path)

    try:
        content = await asyncio.to_thread(get_bytes, key)
    except Exception as exc:
        logger.exception("Knowledge source could not be loaded for re-index: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="The stored source document could not be loaded for re-indexing.")

    meta = dict(doc.metadata_json or {})
    try:
        result = await asyncio.to_thread(
            ingest_document,
            content=content,
            filename=doc.source_name,
            document_type=doc.document_type,
            insurance_type=doc.insurance_type,
            policy_number=meta.get("policy_number"),
            effective_from=meta.get("effective_from"),
            effective_to=meta.get("effective_to"),
            policy_version=meta.get("policy_version") or doc.document_version,
            uploaded_by=str(user.id),
            tenant_id=str(user.tenant_id or ""),
            jurisdiction=doc.jurisdiction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Knowledge re-index failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Knowledge re-indexing is temporarily unavailable.") from exc

    if str(result.get("document_id")) != str(doc.id):
        meta["publication_status"] = "superseded"
        meta["superseded_by"] = str(result.get("document_id"))
        doc.metadata_json = meta
        db.commit()

    return {"document_id": str(doc.id), "reindexed_document_id": str(result.get("document_id")), "status": "completed", "chunks": result.get("chunks", 0)}

@router.post("/documents/{document_id}/publish")
def publish_document(
    document_id: str,
    user: User = Depends(require_role(["ADJUSTER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id, KnowledgeDocument.tenant_id == user.tenant_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Knowledge document not found.")
    meta = dict(doc.metadata_json or {})
    meta["publication_status"] = "published"
    meta["published_by"] = str(user.id)
    from datetime import datetime, timezone
    meta["published_at"] = datetime.now(timezone.utc).isoformat()
    doc.metadata_json = meta
    db.commit()
    return {"document_id": str(doc.id), "publication_status": "published"}
