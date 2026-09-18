"""Optional cross-encoder reranking for higher-precision RAG."""
from __future__ import annotations
import logging
import requests
from src.config import settings

logger = logging.getLogger(__name__)

def rerank(query: str, documents: list[dict], top_n: int = 5) -> list[dict]:
    if not documents or not settings.RERANK_MODEL:
        return documents[:top_n]

    base_url = (settings.EMBEDDING_BASE_URL or settings.CLOUD_LLM_BASE_URL or "").rstrip("/")
    if not base_url or "openrouter.ai" in base_url:
        return documents[:top_n]

    api_key = settings.EMBEDDING_API_KEY or settings.CLOUD_LLM_API_KEY
    if not api_key:
        return documents[:top_n]

    try:
        response = requests.post(
            f"{base_url}/rerank",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": settings.RERANK_MODEL, "query": query, "documents": [d["text"] for d in documents], "top_n": min(top_n, len(documents))},
            timeout=settings.RERANK_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        ranked = []
        for item in results:
            idx = int(item.get("index", 0))
            if idx < len(documents):
                doc = dict(documents[idx])
                doc["rerank_score"] = item.get("relevance_score")
                ranked.append(doc)
        return ranked or documents[:top_n]
    except Exception as exc:
        logger.warning("Reranker service failed (%s), returning original search results: %s", exc.__class__.__name__, exc)
        return documents[:top_n]

