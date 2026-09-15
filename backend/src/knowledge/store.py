"""Small, dependency-light persistent retrieval store for policy/regulatory RAG.

Documents are chunked into JSONL under UPLOAD_DIR/knowledge. Retrieval is lexical with
metadata and temporal filtering. The interface is intentionally compatible with a future
vector/pgvector implementation.
"""
from __future__ import annotations
import json, re, uuid
from datetime import date
from pathlib import Path
from src.config import settings

ROOT=Path(settings.UPLOAD_DIR)/"knowledge"
ROOT.mkdir(parents=True,exist_ok=True)

def _tokens(text:str)->set[str]:
    return {x for x in re.findall(r"[a-z0-9]+",text.lower()) if len(x)>2}

def ingest_document(text:str, *, source_name:str, document_type:str, insurance_type:str|None=None,
                    policy_number:str|None=None, effective_from:str|None=None, effective_to:str|None=None,
                    chunk_size:int=1200)->dict:
    words=text.split()
    chunks=[]
    for i in range(0,len(words),max(100,chunk_size//5)):
        part=" ".join(words[i:i+max(100,chunk_size//5)]).strip()
        if not part: continue
        chunks.append({"id":str(uuid.uuid4()),"text":part,"document_type":document_type,
                       "insurance_type":insurance_type,"policy_number":policy_number,
                       "effective_from":effective_from,"effective_to":effective_to,
                       "source_name":source_name})
    path=ROOT/f"{uuid.uuid4()}.json"
    path.write_text(json.dumps({"source_name":source_name,"chunks":chunks},ensure_ascii=False),encoding="utf-8")
    return {"document_id":path.stem,"source_name":source_name,"chunks":len(chunks)}

def _date_ok(row:dict, incident_date:date|None)->bool:
    if not incident_date: return True
    try:
        if row.get("effective_from") and incident_date < date.fromisoformat(row["effective_from"]): return False
        if row.get("effective_to") and incident_date > date.fromisoformat(row["effective_to"]): return False
    except ValueError: return False
    return True

def search(query:str, *, insurance_type:str|None=None, policy_number:str|None=None,
           document_types:list[str]|None=None, incident_date:date|None=None, limit:int=6)->list[dict]:
    q=_tokens(query); scored=[]
    for path in ROOT.glob("*.json"):
        try: payload=json.loads(path.read_text(encoding="utf-8"))
        except Exception: continue
        for row in payload.get("chunks",[]):
            if insurance_type and row.get("insurance_type") not in (None,insurance_type): continue
            if policy_number and row.get("policy_number") not in (None,policy_number): continue
            if document_types and row.get("document_type") not in document_types: continue
            if not _date_ok(row,incident_date): continue
            score=len(q & _tokens(row.get("text","")))
            if score: scored.append((score,row))
    scored.sort(key=lambda x:x[0],reverse=True)
    return [r for _,r in scored[:limit]]
