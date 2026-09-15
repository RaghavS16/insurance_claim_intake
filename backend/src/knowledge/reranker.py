"""Optional OpenRouter cross-encoder reranking for higher-precision RAG."""
from __future__ import annotations
import requests
from src.config import settings

def rerank(query:str,documents:list[dict],top_n:int=5)->list[dict]:
    if not documents or not settings.CLOUD_LLM_API_KEY or not settings.RERANK_MODEL:
        return documents[:top_n]
    try:
        response=requests.post(
            f"{(settings.EMBEDDING_BASE_URL or settings.CLOUD_LLM_BASE_URL).rstrip('/')}/rerank",
            headers={"Authorization":f"Bearer {settings.CLOUD_LLM_API_KEY}","Content-Type":"application/json"},
            json={"model":settings.RERANK_MODEL,"query":query,"documents":[d["text"] for d in documents],"top_n":min(top_n,len(documents))},
            timeout=settings.RERANK_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        results=response.json().get("results",[])
        ranked=[]
        for item in results:
            idx=int(item.get("index",0))
            doc=dict(documents[idx])
            doc["rerank_score"]=item.get("relevance_score")
            ranked.append(doc)
        return ranked or documents[:top_n]
    except Exception as exc:
        raise RuntimeError(f"Reranker service failed: {type(exc).__name__}") from exc
