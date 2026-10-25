"""Centralized LLM factory with separate low-latency and reasoning profiles, multi-provider failover, and prompt caching."""
from __future__ import annotations

import hashlib
import json
import random
import time
from collections import OrderedDict, defaultdict
from typing import Any, Callable, Generic, TypeVar, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.config import settings
from src.services.observability import record_ai_fallback
from src.utils.logger import app_logger
from src.services.ai_governance import assert_model_allowed

logger = app_logger

T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")


class LLMTransientError(RuntimeError):
    """A retryable upstream LLM/service failure after bounded retries."""


def is_transient_llm_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status in {402, 408, 409, 429, 500, 502, 503, 504}:
        return True
    return any(token in text for token in (
        "402", "429", "500", "502", "503", "504", "rate limit", "rate_limit",
        "no remaining credits", "credit balance", "insufficient_quota",
        "unavailable", "temporarily unavailable", "timeout", "timed out",
        "deadline exceeded", "service busy", "high demand", "getaddrinfo failed",
        "name resolution", "connection error", "connection refused", "connecterror",
        "gaierror", "socket", "errno 11001",
    ))


# ---------------------------------------------------------------------------
# Multi-Key Rotation
# ---------------------------------------------------------------------------
_KEY_INDEX: dict[str, int] = defaultdict(int)


def _split_keys(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]


def _rotate_key(provider: str, raw: str | None) -> str:
    keys = _split_keys(raw)
    if not keys:
        return ""
    idx = _KEY_INDEX[provider] % len(keys)
    _KEY_INDEX[provider] += 1
    return keys[idx]


# ---------------------------------------------------------------------------
# Circuit Breaker Tracking
# ---------------------------------------------------------------------------
_CIRCUIT_COOLDOWN_UNTIL: dict[str, float] = {}


def _get_candidate_key(candidate: Any) -> str:
    model = getattr(candidate, "model", None) or getattr(candidate, "model_name", None) or type(candidate).__name__
    base_url = str(getattr(candidate, "openai_api_base", None) or getattr(candidate, "base_url", None) or type(candidate).__name__)
    raw_key = getattr(candidate, "openai_api_key", None) or getattr(candidate, "google_api_key", None) or ""
    if hasattr(raw_key, "get_secret_value"):
        try:
            raw_key = raw_key.get_secret_value()
        except Exception:
            raw_key = str(raw_key)
    key_fp = hashlib.sha256(str(raw_key).encode("utf-8")).hexdigest()[:6] if raw_key else "nokey"
    prov = "groq" if "groq.com" in base_url else ("hf" if "huggingface.co" in base_url else ("gemini" if "Google" in type(candidate).__name__ else "local"))
    return f"{prov}:{model}:{key_fp}"


def _is_in_cooldown(key: str) -> bool:
    cooldown = _CIRCUIT_COOLDOWN_UNTIL.get(key, 0.0)
    return time.time() < cooldown


def _trip_circuit(key: str, exc: BaseException) -> None:
    text = str(exc).lower()
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    now = time.time()
    if status == 402 or "402" in text or "credit" in text or "quota" in text:
        cooldown_duration = 300.0  # 5 minutes for quota/credit exhaustion
    else:
        cooldown_duration = 45.0   # 45 seconds for 429/503/timeout
    _CIRCUIT_COOLDOWN_UNTIL[key] = now + cooldown_duration
    logger.warning("Circuit breaker tripped for '%s': in cooldown for %.1fs (%s)", key, cooldown_duration, exc)


# ---------------------------------------------------------------------------
# Content-Addressable In-Memory Prompt Cache
# ---------------------------------------------------------------------------
class _PromptCache:
    def __init__(self, maxsize: int = 512, ttl_seconds: float = 3600.0):
        self.maxsize = maxsize
        self.ttl = ttl_seconds
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def _hash_key(self, prompt: Any, extra: str = "") -> str:
        prompt_repr = str(prompt)
        return hashlib.sha256((prompt_repr + "::" + extra).encode("utf-8")).hexdigest()

    def get(self, prompt: Any, extra: str = "") -> Any | None:
        key = self._hash_key(prompt, extra)
        if key in self._cache:
            ts, val = self._cache[key]
            if time.time() - ts < self.ttl:
                self._cache.move_to_end(key)
                return val
            del self._cache[key]
        return None

    def set(self, prompt: Any, value: Any, extra: str = "") -> None:
        key = self._hash_key(prompt, extra)
        if key in self._cache:
            del self._cache[key]
        elif len(self._cache) >= self.maxsize:
            self._cache.popitem(last=False)
        self._cache[key] = (time.time(), value)


_PROMPT_CACHE = _PromptCache()


def invoke_with_retry(operation: Callable[[], R], *, operation_name: str, attempts: int | None = None) -> R:
    """Run an LLM operation with bounded exponential backoff for transient failures."""
    last_exc: BaseException | None = None
    max_attempts = attempts if attempts is not None else 1
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
    """Parse JSON directly without automatic function calling."""

    def __init__(self, model: Any, schema: type[T]):
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

    def invoke(self, prompt: Any) -> T:
        schema_name = getattr(self.schema, "__name__", "Structured")
        cached = _PROMPT_CACHE.get(prompt, extra=schema_name)
        if cached is not None:
            return cached

        candidates = [lambda: self.resilient_model.primary]
        if self.resilient_model.candidate_builders:
            candidates.extend(self.resilient_model.candidate_builders)
        if self.resilient_model.fallback_builder:
            candidates.append(self.resilient_model.fallback_builder)

        last_exc: BaseException | None = None
        for c_fn in candidates:
            if c_fn is self.resilient_model.fallback_builder and not settings.AI_ALLOW_LOCAL_FALLBACK:
                continue
            try:
                c_inst = c_fn() if callable(c_fn) else c_fn
            except Exception as e:
                logger.debug("Structured candidate init skipped: %s", e)
                continue

            c_key = _get_candidate_key(c_inst)
            if _is_in_cooldown(c_key):
                logger.debug("Skipping candidate '%s' in cooldown", c_key)
                continue

            is_local = "ollama" in c_key.lower() or isinstance(c_inst, ChatOllama)
            if is_local and settings.ENVIRONMENT in {"production", "staging"} and not settings.AI_ALLOW_LOCAL_FALLBACK:
                raise RuntimeError("Local Ollama fallback is disabled by AI governance.")

            try:
                helper = _GeminiJsonStructured(c_inst, self.schema)
                res = helper.invoke(prompt)
                _PROMPT_CACHE.set(prompt, res, extra=schema_name)
                return res
            except Exception as exc:
                last_exc = exc
                _trip_circuit(c_key, exc)
                if is_local and not settings.AI_ALLOW_LOCAL_FALLBACK:
                    raise
                if is_transient_llm_error(exc) or "getaddrinfo" in str(exc).lower() or isinstance(exc, (LLMTransientError, OSError)):
                    record_ai_fallback(operation="structured")
                    logger.warning("Structured candidate '%s' failed: %s; failing over (0ms)", c_key, exc)
                    continue
                raise

        if last_exc:
            raise last_exc
        raise RuntimeError("No candidate LLM available for structured output.")


class ResilientChatModel:
    """Wraps primary cloud chat model with circuit breaker, multi-provider failover, and prompt caching."""

    def __init__(
        self,
        primary: Any,
        fallback_builder: Callable[[], BaseChatModel] | None = None,
        candidate_builders: list[Callable[[], BaseChatModel]] | None = None,
    ):
        self.primary = primary
        self.fallback_builder = fallback_builder or (lambda: _build_ollama())
        self.candidate_builders = candidate_builders or []
        self._fallback_instance: BaseChatModel | None = None

    def get_fallback(self) -> BaseChatModel:
        if self._fallback_instance is None:
            self._fallback_instance = self.fallback_builder()
        return self._fallback_instance

    def invoke(self, prompt: Any, *args: Any, **kwargs: Any) -> Any:
        cached = _PROMPT_CACHE.get(prompt)
        if cached is not None:
            return cached

        candidates = [lambda: self.primary]
        if self.candidate_builders:
            candidates.extend(self.candidate_builders)
        if self.fallback_builder:
            candidates.append(self.fallback_builder)

        last_exc: BaseException | None = None
        for c_fn in candidates:
            if c_fn is self.fallback_builder and not settings.AI_ALLOW_LOCAL_FALLBACK:
                continue
            try:
                c_inst = c_fn() if callable(c_fn) else c_fn
            except Exception as e:
                logger.debug("Candidate initialization skipped: %s", e)
                continue

            c_key = _get_candidate_key(c_inst)
            if _is_in_cooldown(c_key):
                logger.debug("Candidate '%s' in circuit breaker cooldown; skipping immediately", c_key)
                continue

            is_local = "ollama" in c_key.lower() or isinstance(c_inst, ChatOllama)
            if is_local and settings.ENVIRONMENT in {"production", "staging"} and not settings.AI_ALLOW_LOCAL_FALLBACK:
                raise RuntimeError("Local Ollama fallback is disabled by AI governance.")

            try:
                res = c_inst.invoke(prompt, *args, **kwargs)
                _PROMPT_CACHE.set(prompt, res)
                return res
            except Exception as exc:
                last_exc = exc
                _trip_circuit(c_key, exc)
                if is_local and not settings.AI_ALLOW_LOCAL_FALLBACK:
                    raise
                if is_transient_llm_error(exc) or "getaddrinfo" in str(exc).lower() or isinstance(exc, (LLMTransientError, OSError)):
                    record_ai_fallback(operation="sync")
                    logger.warning("LLM candidate '%s' transient error: %s; failing over immediately (0ms)", c_key, exc)
                    continue
                raise

        if last_exc:
            raise last_exc
        raise RuntimeError("No candidate LLM available.")

    async def ainvoke(self, prompt: Any, *args: Any, **kwargs: Any) -> Any:
        cached = _PROMPT_CACHE.get(prompt)
        if cached is not None:
            return cached

        candidates = [lambda: self.primary]
        if self.candidate_builders:
            candidates.extend(self.candidate_builders)
        if self.fallback_builder:
            candidates.append(self.fallback_builder)

        last_exc: BaseException | None = None
        for c_fn in candidates:
            if c_fn is self.fallback_builder and not settings.AI_ALLOW_LOCAL_FALLBACK:
                continue
            try:
                c_inst = c_fn() if callable(c_fn) else c_fn
            except Exception as e:
                continue

            c_key = _get_candidate_key(c_inst)
            if _is_in_cooldown(c_key):
                continue

            is_local = "ollama" in c_key.lower() or isinstance(c_inst, ChatOllama)
            if is_local and settings.ENVIRONMENT in {"production", "staging"} and not settings.AI_ALLOW_LOCAL_FALLBACK:
                raise RuntimeError("Local Ollama fallback is disabled by AI governance.")

            try:
                ainvoke_fn = getattr(c_inst, "ainvoke", None)
                if callable(ainvoke_fn):
                    res = await ainvoke_fn(prompt, *args, **kwargs)
                else:
                    res = c_inst.invoke(prompt, *args, **kwargs)
                _PROMPT_CACHE.set(prompt, res)
                return res
            except Exception as exc:
                last_exc = exc
                _trip_circuit(c_key, exc)
                if is_local and not settings.AI_ALLOW_LOCAL_FALLBACK:
                    raise
                if is_transient_llm_error(exc) or "getaddrinfo" in str(exc).lower() or isinstance(exc, (LLMTransientError, OSError)):
                    record_ai_fallback(operation="async")
                    logger.warning("LLM candidate '%s' ainvoke error: %s; failing over immediately (0ms)", c_key, exc)
                    continue
                raise

        if last_exc:
            raise last_exc
        raise RuntimeError("No candidate LLM available for ainvoke.")

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

        client = ollama.Client(host=base_url, timeout=2.0)
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
    if settings.ENVIRONMENT in {"production", "staging"} and not settings.AI_ALLOW_LOCAL_FALLBACK:
        raise RuntimeError("Local Ollama fallback is disabled by AI governance.")
    assert_model_allowed(resolved)
    return ChatOllama(
        base_url=settings.OLLAMA_BASE_URL,
        model=resolved,
        temperature=0,
        timeout=min(settings.LLM_TIMEOUT_SECONDS, 5.0),
    )


def _get_google_api_key() -> str:
    raw_key = settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY
    key = _rotate_key("gemini", raw_key)
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY (or GOOGLE_API_KEY) is required when LLM_PROVIDER=gemini."
        )
    return key


def _build_raw_gemini(model_name: str | None = None) -> BaseChatModel:
    resolved_model = model_name or settings.GEMINI_MODEL
    assert_model_allowed(resolved_model)
    return ChatGoogleGenerativeAI(
        model=resolved_model,
        google_api_key=_get_google_api_key(),
        max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=0,
    )



def _build_raw_huggingface(*, model_name: str, timeout_seconds: float) -> BaseChatModel:
    token = _rotate_key("hf", settings.HF_TOKEN)
    if not token:
        raise RuntimeError("HF_TOKEN is required when using Hugging Face Inference Providers.")
    base_url = (settings.HF_BASE_URL or "https://router.huggingface.co/v1").rstrip("/")
    if "openrouter.ai" in base_url.lower():
        raise RuntimeError("OpenRouter is not supported by the production LLM routing path.")
    model = model_name.strip()
    assert_model_allowed(model)
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
    resolved_model = model_name or settings.CLOUD_LLM_MODEL
    assert_model_allowed(resolved_model)
    primary = ChatOpenAI(
        model=resolved_model,
        api_key=settings.CLOUD_LLM_API_KEY, base_url=base_url, temperature=0,
        max_tokens=2048, max_retries=0, timeout=timeout_seconds or settings.LLM_TIMEOUT_SECONDS,
    )
    return cast(BaseChatModel, ResilientChatModel(primary, lambda: _build_ollama()))


def _build_raw_groq(model_name: str, *, timeout_seconds: float) -> BaseChatModel:
    api_key = _rotate_key("groq", settings.GROQ_API_KEY)
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required when using the direct Groq provider.")
    clean_model = model_name.split(":")[0] if ":" in model_name else model_name
    assert_model_allowed(model_name)
    return ChatOpenAI(
        model=clean_model, api_key=api_key,
        base_url=settings.GROQ_BASE_URL.rstrip("/"), temperature=0,
        max_tokens=2048, max_retries=0, timeout=timeout_seconds,
    )


def _build_configured_fast_llm() -> BaseChatModel:
    provider = (settings.FAST_LLM_PROVIDER or settings.LLM_PROVIDER or "huggingface").lower().strip()
    if provider in ("huggingface", "hf", "inference-providers"):
        return _build_raw_huggingface(model_name=settings.FAST_LLM_MODEL, timeout_seconds=settings.FAST_LLM_TIMEOUT_SECONDS)
    if provider == "groq":
        return _build_raw_groq(settings.FAST_LLM_MODEL, timeout_seconds=settings.FAST_LLM_TIMEOUT_SECONDS)
    if provider in ("gemini", "google"):
        return _build_raw_gemini(settings.GEMINI_FAST_MODEL)
    if provider in ("openai", "cloud"):
        return _build_openai_compatible(timeout_seconds=settings.FAST_LLM_TIMEOUT_SECONDS)
    if provider == "ollama":
        return _build_ollama()
    raise RuntimeError(f"Unsupported fast LLM provider: {provider}")


def _build_configured_reasoning_llm() -> BaseChatModel:
    provider = (settings.REASONING_LLM_PROVIDER or settings.LLM_PROVIDER or "huggingface").lower().strip()
    if provider in ("huggingface", "hf", "inference-providers"):
        return _build_raw_huggingface(model_name=settings.REASONING_LLM_MODEL, timeout_seconds=settings.REASONING_LLM_TIMEOUT_SECONDS)
    if provider == "groq":
        return _build_raw_groq(settings.REASONING_LLM_MODEL, timeout_seconds=settings.REASONING_LLM_TIMEOUT_SECONDS)
    if provider in ("gemini", "google"):
        return _build_raw_gemini(settings.GEMINI_MODEL)
    if provider in ("openai", "cloud"):
        return _build_openai_compatible(timeout_seconds=settings.REASONING_LLM_TIMEOUT_SECONDS)
    if provider == "ollama":
        return _build_ollama()
    raise RuntimeError(f"Unsupported reasoning LLM provider: {provider}")


def get_fast_llm() -> BaseChatModel:
    """Return the low-latency model with zero-cost multi-provider failover."""
    candidates: list[Callable[[], BaseChatModel]] = []

    # Direct Groq candidates
    if settings.GROQ_API_KEY:
        candidates.append(lambda: _build_raw_groq("llama-3.1-8b-instant", timeout_seconds=settings.FAST_LLM_TIMEOUT_SECONDS))
        candidates.append(lambda: _build_raw_groq("openai/gpt-oss-20b", timeout_seconds=settings.FAST_LLM_TIMEOUT_SECONDS))

    # Gemini candidates
    if settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY:
        candidates.append(lambda: _build_raw_gemini("gemini-2.5-flash-lite"))
        candidates.append(lambda: _build_raw_gemini("gemini-2.5-flash"))

    # Hugging Face candidates
    if settings.HF_TOKEN:
        candidates.append(lambda: _build_raw_huggingface(model_name="openai/gpt-oss-20b:groq", timeout_seconds=settings.FAST_LLM_TIMEOUT_SECONDS))
        candidates.append(lambda: _build_raw_huggingface(model_name="meta-llama/Llama-3.3-70B-Instruct:groq", timeout_seconds=settings.FAST_LLM_TIMEOUT_SECONDS))

    # Groq secondary
    if settings.GROQ_API_KEY:
        candidates.append(lambda: _build_raw_groq("llama-3.3-70b-versatile", timeout_seconds=settings.FAST_LLM_TIMEOUT_SECONDS))

    fallback = lambda: _build_ollama("qwen2.5:1.5b")

    primary: Any = None
    try:
        primary = _build_configured_fast_llm()
    except Exception as e:
        logger.warning("Configured fast LLM unavailable (%s); promoting candidate from pool", e)
        if candidates:
            first_builder = candidates.pop(0)
            primary = first_builder()
        else:
            primary = fallback()

    return cast(BaseChatModel, ResilientChatModel(primary, fallback, candidate_builders=candidates))


def get_reasoning_llm() -> BaseChatModel:
    """Return the high-quality model with zero-cost multi-provider failover."""
    candidates: list[Callable[[], BaseChatModel]] = []

    # Direct Groq candidates
    if settings.GROQ_API_KEY:
        candidates.append(lambda: _build_raw_groq("llama-3.3-70b-versatile", timeout_seconds=settings.REASONING_LLM_TIMEOUT_SECONDS))
        candidates.append(lambda: _build_raw_groq("openai/gpt-oss-120b", timeout_seconds=settings.REASONING_LLM_TIMEOUT_SECONDS))

    # Gemini candidates
    if settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY:
        candidates.append(lambda: _build_raw_gemini("gemini-2.5-flash"))
        candidates.append(lambda: _build_raw_gemini("gemini-2.5-flash-lite"))

    # Hugging Face candidates
    if settings.HF_TOKEN:
        candidates.append(lambda: _build_raw_huggingface(model_name="openai/gpt-oss-120b:groq", timeout_seconds=settings.REASONING_LLM_TIMEOUT_SECONDS))
        candidates.append(lambda: _build_raw_huggingface(model_name="meta-llama/Llama-3.3-70B-Instruct:groq", timeout_seconds=settings.REASONING_LLM_TIMEOUT_SECONDS))
        candidates.append(lambda: _build_raw_huggingface(model_name="Qwen/Qwen2.5-72B-Instruct:together", timeout_seconds=settings.REASONING_LLM_TIMEOUT_SECONDS))

    # Groq secondary
    if settings.GROQ_API_KEY:
        candidates.append(lambda: _build_raw_groq("llama-3.1-8b-instant", timeout_seconds=settings.REASONING_LLM_TIMEOUT_SECONDS))

    fallback = lambda: _build_ollama(settings.OLLAMA_MODEL)

    primary: Any = None
    try:
        primary = _build_configured_reasoning_llm()
    except Exception as e:
        logger.warning("Configured reasoning LLM unavailable (%s); promoting candidate from pool", e)
        if candidates:
            first_builder = candidates.pop(0)
            primary = first_builder()
        else:
            primary = fallback()

    return cast(BaseChatModel, ResilientChatModel(primary, fallback, candidate_builders=candidates))


def get_configured_llm() -> BaseChatModel:
    """Return the configured reasoning-capable LLM."""
    return get_reasoning_llm()
