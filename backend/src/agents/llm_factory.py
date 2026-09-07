"""Centralized LLM factory supporting local Ollama and Cloud OpenAI-compatible endpoints."""
from __future__ import annotations

from typing import Any
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from src.config import settings
from src.utils.logger import app_logger

logger = app_logger


def _resolve_ollama_model(base_url: str, requested_model: str) -> str:
    """Check if the requested Ollama model is available locally; fallback to installed models if needed."""
    try:
        import ollama
        client = ollama.Client(host=base_url)
        available = [getattr(m, "model", "") for m in client.list().models]
        # Exact match or prefix match (e.g. model:latest)
        for m in available:
            if m == requested_model or m.split(":")[0] == requested_model.split(":")[0]:
                return requested_model

        # Prioritized local fallbacks
        fallbacks = ["llama3.1:8b", "qwen2.5:1.5b", "llama3:latest", "mistral:latest"]
        for fb in fallbacks:
            for m in available:
                if m == fb or m.split(":")[0] == fb.split(":")[0]:
                    logger.warning(
                        "Configured Ollama model '%s' not found locally. Auto-falling back to installed model '%s'. (Run 'ollama pull %s' to download your chosen model).",
                        requested_model,
                        m,
                        requested_model,
                    )
                    return m
    except Exception as exc:
        logger.debug("Could not verify Ollama models list: %s", exc)
    return requested_model


def get_configured_llm() -> BaseChatModel:
    """Instantiate the chat LLM based on application settings."""
    provider = (settings.LLM_PROVIDER or "ollama").lower().strip()

    if provider in ("cloud", "openai", "openrouter", "dashscope", "together"):
        logger.info(
            "Initializing Cloud LLM model=%s (base_url=%s)",
            settings.CLOUD_LLM_MODEL,
            settings.CLOUD_LLM_BASE_URL,
        )
        return ChatOpenAI(
            model=settings.CLOUD_LLM_MODEL,
            api_key=settings.CLOUD_LLM_API_KEY or "not-needed",
            base_url=settings.CLOUD_LLM_BASE_URL,
            temperature=0,
            max_tokens=1000,
            max_retries=2,
            timeout=30,
        )

    # Local Ollama
    resolved_model = _resolve_ollama_model(settings.OLLAMA_BASE_URL, settings.OLLAMA_MODEL)
    logger.info(
        "Initializing Local Ollama model=%s (base_url=%s)",
        resolved_model,
        settings.OLLAMA_BASE_URL,
    )
    return ChatOllama(
        base_url=settings.OLLAMA_BASE_URL,
        model=resolved_model,
        temperature=0,
        timeout=30,
    )

