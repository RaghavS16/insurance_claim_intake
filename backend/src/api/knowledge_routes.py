"""
Knowledge document management API routes.

Handles versioned policy wording and IRDAI regulation document
upload, listing, and secure download.
Extracted from the monolithic main.py for clean architectural separation.
"""
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from src.config import settings
from src.database.session import get_db
from src.database.models import KnowledgeDocument, User
from src.utils.validators import validate_enum, VALID_DOCUMENT_TYPES, sanitize_filename
from src.utils.logger import app_logger

logger = app_logger
router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge Base"])


# ---------------------------------------------------------------------------
# Helper: resolve authenticated user from request
# ---------------------------------------------------------------------------
def _resolve_user(request: Request, db: Session) -> User:
    """Resolve authenticated user via the centralized get_current_user dependency."""
    from src.api.main import get_current_user

    auth_header = request.headers.get("authorization", "")
    credentials = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    return get_current_user(request=request, credentials=credentials, db=db)


@router.get("")
def list_knowledge_documents(
    request: Request,
    db: Session = Depends(get_db),
):
    """List all active knowledge documents ordered by most recent."""
    current_user = _resolve_user(request, db)

    docs = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.status == "active")
        .order_by(KnowledgeDocument.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(d.id),
            "document_type": d.document_type,
            "title": d.title,
            "version": d.version,
            "file_reference": d.file_reference,
            "status": d.status,
            "effective_date": str(d.effective_date) if d.effective_date else None,
            "uploaded_by": str(d.uploaded_by) if d.uploaded_by else None,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


@router.post("")
async def upload_knowledge_document(
    request: Request,
    title: str = Form(...),
    version: str = Form(...),
    document_type: str = Form(...),
    effective_date: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a new versioned knowledge document (policy wording or IRDAI regulation)."""
    current_user = _resolve_user(request, db)

    # Validate document type
    try:
        clean_doc_type = validate_enum(document_type, VALID_DOCUMENT_TYPES, "document_type")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Input validation
    if not title.strip():
        raise HTTPException(status_code=400, detail="Document title is required.")
    if len(title.strip()) > 200:
        raise HTTPException(status_code=400, detail="Document title must not exceed 200 characters.")
    if not version.strip():
        raise HTTPException(status_code=400, detail="Document version is required.")
    if len(version.strip()) > 50:
        raise HTTPException(status_code=400, detail="Version must not exceed 50 characters.")
    if not effective_date.strip():
        raise HTTPException(status_code=400, detail="Effective date is required.")

    # Read file with size check
    content = await file.read()
    if len(content) < 100:
        raise HTTPException(status_code=400, detail="Uploaded file is empty or too small.")
    if len(content) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB limit.",
        )

    original_filename = file.filename or "unnamed"
    safe_filename = sanitize_filename(original_filename)
    doc_id = str(uuid.uuid4())
    ext = os.path.splitext(original_filename)[1].lower() or ".pdf"

    knowledge_dir = Path(settings.UPLOAD_DIR) / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    file_path = knowledge_dir / f"{doc_id}{ext}"

    try:
        file_path.write_bytes(content)
    except Exception:
        logger.exception("Failed to write knowledge document to disk")
        raise HTTPException(status_code=500, detail="File upload failed.")

    doc = KnowledgeDocument(
        id=doc_id,
        document_type=clean_doc_type.upper(),
        title=title.strip(),
        version=version.strip(),
        file_reference=str(file_path),
        status="active",
        effective_date=effective_date.strip(),
        uploaded_by=current_user.id,
    )
    db.add(doc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        file_path.unlink(missing_ok=True)
        logger.exception("Failed to persist knowledge document record")
        raise HTTPException(status_code=500, detail="Document record creation failed.")

    return {
        "id": doc_id,
        "title": title.strip(),
        "version": version.strip(),
        "document_type": clean_doc_type.upper(),
        "status": "active",
        "message": "Knowledge document uploaded successfully.",
    }


@router.get("/{doc_id}/download")
def download_knowledge_document(
    doc_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Secure download of a knowledge document.
    Prevents path traversal by resolving the canonical path and checking containment.
    """
    current_user = _resolve_user(request, db)

    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    file_path = Path(str(doc.file_reference))

    # Path traversal prevention: resolve to absolute and check containment
    try:
        resolved = file_path.resolve()
        upload_base = Path(settings.UPLOAD_DIR).resolve()
        if not str(resolved).startswith(str(upload_base)):
            raise ValueError("Path traversal attempt detected")
    except Exception:
        raise HTTPException(status_code=403, detail="Access denied.")

    if not resolved.exists():
        raise HTTPException(status_code=404, detail="Document file not found on disk.")

    return FileResponse(
        path=str(resolved),
        filename=resolved.name,
        media_type="application/octet-stream",
    )
