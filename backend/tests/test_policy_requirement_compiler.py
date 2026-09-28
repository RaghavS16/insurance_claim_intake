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


def test_policy_manifest_preserves_provenance_after_resolution():
    manifest = _manifest()
    with patch(
        "src.knowledge.policy_compiler.get_configured_llm",
        return_value=MagicMock(),
    ), patch(
        "src.knowledge.policy_compiler.structured_output",
        return_value=MagicMock(
            invoke=MagicMock(return_value=RequirementPlan(requirements=[
                manifest[0] | {"provenance": {}}
            ]))
        ),
    ):
        resolved = resolve_requirement_manifest(
            manifest=manifest,
            insurance_type="motor",
            claim_facts={"event_description": "theft"},
        )
    assert resolved[0]["provenance"]["document_id"] == "doc-1"
    assert resolved[0]["source_chunk_ids"] == ["chunk-7"]


def test_policy_compilation_fails_closed_when_any_source_batch_fails():
    from src.knowledge.policy_compiler import compile_policy_requirements

    llm = MagicMock()
    chunks = [
        {"chunk_id": f"chunk-{i}", "text": f"policy text {i}"}
        for i in range(5)
    ]
    with patch(
        "src.knowledge.policy_compiler.get_configured_llm",
        return_value=llm,
    ), patch(
        "src.knowledge.policy_compiler._compile_batch",
        side_effect=[[], RuntimeError("provider unavailable")],
    ):
        try:
            compile_policy_requirements(
                document_id="doc-1",
                insurance_type="motor",
                chunks=chunks,
                llm=llm,
            )
            assert False, "expected fail-closed compilation"
        except RuntimeError as exc:
            assert "batch 2" in str(exc)
