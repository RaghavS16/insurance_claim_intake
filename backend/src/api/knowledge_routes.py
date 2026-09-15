"""Policy/regulatory knowledge ingestion and semantic retrieval endpoints."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from src.api.deps import require_role
from src.database.models import User
from src.knowledge.store import ingest_document, search

router=APIRouter(prefix="/api/v1/knowledge",tags=["Knowledge"])

class IngestRequest(BaseModel):
    text:str=Field(...,min_length=20,max_length=500000)
    source_name:str=Field(...,min_length=1,max_length=255)
    document_type:str|None=None
    insurance_type:str|None=None
    policy_number:str|None=None
    effective_from:str|None=None
    effective_to:str|None=None

@router.post("/documents")
def add_document(payload:IngestRequest,user:User=Depends(require_role(["ADJUSTER"]))):
    try:
        return ingest_document(content=payload.text.encode("utf-8"),filename=payload.source_name,document_type=payload.document_type,insurance_type=payload.insurance_type,policy_number=payload.policy_number,effective_from=payload.effective_from,effective_to=payload.effective_to,uploaded_by=str(user.id))
    except Exception as exc:
        raise HTTPException(status_code=502,detail=f"Knowledge indexing failed: {exc}")

@router.post("/upload")
async def upload_document(
    file:UploadFile=File(...),
    document_type:str|None=Form(None),
    insurance_type:str|None=Form(None),
    policy_number:str|None=Form(None),
    effective_from:str|None=Form(None),
    effective_to:str|None=Form(None),
    user:User=Depends(require_role(["ADJUSTER"])),
):
    if not file.filename: raise HTTPException(status_code=400,detail="A document file is required.")
    raw=await file.read()
    try:
        return ingest_document(content=raw,filename=file.filename,document_type=document_type,insurance_type=insurance_type,policy_number=policy_number,effective_from=effective_from,effective_to=effective_to,uploaded_by=str(user.id))
    except ValueError as exc:
        raise HTTPException(status_code=400,detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502,detail=f"Knowledge indexing failed: {exc}")

@router.get("/search")
def retrieve(q:str,user:User=Depends(require_role(["ADMIN","ADJUSTER"])),insurance_type:str|None=None,policy_number:str|None=None,document_type:str|None=None):
    try:
        return {"items":search(q,insurance_type=insurance_type,policy_number=policy_number,document_types=[document_type] if document_type else None),"query":q}
    except Exception as exc:
        raise HTTPException(status_code=502,detail=f"Knowledge retrieval failed: {exc}")
