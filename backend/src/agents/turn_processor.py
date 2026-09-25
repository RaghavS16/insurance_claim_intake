"""Shared, transaction-safe claim conversation turn processing."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable, Dict

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from src.agents.graph import build_conversation_graph
from src.database.models import Claim, ConversationTurn
from src.database.hardening_models import ClaimRequirement
from src.utils.logger import app_logger

logger = app_logger


async def process_claimant_turn(
    db: Session,
    claim: Claim,
    user_text: str,
    input_mode: str,
    turn_number: int | None = None,
    is_turn_current: Callable[[], bool] | None = None,
) -> Dict[str, Any]:
    """Process one claimant turn without blocking the event loop during LLM work."""
    from src.agents.policy_check import verify_policy_for_claim
    from src.database.claim_workflow import assign_claim, transition_claim

    if claim.status in {"submitted", "assigned", "under_review", "closed"}:
        prior_turns = db.query(ConversationTurn).filter(ConversationTurn.claim_id == claim.id).count()
        logical_turn = (prior_turns // 2) + 1
        agent_reply = f"Your claim #{claim.ticket_id} has been submitted and is currently being processed by our adjusters."
        try:
            db.add(ConversationTurn(claim_id=claim.id, turn_number=logical_turn, speaker="user", text=user_text))
            db.add(ConversationTurn(claim_id=claim.id, turn_number=logical_turn, speaker="agent", text=agent_reply))
            db.commit()
        except Exception:
            db.rollback()
        state = dict(getattr(claim, "pipeline_state", None) or {})
        return {**state, "next_question": agent_reply, "message": agent_reply, "conversation_status": "submitted"}

    prior_turns = db.query(ConversationTurn).filter(ConversationTurn.claim_id == claim.id).count()
    logical_turn = (prior_turns // 2) + 1
    prior_state = dict(getattr(claim, "pipeline_state", None) or {})
    workflow_event = None

    # A verified claim is already past policy verification even if an older
    # pipeline_state snapshot did not persist the verification payload. Rehydrate
    # the workflow gate from the durable claim status so the next claimant turn
    # can enter RAG instead of getting stuck on "I need the claim requirements".
    if claim.status == "verified" and not user_text:
        # A verified claim can receive a user turn after policy verification.
        # Only the internal re-entry (which has no claimant text) should be treated
        # as a workflow event. Previously every post-verification claimant message
        # was discarded here, causing repeated RAG questions with no user turns
        # persisted in the dossier.
        prior_state["policy_valid"] = True
        policy_state = prior_state.get("policy_verification") or {}
        if not isinstance(policy_state, dict) or not policy_state.get("valid"):
            prior_state["policy_verification"] = {
                "valid": True,
                "reason": "Claim is already in the verified workflow state.",
            }
        prior_state["confirmed"] = True
        prior_state["awaiting_confirmation"] = False
        workflow_event = "policy_verified"

    if user_text.startswith("[System Event] Uploaded evidence"):
        workflow_event = "evidence_verified"

    graph_input = {
        **prior_state,
        "claim_text": "" if workflow_event else user_text,
        "ticket_id": claim.ticket_id,
        "input_mode": input_mode,
        **({"_workflow_event": workflow_event} if workflow_event else {}),
    }

    # LangChain's sync invoke performs network/model work. Never run it on FastAPI's event loop.
    result = await asyncio.to_thread(build_conversation_graph().invoke, graph_input)
    extracted = result.get("extracted_data", {}) or {}

    # Stage 2: Policy Verification Trigger upon Baseline Confirmation
    # Persist the just-confirmed graph state before policy verification. The policy
    # checker intentionally reads the durable claim row, so verifying against the
    # previous pre-confirmation snapshot would incorrectly return
    # "claimant_confirmation_required".
    if result.get("confirmed") and claim.status not in {"verified", "submitted", "assigned"}:
        claim.pipeline_state = dict(result)
        flag_modified(claim, "pipeline_state")
        verification = verify_policy_for_claim(
            policy_id=extracted.get("policy_id"),
            event_date_str=extracted.get("event_date"),
            claimant_user_id=str(claim.claimant_id),
            insurance_type=extracted.get("insurance_type"),
            db=db,
            claim_id=claim.id,
        )
        result["policy_verification"] = verification
        if verification.get("valid"):
            result["policy_valid"] = True
            try:
                transition_claim(db, claim, "verified", str(claim.claimant_id), "policy verification successful")
            except Exception:
                claim.status = "verified"

            # Continue the same workflow after policy verification without asking the
            # claimant to send another message. The second graph pass is an internal
            # workflow event: it runs RAG + claim-specific planning, but does not
            # re-extract the claimant's last utterance.
            result["_workflow_event"] = "policy_verified"
            result = await asyncio.to_thread(build_conversation_graph().invoke, result)
            result["policy_verification"] = verification
            result["policy_valid"] = True
            result["conversation_status"] = (
                "collecting_dynamic"
                if result.get("dynamic_missing") or result.get("missing_evidence")
                else "final_review"
            )
        else:
            result["policy_valid"] = False
            try:
                transition_claim(db, claim, "verification_failed", str(claim.claimant_id), verification.get("reason", "policy verification failed"))
            except Exception:
                claim.status = "verification_failed"
            result["conversation_status"] = "verification_failed"

    # Stage 5: Final Submission to Adjuster upon Final Confirmation & Package Compilation
    dynamic_rem = result.get("dynamic_missing") or []
    missing_ev = result.get("missing_evidence") or []
    is_final_turn = (
        claim.status == "verified"
        and not dynamic_rem
        and not missing_ev
        and result.get("confirmed")
        and result.get("final_submission_confirmed")
    )

    if is_final_turn and claim.status != "submitted":
        try:
            from src.agents.submission_synthesizer import synthesize_claims_package
            assigned = assign_claim(db, claim, str(claim.claimant_id))
            transition_claim(db, claim, "assigned", str(claim.claimant_id), "assigned to adjuster")
            result["assigned_adjuster_id"] = assigned.id
            result["assigned_adjuster_name"] = assigned.name
            result["assigned_adjuster"] = {"id": assigned.id, "name": assigned.name, "specialization": assigned.specialization}
            claim.status = "submitted"
            result["conversation_status"] = "submitted"
            result["status"] = "submitted"
            result["conversation_phase"] = "5_completed"
            
            # Synthesize the standardized adjuster dossier
            package = synthesize_claims_package(result, db, claim)
            result["submission_package"] = package

            submission_msg = f"Your claim #{claim.ticket_id} has been submitted and assigned to adjuster {assigned.name}. Your standardized claims package has been compiled for review. You're all set! We will update you as it is processed."
            result["next_question"] = submission_msg
            result["message"] = submission_msg
        except Exception as exc:
            logger.warning("Assignment/package compilation failed during conversational final confirmation: %s", exc)

    # Continuous Gap & Validation Analysis and 5-phase tracking
    try:
        from src.agents.gap_analysis import analyze_claim_gaps
        result["gap_analysis"] = analyze_claim_gaps(result)
        if claim.status in {"submitted", "assigned", "under_review", "closed"} or result.get("conversation_status") == "submitted":
            result["conversation_phase"] = "5_completed"
        elif not result.get("confirmed"):
            result["conversation_phase"] = "2_verification" if result.get("awaiting_confirmation") else "1_baseline"
        elif claim.status != "verified":
            result["conversation_phase"] = "2_verification"
        elif dynamic_rem or missing_ev:
            result["conversation_phase"] = "3_rag_intake"
        elif not result.get("final_submission_confirmed"):
            result["conversation_phase"] = "4_gap_analysis"
        else:
            result["conversation_phase"] = "5_completed"
    except Exception as exc:
        logger.debug("Gap analysis / phase mapping error: %s", exc)

    # A system workflow event (evidence upload/verification) must immediately
    # re-enter the conversational planner so the claimant gets the next natural
    # step without having to type "continue".
    if result.get("_workflow_event") == "evidence_verified":
        result = await asyncio.to_thread(build_conversation_graph().invoke, result)
        result.pop("_workflow_event", None)

    # Persist the RAG-generated requirement plan as durable claim state. The JSON
    # pipeline_state remains a cache for conversation speed, but requirements are
    # independently auditable and survive graph/state refactors.
    requirements = result.get("dynamic_requirements") or []
    if requirements:
        existing_rows = {
            row.requirement_key: row
            for row in db.query(ClaimRequirement).filter(ClaimRequirement.claim_id == claim.id).all()
        }
        outstanding_dynamic = {str(x.get("key")) for x in (result.get("dynamic_missing") or []) if x.get("key")}
        outstanding_evidence = {str(x.get("key")) for x in (result.get("missing_evidence") or []) if x.get("key")}
        seen_keys = set()
        for req in requirements:
            seen_keys.add(str(req.get("key") or "").strip())
            key = str(req.get("key") or "").strip()
            if not key:
                continue
            row = existing_rows.get(key)
            if row is None:
                row = ClaimRequirement(claim_id=str(claim.id), requirement_key=key,
                    label=str(req.get("label") or key), question_hint=req.get("question_hint"),
                    required=bool(req.get("required", True)), evidence_type=req.get("evidence_type"),
                    condition_json={"condition": req.get("condition")},
                    provenance_json=req.get("provenance") or {})
                db.add(row)
                existing_rows[key] = row
            else:
                row.label = str(req.get("label") or row.label)
                row.question_hint = req.get("question_hint") or row.question_hint
                row.required = bool(req.get("required", row.required))
                row.evidence_type = req.get("evidence_type") or row.evidence_type
                row.condition_json = {"condition": req.get("condition")}
                row.provenance_json = req.get("provenance") or row.provenance_json
            if key in outstanding_evidence:
                row.status = "evidence_required"
            elif key in outstanding_dynamic:
                row.status = "information_required"
            else:
                row.status = "satisfied"
        # If the RAG planner intentionally changed the requirement set (for example
        # after a corrected insurance type), retain history but stop treating removed
        # requirements as active blockers.
        if result.get("rag_status") == "OK":
            for key, row in existing_rows.items():
                if key not in seen_keys:
                    row.status = "superseded"
    claim.pipeline_state = dict(result)
    claim.insurance_type = extracted.get("insurance_type")
    claim.event_description = extracted.get("event_description")
    claim.event_location = extracted.get("event_location")
    claim.estimated_claim_amount = extracted.get("estimated_claim_amount")
    claim.conversation_status = result.get("conversation_status", "collecting")
    if result.get("extraction_confidence") is not None:
        claim.extraction_confidence = float(result["extraction_confidence"])

    event_date_str = extracted.get("event_date")
    if event_date_str:
        try:
            claim.event_date = datetime.strptime(str(event_date_str), "%Y-%m-%d").date()
        except ValueError:
            logger.warning("Invalid normalized event date: %r", event_date_str)
    flag_modified(claim, "pipeline_state")

    agent_text = result.get("next_question") or result.get("message", "")
    # Voice barge-in can invalidate a turn while the LLM is still running. Do not
    # persist an assistant response the claimant has already interrupted.
    if is_turn_current is not None and not is_turn_current():
        db.rollback()
        return result
    try:
        if not workflow_event:
            db.add(ConversationTurn(claim_id=claim.id, turn_number=logical_turn, speaker="user", text=user_text))
        if agent_text:
            db.add(ConversationTurn(claim_id=claim.id, turn_number=logical_turn, speaker="agent", text=agent_text))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist conversation turn for %s", claim.ticket_id)
        raise
    return result
