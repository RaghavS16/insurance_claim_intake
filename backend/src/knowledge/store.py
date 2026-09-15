"""Lightweight persistent document store used as the repository's RAG adapter."""
from __future__ import annotations
import json,re,uuid
from datetime import date
from pathlib import Path
from src.config import settings

ROOT=Path(settings.UPLOAD_DIR)/"knowledge"
ROOT.mkdir(parents=True,exist_ok=True)

def ingest(text:str,source_name:str,document_type:str,insurance_type:str|None=None,policy_number:str|None=None,effective_from:str|None=None,effective_to:str|None=None)->dict:
    words=text.split(); size=220; chunks=[]
    for i in range(0,len(words),size):
        part=" ".join(words[i:i+size]).strip()
        if part: chunks.append({"id":str(uuid.uuid4()),"text":part,"source_name":source_name,"document_type":document_type,"insurance_type":insurance_type,"policy_number":policy_number,"effective_from":effective_from,"effective_to":effective_to})
    path=ROOT/(uuid.uuid4().hex+".json"); path.write_text(json.dumps({"chunks":chunks},ensure_ascii=False),encoding="utf-8")
    return {"document_id":path.stem,"source_name":source_name,"chunks":len(chunks)}

def _tokens(s:str)->set[str]:
    return {x for x in re.findall(r"[a-z0-9]+",s.lower()) if len(x)>2}

def search(query:str,insurance_type:str|None=None,policy_number:str|None=None,document_types:list[str]|None=None,incident_date:date|None=None,limit:int=6)->list[dict]:
    q=_tokens(query); hits=[]
    for p in ROOT.glob("*.json"):
        try: rows=json.loads(p.read_text(encoding="utf-8")).get("chunks",[])
        except Exception: continue
        for row in rows:
            if insurance_type and row.get("insurance_type") not in (None,insurance_type): continue
            if policy_number and row.get("policy_number") not in (None,policy_number): continue
            if document_types and row.get("document_type") not in document_types: continue
            if incident_date:
                try:
                    if row.get("effective_from") and incident_date < date.fromisoformat(row["effective_from"]): continue
                    if row.get("effective_to") and incident_date > date.fromisoformat(row["effective_to"]): continue
                except ValueError: continue
            score=len(q & _tokens(row.get("text","")))
            if score: hits.append((score,row))
    hits.sort(key=lambda x:x[0],reverse=True)
    return [x[1] for x in hits[:limit]]
