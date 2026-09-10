"""Centralized LLM factory supporting local Ollama and cloud OpenAI-compatible endpoints."""
from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from src.config import settings
from src.utils.logger import app_logger

logger = app_logger


def _resolve_ollama_model(base_url: str, requested_model: str) -> str:
    try:
        import ollama
        client = ollama.Client(host=base_url)
        available = [getattr(m, "model", "") for m in client.list().models]
        for model in available:
            if model == requested_model or model.split(":")[0] == requested_model.split(":")[0]:
                return requested_model
        fallbacks = ["llama3.1:8b", "qwen2.5:1.5b", "llama3:latest", "mistral:latest"]
        for fallback in fallbacks:
            for model in available:
                if model == fallback or model.split(":")[0] == fallback.split(":")[0]:
                    logger.warning("Configured Ollama model '%s' unavailable; using '%s'.", requested_model, model)
                    return model
    except Exception as exc:
        logger.debug("Could not verify Ollama model list: %s", exc)
    return requested_model


class ClaimChatOpenAI(ChatOpenAI):
    """OpenAI-compatible chat model with tool/function structured output by default.

    The project extraction schema contains flexible values and provider-backed OpenAI
    JSON-schema response_format rejects that shape. Function calling supports the same
    Pydantic extraction contract without requiring the provider's strict response schema.
    """

    def with_structured_output(self, schema=None, *, method="function_calling", include_raw=False, strict=None, tools=None, **kwargs):
        return super().with_structured_output(
            schema,
            method=method,
            include_raw=include_raw,
            strict=strict,
            tools=tools,
            **kwargs,
        )


def get_configured_llm() -> BaseChatModel:
    provider = (settings.LLM_PROVIDER or "ollama").lower().strip()
    timeout = settings.LLM_TIMEOUT_SECONDS
    if provider in ("cloud", "openai", "openrouter", "dashscope", "together"):
        return ClaimChatOpenAI(
            model=settings.CLOUD_LLM_MODEL,
            api_key=settings.CLOUD_LLM_API_KEY or "not-needed",
            base_url=settings.CLOUD_LLM_BASE_URL,
            temperature=0,
            max_tokens=700,
            max_retries=0,
            timeout=timeout,
        )
    resolved_model = _resolve_ollama_model(settings.OLLAMA_BASE_URL, settings.OLLAMA_MODEL)
    return ChatOllama(
        base_url=settings.OLLAMA_BASE_URL,
        model=resolved_model,
        temperature=0,
        timeout=timeout,
    )
