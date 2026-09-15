"""Admin-only knowledge ingestion for policy and regulatory RAG."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
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
def add_document(payload:IngestRequest,user:User=Depends(require_role(["ADMIN","ADJUSTER"]))):
    return ingest(**payload.model_dump())

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    insurance_type: str | None = Form(None),
    policy_number: str | None = Form(None),
    effective_from: str | None = Form(None),
    effective_to: str | None = Form(None),
    user: User = Depends(require_role(["ADMIN","ADJUSTER"])),
):
    if document_type not in {"policy_wording", "regulation", "guideline", "claim_requirement"}:
        raise HTTPException(status_code=400, detail="Invalid document type.")
    if not file.filename:
        raise HTTPException(status_code=400, detail="A document file is required.")
    raw = await file.read()
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Knowledge document is too large.")
    text = ""
    name = file.filename
    lower = name.lower()
    if lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not extract PDF text: {exc}")
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Use PDF or UTF-8 text/markdown files for knowledge ingestion.")
    if len(text.strip()) < 20:
        raise HTTPException(status_code=400, detail="The document contains too little extractable text.")
    return ingest(text=text, source_name=name, document_type=document_type, insurance_type=insurance_type, policy_number=policy_number, effective_from=effective_from, effective_to=effective_to)

@router.get("/search")
def retrieve(q:str,user:User=Depends(require_role(["ADMIN","ADJUSTER"])),insurance_type:str|None=None,policy_number:str|None=None,document_type:str|None=None):
    return {"items":search(q,insurance_type=insurance_type,policy_number=policy_number,document_types=[document_type] if document_type else None), "query": q}
