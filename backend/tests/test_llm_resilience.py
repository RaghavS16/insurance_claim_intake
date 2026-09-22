"""Tests for resilient Gemini/LLM invocation behavior."""
from unittest.mock import MagicMock, patch

import pytest


def test_invoke_with_retry_retries_transient_failure():
    from src.agents.llm_factory import invoke_with_retry

    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("503 UNAVAILABLE: high demand")
        return "ok"

    with patch("src.agents.llm_factory.time.sleep") as sleep:
        assert invoke_with_retry(operation, operation_name="test", attempts=3) == "ok"

    assert calls["count"] == 3
    assert sleep.call_count == 2


def test_invoke_with_retry_raises_typed_transient_error_after_exhaustion():
    from src.agents.llm_factory import LLMTransientError, invoke_with_retry

    with patch("src.agents.llm_factory.time.sleep"):
        with pytest.raises(LLMTransientError):
            invoke_with_retry(
                lambda: (_ for _ in ()).throw(RuntimeError("503 UNAVAILABLE")),
                operation_name="test",
                attempts=2,
            )


def test_gemini_structured_output_uses_native_json_schema():
    from src.agents.llm_factory import structured_output

    fake_model = MagicMock()
    fake_model.with_structured_output.return_value = "structured"

    # A generic mock remains compatible with non-Gemini providers.
    assert structured_output(fake_model, dict) == "structured"
    fake_model.with_structured_output.assert_called_once_with(dict)
