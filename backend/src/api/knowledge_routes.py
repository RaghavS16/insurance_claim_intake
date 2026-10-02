"""Policy/regulatory knowledge ingestion and semantic retrieval endpoints."""
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from src.api.deps import require_role
from src.database.models import User, KnowledgeDocument
from src.database.session import get_db
from sqlalchemy.orm import Session
from src.knowledge.store import ingest_document, search
from src.utils.upload_limits import read_limited
from src.utils.clamav import scan_bytes

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
        return await asyncio.to_thread(
            ingest_document,
            content=raw,
            filename=file.filename,
            document_type=document_type,
            insurance_type=insurance_type,
            policy_number=policy_number,
            effective_from=effective_from,
            effective_to=effective_to,
            policy_version=policy_version,
            uploaded_by=str(user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Knowledge document upload failed for '%s': %s", file.filename, exc)
        raise HTTPException(status_code=502, detail=f"Knowledge indexing failed: {exc}")

@router.get("/search")
async def retrieve(
    q: str,
    user: User = Depends(require_role(["ADJUSTER"])),
    insurance_type: str | None = None,
    document_type: str | None = None,
    policy_number: str | None = None,
    incident_date: str | None = None,
):
    try:
        items = await asyncio.to_thread(
            search,
            query=q,
            insurance_type=insurance_type,
            document_types=[document_type] if document_type else None,
            policy_number=policy_number,
            incident_date=__import__("datetime").date.fromisoformat(incident_date) if incident_date else None,
        )
        return {"items": items, "query": q}
    except Exception as exc:
        logger.exception("Knowledge search failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Knowledge retrieval failed: {exc}")



@router.post("/documents/{document_id}/publish")
def publish_document(
    document_id: str,
    user: User = Depends(require_role(["ADJUSTER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id).first()
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
