"""Embedding client for semantic RAG retrieval."""
from __future__ import annotations
import requests
from src.config import settings

class EmbeddingService:
    def __init__(self) -> None:
        self.base_url = (settings.EMBEDDING_BASE_URL or settings.CLOUD_LLM_BASE_URL or "").rstrip("/")
        self.model = settings.EMBEDDING_MODEL

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not settings.CLOUD_LLM_API_KEY:
            raise RuntimeError("CLOUD_LLM_API_KEY is required for RAG embeddings.")
        response = requests.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {settings.CLOUD_LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": self.model, "input": texts, "encoding_format": "float"},
            timeout=settings.EMBEDDING_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        return [item["embedding"] for item in sorted(payload["data"], key=lambda x: x["index"])]

_embeddings = EmbeddingService()

def embed_documents(texts: list[str]) -> list[list[float]]:
    return _embeddings.embed(texts)
