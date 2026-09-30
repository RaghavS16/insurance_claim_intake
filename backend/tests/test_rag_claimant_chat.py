import src.agents.graph as graph


def test_rag_question_responder_answers_question_before_intake(monkeypatch):
    class FakeRetriever:
        def answer_query(self, **kwargs):
            assert kwargs["query"] == "What is the procedure to file a health insurance claim?"
            assert kwargs["insurance_type"] == "health"
            return {
                "answer": "The indexed health-claim guidance says to submit the reimbursement form and supporting medical bills.",
                "grounded": True,
                "sources": [{"source_name": "health-policy.pdf", "document_type": "policy_wording", "text": "Submit the reimbursement form with medical bills."}],
                "status": "OK",
            }

    monkeypatch.setattr(graph, "KnowledgeRetriever", FakeRetriever, raising=False)

    state = {
        "last_user_utterance": "What is the procedure to file a health insurance claim?",
        "last_intent": "claim_detail",
        "extracted_data": {"insurance_type": "health"},
        "recently_extracted_fields": ["insurance_type"],
        "_skip_all": False,
    }
    result = graph._rag_question_responder(state)

    assert result["rag_answer_grounded"] is True
    assert "procedure" in result["rag_answer"].lower() or "submit" in result["rag_answer"].lower()
    assert result["_rag_question_only"] is False


def test_response_planner_preserves_rag_answer_and_asks_only_one_intake_item(monkeypatch):
    monkeypatch.setattr(graph, "analyze_claim_gaps", lambda state: {"user_sentiment": "normal", "flagged_gaps": []})

    state = {
        "rag_answer": "The indexed health-claim guidance says to submit the reimbursement form and supporting medical bills.",
        "rag_answer_grounded": True,
        "last_intent": "question",
        "last_user_utterance": "What is the procedure to file a health insurance claim?",
        "extracted_data": {"insurance_type": "health"},
        "missing_fields": ["policy_id", "event_date", "event_description", "event_location", "estimated_claim_amount"],
        "dynamic_missing": [],
        "missing_evidence": [],
        "pending_evidence_review": [],
        "awaiting_confirmation": False,
        "confirmed": False,
    }

    result = graph._response_planner(state)

    assert result["message"].startswith("The indexed health-claim guidance")
    assert result["message"].count("policy number") == 1
    assert "event date" not in result["message"]


def test_generic_question_does_not_invoke_dynamic_requirement_planner(monkeypatch):
    monkeypatch.setattr(graph, "KnowledgeRetriever", lambda: type(
        "R", (), {"answer_query": lambda self, **kwargs: {
            "answer": "The indexed guidance does not define that term.",
            "grounded": True,
            "sources": [{"source_name": "guide.pdf", "document_type": "guideline", "text": "Definition unavailable."}],
            "status": "OK",
        }}
    )())

    called = {"value": False}

    def fail_if_called(_state):
        called["value"] = True
        raise AssertionError("dynamic requirement planning should not run for a pure Q&A turn")

    original = graph.build_dynamic_context
    monkeypatch.setattr(graph, "build_dynamic_context", fail_if_called)
    state = {
        "last_user_utterance": "What is a deductible?",
        "last_intent": "question",
        "extracted_data": {},
        "recently_extracted_fields": [],
        "_skip_all": False,
    }

    result = graph._rag_question_responder(state)
    assert result["_rag_question_only"] is True
    assert graph._dynamic_requirement_enrichment(result)["rag_answer"].startswith("The indexed")
    assert called["value"] is False
