"""Admin knowledge ingestion and retrieval endpoints."""
from __future__ import annotations
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from src.api.deps import get_current_user
from src.database.session import get_db
from src.knowledge.store import ingest_document, search

router=APIRouter(prefix="/api/v1/knowledge",tags=["Knowledge"])

class IngestRequest(BaseModel):
    text:str=Field(...,min_length=20,max_length=500000)
    source_name:str=Field(...,min_length=1,max_length=255)
    document_type:str=Field(...,pattern="^(claim_requirement|policy_wording|regulation|guideline)$")
    insurance_type:str|None=None
    policy_number:str|None=None
    effective_from:str|None=None
    effective_to:str|None=None

def _admin(request:Request,db:Session):
    u=get_current_user(request=request,credentials=None,db=db)
    if u.role!="ADMIN": raise HTTPException(status_code=403,detail="Admin access required.")
    return u

@router.post("/documents")
def ingest(payload:IngestRequest,request:Request,db:Session=Depends(get_db)):
    _admin(request,db)
    return ingest_document(**payload.model_dump())

@router.get("/search")
def retrieve(request:Request,db:Session=Depends(get_db),q:str="",insurance_type:str|None=None,
             policy_number:str|None=None,document_type:str|None=None,incident_date:str|None=None):
    _admin(request,db)
    d=date.fromisoformat(incident_date) if incident_date else None
    return {"items":search(q,insurance_type=insurance_type,policy_number=policy_number,
                            document_types=[document_type] if document_type else None,incident_date=d)}
