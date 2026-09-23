"""Centralized LLM factory with separate low-latency and reasoning profiles."""
from __future__ import annotations

import json
import random
import time
from typing import Any, Callable, Generic, TypeVar, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.config import settings
from src.utils.logger import app_logger

logger = app_logger

T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")


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
        "deadline exceeded", "service busy", "high demand", "getaddrinfo failed",
        "name resolution", "connection error", "connection refused", "connecterror",
        "gaierror", "socket", "errno 11001",
    ))


def invoke_with_retry(operation: Callable[[], R], *, operation_name: str, attempts: int | None = None) -> R:
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


class _GeminiJsonStructured(Generic[T]):
    """Parse JSON directly from Gemini without automatic function calling."""

    def __init__(self, model: ChatGoogleGenerativeAI, schema: type[T]):
        self.model = model
        self.schema = schema

    @staticmethod
    def _content_to_text(result: Any) -> str:
        content = getattr(result, "content", result)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))
            return "".join(parts)
        return str(content)

    @staticmethod
    def _extract_json(text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        try:
            json.loads(cleaned)
            return cleaned
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                candidate = cleaned[start:end + 1]
                json.loads(candidate)
                return candidate
            raise

    def invoke(self, prompt: Any) -> T:
        schema_json = json.dumps(self.schema.model_json_schema(), ensure_ascii=False)
        instruction = (
            "\n\nReturn ONLY one valid JSON object. Do not use Markdown, code fences, "
            "explanations, or tool/function calls. The JSON must conform exactly to "
            f"this schema:\n{schema_json}"
        )
        result = self.model.invoke(f"{prompt}{instruction}")
        payload = json.loads(self._extract_json(self._content_to_text(result)))
        return self.schema.model_validate(payload)


class _ResilientStructured(Generic[T]):
    def __init__(self, resilient_model: "ResilientChatModel", schema: type[T]):
        self.resilient_model = resilient_model
        self.schema = schema
        self._gemini_structured = _GeminiJsonStructured(resilient_model.primary, schema)

    def invoke(self, prompt: Any) -> T:
        try:
            return self._gemini_structured.invoke(prompt)
        except Exception as exc:
            if is_transient_llm_error(exc) or "getaddrinfo" in str(exc).lower() or isinstance(exc, (LLMTransientError, OSError)):
                logger.warning("Primary structured LLM failed (%s); falling back to local Ollama.", exc)
                fb = self.resilient_model.get_fallback()
                return structured_output(fb, self.schema).invoke(prompt)
            raise


class ResilientChatModel:
    """Wraps primary cloud chat model with seamless fallback to local Ollama."""

    def __init__(self, primary: Any, fallback_builder: Callable[[], BaseChatModel]):
        self.primary = primary
        self.fallback_builder = fallback_builder
        self._fallback_instance: BaseChatModel | None = None

    def get_fallback(self) -> BaseChatModel:
        if self._fallback_instance is None:
            self._fallback_instance = self.fallback_builder()
        return self._fallback_instance

    def invoke(self, prompt: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return self.primary.invoke(prompt, *args, **kwargs)
        except Exception as exc:
            if is_transient_llm_error(exc) or "getaddrinfo" in str(exc).lower() or isinstance(exc, (LLMTransientError, OSError)):
                logger.warning("Primary LLM invocation failed (%s); falling back to local Ollama.", exc)
                return self.get_fallback().invoke(prompt, *args, **kwargs)
            raise

    async def ainvoke(self, prompt: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            ainvoke_fn = getattr(self.primary, "ainvoke", None)
            if callable(ainvoke_fn):
                return await ainvoke_fn(prompt, *args, **kwargs)
            return self.invoke(prompt, *args, **kwargs)
        except Exception as exc:
            if is_transient_llm_error(exc) or "getaddrinfo" in str(exc).lower() or isinstance(exc, (LLMTransientError, OSError)):
                logger.warning("Primary LLM ainvoke failed (%s); falling back to local Ollama.", exc)
                fb = self.get_fallback()
                fb_ainvoke = getattr(fb, "ainvoke", None)
                if callable(fb_ainvoke):
                    return await fb_ainvoke(prompt, *args, **kwargs)
                return fb.invoke(prompt, *args, **kwargs)
            raise

    def with_structured_output(self, schema: type[T], **kwargs: Any) -> Any:
        return structured_output(self, schema)


def structured_output(model: Any, schema: type[T]) -> Any:
    """Return structured parsing without Gemini automatic function calling."""
    if isinstance(model, ChatGoogleGenerativeAI):
        return _GeminiJsonStructured(model, schema)
    if isinstance(model, ResilientChatModel):
        return _ResilientStructured(model, schema)
    return model.with_structured_output(schema)


def _resolve_ollama_model(base_url: str, requested_model: str) -> str:
    try:
        import ollama

        client = ollama.Client(host=base_url)
        available = [getattr(m, "model", "") for m in client.list().models]
        for model in available:
            if model == requested_model or model.split(":")[0] == requested_model.split(":")[0]:
                return requested_model
        fallbacks = ["qwen2.5:7b-instruct", "qwen2.5:7b", "llama3.1:8b", "qwen2.5:1.5b", "llama3:latest", "mistral:latest"]
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


def _build_ollama(model_name: str | None = None) -> BaseChatModel:
    requested = model_name or settings.OLLAMA_MODEL or "qwen2.5:7b-instruct"
    resolved = _resolve_ollama_model(settings.OLLAMA_BASE_URL, requested)
    return ChatOllama(
        base_url=settings.OLLAMA_BASE_URL,
        model=resolved,
        temperature=0,
        timeout=settings.LLM_TIMEOUT_SECONDS,
    )


def _get_google_api_key() -> str:
    key = settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY (or GOOGLE_API_KEY) is required when LLM_PROVIDER=gemini."
        )
    return key


def _build_gemini(model_name: str | None = None) -> BaseChatModel:
    """Build a direct Google Gemini client wrapped with automatic Ollama fallback."""
    gemini_client = ChatGoogleGenerativeAI(
        model=model_name or settings.GEMINI_MODEL,
        google_api_key=_get_google_api_key(),
        max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=0,
    )
    fallback_model = "qwen2.5:1.5b" if model_name == settings.GEMINI_FAST_MODEL else settings.OLLAMA_MODEL
    return cast(BaseChatModel, ResilientChatModel(gemini_client, lambda: _build_ollama(fallback_model)))


def _build_huggingface(*, model_name: str, timeout_seconds: float) -> BaseChatModel:
    """Build an OpenAI-compatible client through Hugging Face Inference Providers."""
    token = (settings.HF_TOKEN or "").strip()
    if not token:
        raise RuntimeError("HF_TOKEN is required when using Hugging Face Inference Providers.")
    base_url = (settings.HF_BASE_URL or "https://router.huggingface.co/v1").rstrip("/")
    if "openrouter.ai" in base_url.lower():
        raise RuntimeError("OpenRouter is not supported by the production LLM routing path.")
    model = model_name.strip()
    if ":" not in model:
        raise RuntimeError("Hugging Face routing requires a provider-qualified model such as openai/gpt-oss-20b:groq.")
    return ChatOpenAI(
        model=model, api_key=token, base_url=base_url, temperature=0,
        max_tokens=2048, max_retries=0, timeout=timeout_seconds,
    )

def _build_openai_compatible(*, model_name: str | None = None, timeout_seconds: float | None = None) -> BaseChatModel:
    base_url = (settings.CLOUD_LLM_BASE_URL or "").strip()
    if not base_url:
        raise RuntimeError("CLOUD_LLM_BASE_URL is required when LLM_PROVIDER=openai.")
    if "openrouter.ai" in base_url.lower():
        raise RuntimeError("OpenRouter is not supported by the production routing path.")
    if not settings.CLOUD_LLM_API_KEY:
        raise RuntimeError("CLOUD_LLM_API_KEY is required when LLM_PROVIDER=openai.")
    return ChatOpenAI(
        model=model_name or settings.CLOUD_LLM_MODEL,
        api_key=settings.CLOUD_LLM_API_KEY, base_url=base_url, temperature=0,
        max_tokens=2048, max_retries=0, timeout=timeout_seconds or settings.LLM_TIMEOUT_SECONDS,
    )

def _build_groq(model_name: str, *, timeout_seconds: float) -> BaseChatModel:
    """Optional emergency direct-Groq path; HF is the production default."""
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is required when using the direct Groq provider.")
    return ChatOpenAI(
        model=model_name, api_key=settings.GROQ_API_KEY,
        base_url=settings.GROQ_BASE_URL.rstrip("/"), temperature=0,
        max_tokens=2048, max_retries=0, timeout=timeout_seconds,
    )

def get_fast_llm() -> BaseChatModel:
    """Return the low-latency model used for claimant turns."""
    provider = (settings.FAST_LLM_PROVIDER or settings.LLM_PROVIDER or "huggingface").lower().strip()
    if provider in ("huggingface", "hf", "inference-providers"):
        return _build_huggingface(model_name=settings.FAST_LLM_MODEL, timeout_seconds=settings.FAST_LLM_TIMEOUT_SECONDS)
    if provider == "groq":
        return _build_groq(settings.FAST_LLM_MODEL, timeout_seconds=settings.FAST_LLM_TIMEOUT_SECONDS)
    if provider in ("gemini", "google"):
        return _build_gemini(settings.GEMINI_FAST_MODEL)
    if provider in ("openai", "cloud"):
        return _build_openai_compatible(timeout_seconds=settings.FAST_LLM_TIMEOUT_SECONDS)
    if provider == "ollama":
        return _build_ollama()
    raise RuntimeError(f"Unsupported fast LLM provider: {provider}")

def get_reasoning_llm() -> BaseChatModel:
    """Return the higher-quality model for RAG and adjuster analysis."""
    provider = (settings.REASONING_LLM_PROVIDER or settings.LLM_PROVIDER or "huggingface").lower().strip()
    if provider in ("huggingface", "hf", "inference-providers"):
        return _build_huggingface(model_name=settings.REASONING_LLM_MODEL, timeout_seconds=settings.REASONING_LLM_TIMEOUT_SECONDS)
    if provider == "groq":
        return _build_groq(settings.REASONING_LLM_MODEL, timeout_seconds=settings.REASONING_LLM_TIMEOUT_SECONDS)
    if provider in ("gemini", "google"):
        return _build_gemini()
    if provider in ("openai", "cloud"):
        return _build_openai_compatible(timeout_seconds=settings.REASONING_LLM_TIMEOUT_SECONDS)
    if provider == "ollama":
        return _build_ollama()
    raise RuntimeError(f"Unsupported reasoning LLM provider: {provider}")

def get_configured_llm() -> BaseChatModel:
    """Return the configured reasoning-capable LLM."""
    return get_reasoning_llm()
