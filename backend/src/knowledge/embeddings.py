"""Embedding client for semantic RAG retrieval with support for Free Production & Local providers."""
from __future__ import annotations
import logging
import requests
from src.config import settings

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self) -> None:
        self._fastembed_model = None

    def _embed_gemini(self, texts: list[str], api_key: str, model_name: str | None = None) -> list[list[float]]:
        import time
        model = model_name or "gemini-embedding-001"
        if model.startswith("models/"):
            model = model[len("models/"):]
        if model == "text-embedding-004":
            model = "gemini-embedding-001"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents?key={api_key}"
        all_embeddings: list[list[float]] = []

        # Send in batches of 30 chunks with gentle pacing to stay under Google's burst token quota
        batch_size = 30
        for i in range(0, len(texts), batch_size):
            chunk_batch = texts[i:i + batch_size]
            payload = {
                "requests": [
                    {
                        "model": f"models/{model}",
                        "content": {"parts": [{"text": t}]},
                        "outputDimensionality": 768,
                    }
                    for t in chunk_batch
                ]
            }

            # Fast timeout and minimal retries for short real-time search queries
            is_single_query = len(texts) <= 2
            max_retries = 1 if is_single_query else 3
            query_timeout = 5 if is_single_query else settings.EMBEDDING_TIMEOUT_SECONDS

            for attempt in range(max_retries):
                try:
                    response = requests.post(url, json=payload, timeout=query_timeout)
                    if response.status_code == 429 and attempt < max_retries - 1:
                        sleep_time = 1.0 * (attempt + 1)
                        logger.warning("Gemini API rate limit hit (429). Retrying in %.1f seconds...", sleep_time)
                        time.sleep(sleep_time)
                        continue
                    response.raise_for_status()
                    data = response.json()
                    raw_embeddings = data.get("embeddings", [])
                    all_embeddings.extend([item["values"] for item in raw_embeddings])
                    break
                except requests.exceptions.RequestException as exc:
                    if attempt < max_retries - 1 and getattr(getattr(exc, "response", None), "status_code", None) == 429:
                        time.sleep(1.0)
                    else:
                        raise
            
            if not is_single_query:
                time.sleep(0.2)

        return all_embeddings

    def _embed_fastembed(self, texts: list[str], model_name: str | None = None) -> list[list[float]]:
        try:
            from fastembed import TextEmbedding
        except ImportError:
            raise RuntimeError("fastembed package is required for in-memory embedded model. Run: pip install fastembed")
        
        target_model = model_name or "BAAI/bge-base-en-v1.5"
        if self._fastembed_model is None or getattr(self._fastembed_model, "model_name", None) != target_model:
            logger.info("Initializing FastEmbed model '%s' (runs locally in RAM)...", target_model)
            self._fastembed_model = TextEmbedding(model_name=target_model)
        return [list(vec) for vec in self._fastembed_model.embed(texts, batch_size=64)]

    def _embed_openai_compatible(self, texts: list[str], base_url: str, model: str, api_key: str) -> list[list[float]]:
        is_local = "localhost" in base_url or "127.0.0.1" in base_url
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        elif not is_local and settings.CLOUD_LLM_API_KEY:
            headers["Authorization"] = f"Bearer {settings.CLOUD_LLM_API_KEY}"
        elif not is_local:
            raise RuntimeError(
                f"Embedding API key is required when calling remote endpoint '{base_url}'. "
                "Please configure EMBEDDING_API_KEY in your .env."
            )

        url = f"{base_url}/embeddings"
        payload = {"model": model, "input": texts, "encoding_format": "float"}
        response = requests.post(url, headers=headers, json=payload, timeout=settings.EMBEDDING_TIMEOUT_SECONDS)
        response.raise_for_status()
        res_json = response.json()
        if "data" in res_json:
            return [item["embedding"] for item in sorted(res_json["data"], key=lambda x: x.get("index", 0))]
        elif "embedding" in res_json:
            return [res_json["embedding"]]
        elif "embeddings" in res_json:
            return res_json["embeddings"]
        else:
            raise ValueError(f"Unrecognized embedding response format: {list(res_json.keys())}")

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        provider = (settings.EMBEDDING_PROVIDER or "ollama").lower().strip()
        gemini_key = settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY or (settings.EMBEDDING_API_KEY if provider == "gemini" else None)

        # 1. Google Gemini (100% Free Production Tier - 1500 RPM, 768-dim)
        if provider == "gemini" or (gemini_key and (provider not in ("ollama", "openai", "fastembed"))):
            if not gemini_key:
                raise RuntimeError("GEMINI_API_KEY is required when EMBEDDING_PROVIDER=gemini.")
            return self._embed_gemini(texts, gemini_key, settings.EMBEDDING_MODEL if "text-embedding" in (settings.EMBEDDING_MODEL or "") else "text-embedding-004")

        # 2. In-Memory Embedded ONNX (100% Free, zero external network dependency)
        if provider in ("fastembed", "local", "inmemory"):
            return self._embed_fastembed(texts, settings.EMBEDDING_MODEL)

        # 3. OpenAI-compatible / Ollama / Cloud
        raw_url = (settings.EMBEDDING_BASE_URL or "").rstrip("/")
        if not raw_url or "openrouter.ai" in raw_url:
            base_url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/v1"
            model = settings.EMBEDDING_MODEL or "nomic-embed-text"
            api_key = settings.EMBEDDING_API_KEY or ""
        else:
            base_url = raw_url
            model = settings.EMBEDDING_MODEL
            api_key = settings.EMBEDDING_API_KEY or settings.CLOUD_LLM_API_KEY or ""

        try:
            return self._embed_openai_compatible(texts, base_url, model, api_key)
        except requests.exceptions.RequestException as exc:
            logger.error("Embedding request failed: %s", exc)
            raise RuntimeError(f"Embedding service failed: {exc}") from exc

_embeddings = EmbeddingService()

def embed_documents(texts: list[str]) -> list[list[float]]:
    return _embeddings.embed(texts)


