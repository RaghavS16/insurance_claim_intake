from unittest.mock import MagicMock, patch

from src.knowledge.requirement_compiler import RequirementCandidate, compile_policy_document
from src.knowledge.requirements import get_requirements_from_context
from src.knowledge.retriever import KnowledgeRetriever


def test_requirement_compiler_uses_all_policy_chunks():
    llm = MagicMock()
    batches = []

    def fake_extract(model, insurance_type, chunks):
        batches.append([c["chunk_id"] for c in chunks])
        if len(batches) == 1:
            return [RequirementCandidate(
                key="driver_license",
                label="Driver licence",
                question_hint="Who was driving, and can you share the driver's licence details?",
                source_chunk_ids=["c1"],
                source_excerpt="The driver must hold a valid licence.",
            )]
        return [RequirementCandidate(
            key="police_report",
            label="Police report",
            question_hint="Do you have a police report or FIR?",
            condition="theft or criminal act",
            evidence_type="document",
            source_chunk_ids=["c2"],
            source_excerpt="Notify the police in the event of theft or criminal acts.",
        )]

    def fake_synth(model, *, insurance_type, document_id, candidates):
        return type("Manifest", (), {
            "model_dump": lambda self: {
                "insurance_type": insurance_type,
                "source_document_id": document_id,
                "requirements": [c.model_dump() for c in candidates],
                "compilation_version": "policy-manifest-v1",
                "rationale": "",
            }
        })()

    with patch("src.knowledge.requirement_compiler._extract_batch", side_effect=fake_extract),          patch("src.knowledge.requirement_compiler._synthesise_manifest", side_effect=fake_synth):
        result = compile_policy_document(
            document_id="doc1",
            insurance_type="motor",
            chunks=[
                {"chunk_id": "c1", "text": "driver requirement"},
                {"chunk_id": "c2", "text": "police requirement"},
            ],
            llm=llm,
        )

    assert result["source_document_id"] == "doc1"
    assert {x["key"] for x in result["requirements"]} == {"driver_license", "police_report"}
    assert batches == [["c1", "c2"]]


def test_claim_resolution_uses_manifest_even_when_retrieved_chunks_are_irrelevant():
    manifest = {
        "insurance_type": "motor",
        "source_document_id": "doc1",
        "requirements": [
            {
                "key": "driver_license",
                "label": "Driver licence",
                "question_hint": "Who was driving the bike, and can you share the driver's licence details?",
                "required": True,
                "evidence_type": None,
                "condition": None,
                "category": "claim_information",
                "basis": "necessary_for_assessment",
                "source_chunk_ids": ["c17"],
                "source_excerpt": "The driver must hold a valid licence.",
            },
            {
                "key": "police_report",
                "label": "Police report",
                "question_hint": "Do you have a police report or FIR?",
                "required": True,
                "evidence_type": "document",
                "condition": "theft or criminal act",
                "category": "evidence",
                "basis": "explicit",
                "source_chunk_ids": ["c88"],
                "source_excerpt": "Notify the police in the event of theft or criminal acts.",
            },
        ],
    }

    fake_result = type("Plan", (), {
        "requirements": [
            type("Req", (), {
                "key": "driver_license",
                "label": "Driver licence",
                "question_hint": "Who was driving the bike, and can you share the driver's licence details?",
                "required": True,
                "evidence_type": None,
                "condition": None,
                "model_dump": lambda self: {
                    "key": self.key,
                    "label": self.label,
                    "question_hint": self.question_hint,
                    "required": self.required,
                    "evidence_type": self.evidence_type,
                    "condition": self.condition,
                },
            })()
        ]
    })()

    llm = MagicMock()
    with patch("src.knowledge.requirements.structured_output") as structured:
        structured.return_value.invoke.return_value = fake_result
        result = get_requirements_from_context(
            llm,
            insurance_type="motor",
            policy_context=[],
            regulatory_context=[],
            incident_description="bike collision",
            claim_facts={"insurance_type": "motor", "third_party_involved": True},
            policy_manifest=manifest,
        )

    assert result[0]["key"] == "driver_license"
    assert result[0]["provenance"]["type"] == "policy_requirement_manifest"
    assert result[0]["provenance"]["manifest_source_chunk_ids"] == ["c17"]


def test_retriever_does_not_require_accident_similarity_when_manifest_exists():
    manifest = {
        "insurance_type": "motor",
        "source_document_id": "doc1",
        "requirements": [{
            "key": "driver_license",
            "label": "Driver licence",
            "question_hint": "Who was driving?",
            "required": True,
            "evidence_type": None,
            "condition": None,
        }],
    }
    with patch("src.knowledge.retriever.get_or_compile_policy_manifest", return_value=manifest),          patch("src.knowledge.retriever.search", return_value=[]),          patch("src.knowledge.retriever.get_configured_llm", return_value=MagicMock()),          patch("src.knowledge.retriever.get_requirements_from_context", return_value=[{
             "key": "driver_license",
             "label": "Driver licence",
             "question_hint": "Who was driving?",
             "required": True,
             "evidence_type": None,
         }]):
        result = KnowledgeRetriever().retrieve(
            insurance_type="motor",
            policy_number="POL-1409-XI",
            query="minor collision near junction",
            claim_facts={"event_description": "minor collision near junction"},
        )

    assert result["status"] == "OK"
    assert result["authoritative"] is True
    assert result["policy_manifest"] == manifest
    assert result["requirements"][0]["key"] == "driver_license"
