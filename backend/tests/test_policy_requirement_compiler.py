from unittest.mock import MagicMock, patch

from src.knowledge.policy_compiler import resolve_requirement_manifest
from src.knowledge.requirements import RequirementPlan


def _manifest():
    return [{
        "key": "police_report",
        "label": "Police report",
        "question_hint": "Do you have the police report?",
        "required": True,
        "evidence_type": "document",
        "condition": "if theft or criminal act",
        "category": "evidence",
        "source_section": "Claims Procedure",
        "source_chunk_ids": ["chunk-7"],
        "source_excerpt": "Notify the police immediately in the event of theft.",
        "provenance": {"document_id": "doc-1", "type": "policy_requirement_manifest"},
    }]


def test_policy_manifest_resolution_can_exclude_non_applicable_condition():
    with patch(
        "src.knowledge.policy_compiler.get_configured_llm",
        return_value=MagicMock(),
    ), patch(
        "src.knowledge.policy_compiler.structured_output",
        return_value=MagicMock(
            invoke=MagicMock(return_value=RequirementPlan(requirements=[]))
        ),
    ):
        resolved = resolve_requirement_manifest(
            manifest=_manifest(),
            insurance_type="motor",
            claim_facts={"event_description": "collision with another car"},
        )

    assert resolved == []


def test_policy_manifest_resolution_fallback_never_drops_requirements_on_llm_failure():
    with patch(
        "src.knowledge.policy_compiler.get_configured_llm",
        return_value=MagicMock(),
    ), patch(
        "src.knowledge.policy_compiler.structured_output",
        side_effect=RuntimeError("provider unavailable"),
    ):
        resolved = resolve_requirement_manifest(
            manifest=_manifest(),
            insurance_type="motor",
            claim_facts={"event_description": "collision"},
        )

    assert len(resolved) == 1
    assert resolved[0]["key"] == "police_report"
    assert resolved[0]["source_chunk_ids"] == ["chunk-7"]
    assert resolved[0]["condition"] == "if theft or criminal act"
