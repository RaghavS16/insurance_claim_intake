"""Admin-only knowledge ingestion for policy and regulatory RAG."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from src.api.deps import require_role
from src.database.models import User
from src.knowledge.store import ingest, search

router=APIRouter(prefix="/api/v1/knowledge",tags=["Knowledge"])

class IngestRequest(BaseModel):
    text:str=Field(...,min_length=20,max_length=500000)
    source_name:str=Field(...,min_length=1,max_length=255)
    document_type:str=Field(...,pattern="^(policy_wording|regulation|guideline|claim_requirement)$")
    insurance_type:str|None=None
    policy_number:str|None=None
    effective_from:str|None=None
    effective_to:str|None=None

@router.post("/documents")
def add_document(payload:IngestRequest,user:User=Depends(require_role(["ADMIN"]))):
    return ingest(**payload.model_dump())

@router.get("/search")
def retrieve(q:str,user:User=Depends(require_role(["ADMIN","ADJUSTER"])),insurance_type:str|None=None,policy_number:str|None=None,document_type:str|None=None):
    return {"items":search(q,insurance_type=insurance_type,policy_number=policy_number,document_types=[document_type] if document_type else None)}
