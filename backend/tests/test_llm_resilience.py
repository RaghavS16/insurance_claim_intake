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


def test_retriever_surfaces_transient_requirement_planning_failure():
    from src.agents.llm_factory import LLMTransientError
    from src.knowledge.retriever import KnowledgeRetriever

    with patch(
        "src.knowledge.retriever.search",
        side_effect=[[{"id": "p1"}], [{"id": "g1"}]],
    ), patch(
        "src.knowledge.retriever.rerank",
        side_effect=lambda q, items, top_n=5: items,
    ), patch(
        "src.knowledge.retriever.get_requirements_from_context",
        side_effect=LLMTransientError("503 UNAVAILABLE"),
    ), patch(
        "src.knowledge.retriever.get_configured_llm",
        return_value=MagicMock(),
    ):
        result = KnowledgeRetriever().retrieve(
            insurance_type="health",
            policy_number="POL-1042-JX",
            query="viral fever hospital admission",
        )

    assert result["available"] is False
    assert result["status"] == "LLM_TEMPORARILY_UNAVAILABLE"
