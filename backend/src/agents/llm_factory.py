"""Centralized LLM factory for production insurance-claim conversations.

Primary cloud path is direct Google Gemini (no model router). Local Ollama remains
available for development/offline testing, and OpenAI-compatible endpoints remain
available when explicitly selected.
"""
from __future__ import annotations

import random
import time
from typing import Any, Callable, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from src.config import settings
from src.utils.logger import app_logger

logger = app_logger

T = TypeVar("T")


class LLMTransientError(RuntimeError):
    """A retryable upstream LLM/service failure after bounded retries."""


def is_transient_llm_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status in {408, 409, 429, 500, 502, 503, 504}:
        return True
    return any(token in text for token in (
        "429", "500", "502", "503", "504", "rate limit", "rate_limit",
        "unavailable", "temporarily unavailable", "timeout", "timed out",
        "deadline exceeded", "service busy", "high demand",
    ))


def invoke_with_retry(operation: Callable[[], T], *, operation_name: str, attempts: int | None = None) -> T:
    """Run an LLM operation with bounded exponential backoff for transient failures."""
    last_exc: BaseException | None = None
    max_attempts = attempts if attempts is not None else settings.LLM_RETRY_ATTEMPTS
    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            return operation()
        except Exception as exc:
            last_exc = exc
            if not is_transient_llm_error(exc) or attempt >= max_attempts:
                if is_transient_llm_error(exc):
                    raise LLMTransientError(
                        f"{operation_name} failed after {attempt} attempts: {exc}"
                    ) from exc
                raise
            delay = min(8.0, settings.LLM_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))) + random.uniform(0.0, 0.35)
            logger.warning(
                "%s transient LLM failure (attempt %s/%s): %s; retrying in %.2fs",
                operation_name, attempt, max_attempts, exc, delay,
            )
            time.sleep(delay)
    raise LLMTransientError(f"{operation_name} failed: {last_exc}") from last_exc


def structured_output(model: Any, schema: type[T]) -> Any:
    """Use Gemini native JSON schema instead of tool/AFC-based structured output."""
    if isinstance(model, ChatGoogleGenerativeAI):
        return model.with_structured_output(schema, method="json_schema")
    return model.with_structured_output(schema)


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
                    logger.warning(
                        "Configured Ollama model '%s' unavailable; using '%s'.",
                        requested_model,
                        model,
                    )
                    return model
    except Exception as exc:
        logger.debug("Could not verify Ollama model list: %s", exc)
    return requested_model


def _get_google_api_key() -> str:
    key = settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY (or GOOGLE_API_KEY) is required when LLM_PROVIDER=gemini."
        )
    return key


def _build_gemini() -> BaseChatModel:
    """Build the direct Google Gemini chat client.

    Gemini 3.8 Flash is used for fast conversational extraction, dynamic
    requirement planning, and response generation. Structured output is handled
    by LangChain's native Gemini integration rather than an OpenAI-compatible
    router.
    """
    return ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        google_api_key=_get_google_api_key(),
        temperature=0,
        max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=1,
    )


def _build_openai_compatible() -> BaseChatModel:
    base_url = (settings.CLOUD_LLM_BASE_URL or "").strip()
    if not base_url:
        raise RuntimeError("CLOUD_LLM_BASE_URL is required when LLM_PROVIDER=openai.")

    if "openrouter.ai" in base_url.lower():
        raise RuntimeError(
            "OpenRouter is intentionally unsupported for production claim intake. "
            "Use LLM_PROVIDER=gemini for the primary cloud path or configure a direct "
            "OpenAI-compatible provider."
        )

    if not settings.CLOUD_LLM_API_KEY:
        raise RuntimeError("CLOUD_LLM_API_KEY is required when LLM_PROVIDER=openai.")

    return ChatOpenAI(
        model=settings.CLOUD_LLM_MODEL,
        api_key=settings.CLOUD_LLM_API_KEY,
        base_url=base_url,
        temperature=0,
        max_tokens=2048,
        max_retries=0,
        timeout=settings.LLM_TIMEOUT_SECONDS,
    )


def get_configured_llm() -> BaseChatModel:
    provider = (settings.LLM_PROVIDER or "gemini").lower().strip()

    if provider in ("gemini", "google"):
        return _build_gemini()

    if provider in ("openai", "cloud"):
        return _build_openai_compatible()

    if provider == "ollama":
        resolved_model = _resolve_ollama_model(settings.OLLAMA_BASE_URL, settings.OLLAMA_MODEL)
        return ChatOllama(
            base_url=settings.OLLAMA_BASE_URL,
            model=resolved_model,
            temperature=0,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )

    raise RuntimeError(
        f"Unsupported LLM_PROVIDER='{provider}'. "
        "Supported providers: gemini, openai, ollama."
    )
