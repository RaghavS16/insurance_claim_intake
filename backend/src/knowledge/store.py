"""PostgreSQL/pgvector knowledge store with S3 originals."""
from __future__ import annotations
import hashlib,io,re,uuid
from datetime import date
from pypdf import PdfReader
from sqlalchemy import select
from src.config import settings
from src.database.models import KnowledgeDocument,KnowledgeChunk
from src.database.session import SessionLocal
from src.knowledge.embeddings import embed_documents
from src.knowledge.document_intelligence import infer_metadata
from src.storage.s3 import put_bytes

def _extract_text(content:bytes,filename:str)->str:
    if filename.lower().endswith(".pdf"):
        reader=PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return content.decode("utf-8-sig")

def _chunks(text:str,size:int=450,overlap:int=75)->list[str]:
    words=re.findall(r"\S+",text)
    return [part for i in range(0,len(words),max(1,size-overlap)) if (part:=" ".join(words[i:i+size]).strip())]

def ingest_document(*,content:bytes,filename:str,document_type:str|None=None,insurance_type:str|None=None,policy_number:str|None=None,effective_from:str|None=None,effective_to:str|None=None,uploaded_by:str|None=None)->dict:
    if len(content)>settings.KNOWLEDGE_MAX_UPLOAD_BYTES: raise ValueError("Knowledge document is too large.")
    text=_extract_text(content,filename).strip()
    if len(text)<50: raise ValueError("The document contains too little extractable text.")
    meta=infer_metadata(text,filename,document_type)
    insurance_type=insurance_type or meta.insurance_type
    policy_number=policy_number or meta.policy_number
    effective_from=effective_from or (meta.effective_from.isoformat() if meta.effective_from else None)
    effective_to=effective_to or (meta.effective_to.isoformat() if meta.effective_to else None)
    s3=put_bytes(content,prefix=settings.S3_KNOWLEDGE_PREFIX,filename=filename,content_type="application/pdf" if filename.lower().endswith(".pdf") else "text/plain")
    chunks=_chunks(text); vectors=[]
    for start in range(0,len(chunks),16): vectors.extend(embed_documents(chunks[start:start+16]))
    if len(vectors)!=len(chunks): raise RuntimeError("Embedding service returned an incomplete batch.")
    db=SessionLocal()
    try:
        def as_date(v): return date.fromisoformat(v) if v else None
        doc=KnowledgeDocument(id=str(uuid.uuid4()),source_name=filename,source_uri=s3["uri"],document_type=document_type or meta.document_type or "unknown",insurance_type=insurance_type,policy_number=policy_number,effective_from=as_date(effective_from),effective_to=as_date(effective_to),content_sha256=hashlib.sha256(content).hexdigest(),uploaded_by=uploaded_by,metadata_json={"title":meta.title,"scope":meta.document_scope})
        db.add(doc); db.flush()
        for idx,(chunk,vector) in enumerate(zip(chunks,vectors)):
            db.add(KnowledgeChunk(id=str(uuid.uuid4()),document_id=doc.id,chunk_index=idx,text=chunk,embedding=vector,metadata_json={"source_name":filename}))
        db.commit()
        return {"document_id":doc.id,"source_name":filename,"source_uri":s3["uri"],"chunks":len(chunks),"insurance_type":insurance_type,"policy_number":policy_number}
    except Exception:
        db.rollback(); raise
    finally: db.close()

def search(query:str,insurance_type:str|None=None,policy_number:str|None=None,document_types:list[str]|None=None,incident_date:date|None=None,limit:int=12)->list[dict]:
    vector=embed_documents([query])[0]; db=SessionLocal()
    try:
        conditions=[]
        if insurance_type: conditions.append((KnowledgeDocument.insurance_type==insurance_type)|(KnowledgeDocument.insurance_type.is_(None)))
        if policy_number: conditions.append((KnowledgeDocument.policy_number==policy_number)|(KnowledgeDocument.policy_number.is_(None)))
        if document_types: conditions.append(KnowledgeDocument.document_type.in_(document_types))
        if incident_date:
            conditions.append((KnowledgeDocument.effective_from.is_(None))|(KnowledgeDocument.effective_from<=incident_date))
            conditions.append((KnowledgeDocument.effective_to.is_(None))|(KnowledgeDocument.effective_to>=incident_date))
        distance=KnowledgeChunk.embedding.cosine_distance(vector)
        stmt=select(KnowledgeChunk,KnowledgeDocument,distance.label("distance")).select_from(KnowledgeChunk).join(KnowledgeDocument,KnowledgeChunk.document_id==KnowledgeDocument.id).where(*conditions).order_by(distance).limit(limit)
        rows=db.execute(stmt).all()
        return [{"id":c.id,"text":c.text,"source_name":d.source_name,"source_uri":d.source_uri,"document_type":d.document_type,"insurance_type":d.insurance_type,"policy_number":d.policy_number,"score":round(1-float(dist),6)} for c,d,dist in rows]
    finally: db.close()
