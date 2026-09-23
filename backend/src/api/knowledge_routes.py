"""Policy/regulatory knowledge ingestion and semantic retrieval endpoints."""
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from src.api.deps import require_role
from src.database.models import User
from src.knowledge.store import ingest_document, search

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge"])

class IngestRequest(BaseModel):
    text: str = Field(..., min_length=20, max_length=500000)
    source_name: str = Field(..., min_length=1, max_length=255)
    document_type: str | None = None
    insurance_type: str | None = None

@router.post("/documents")
async def add_document(payload: IngestRequest, user: User = Depends(require_role(["ADJUSTER"]))):
    try:
        return await asyncio.to_thread(
            ingest_document,
            content=payload.text.encode("utf-8"),
            filename=payload.source_name,
            document_type=payload.document_type,
            insurance_type=payload.insurance_type,
            uploaded_by=str(user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Knowledge text indexing failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Knowledge indexing failed: {exc}")

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str | None = Form(None),
    insurance_type: str | None = Form(None),
    user: User = Depends(require_role(["ADJUSTER"])),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="A document file is required.")
    raw = await file.read()
    try:
        return await asyncio.to_thread(
            ingest_document,
            content=raw,
            filename=file.filename,
            document_type=document_type,
            insurance_type=insurance_type,
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
):
    try:
        items = await asyncio.to_thread(
            search,
            query=q,
            insurance_type=insurance_type,
            document_types=[document_type] if document_type else None,
        )
        return {"items": items, "query": q}
    except Exception as exc:
        logger.exception("Knowledge search failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Knowledge retrieval failed: {exc}")

