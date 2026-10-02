"""Shared, transaction-safe claim conversation turn processing."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Callable, Dict

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from src.agents.graph import build_conversation_graph
from src.database.models import Claim, ConversationTurn
from src.database.hardening_models import ClaimSubmission
from src.utils.logger import app_logger

logger = app_logger

class ClaimTurnConflict(RuntimeError):
    """Raised when another request committed a newer claim state while this turn was processing."""


async def process_claimant_turn(
    db: Session,
    claim: Claim,
    user_text: str,
    input_mode: str,
    turn_number: int | None = None,
    is_turn_current: Callable[[], bool] | None = None,
    attachment: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Process one claimant turn without blocking the event loop during LLM work."""
    from src.agents.policy_check import verify_policy_for_claim
    from src.database.claim_workflow import assign_claim, transition_claim, persist_canonical_facts, sync_claim_requirements, build_submission_readiness

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

    expected_state_version = int(getattr(claim, "state_version", 1) or 1)
    prior_turns = db.query(ConversationTurn).filter(ConversationTurn.claim_id == claim.id).count()
    logical_turn = (prior_turns // 2) + 1
    prior_state = dict(getattr(claim, "pipeline_state", None) or {})
    workflow_event = None

    # A verified claim is already past policy verification. Rehydrate the
    # verification gate on every resumed turn, not only internal re-entry turns.
    # This protects against older pipeline_state snapshots and guarantees that a
    # normal claimant message after verification continues through RAG intake
    # instead of falling back to baseline/verification messaging.
    if claim.status == "verified":
        prior_state["policy_valid"] = True
        policy_state = prior_state.get("policy_verification") or {}
        if not isinstance(policy_state, dict) or not policy_state.get("valid"):
            prior_state["policy_verification"] = {
                "valid": True,
                "reason": "Claim is already in the verified workflow state.",
            }
        prior_state["awaiting_confirmation"] = False
        if not user_text:
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

    # Fast-path intent first: classify only when the turn plausibly needs conversational
    # RAG. Plain claim facts can go straight to the intake graph, avoiding an LLM call.
    rag_reply = {}
    if user_text and not workflow_event:
        from src.agents.rag_chat import _heuristic_intent
        fast_intent = _heuristic_intent(user_text)
        likely_question = bool(
            fast_intent.is_question
            or fast_intent.wants_to_file
            or fast_intent.wants_status
            or fast_intent.wants_policy_explanation
            or fast_intent.wants_human
        )
        if likely_question:
            try:
                from src.agents.rag_chat import classify_turn, build_claimant_response
                rag_intent_obj = await asyncio.to_thread(
                    classify_turn,
                    user_text,
                    prior_state.get("extracted_data") or {},
                )
                rag_reply = await asyncio.to_thread(
                    build_claimant_response,
                    user_text,
                    prior_state,
                    rag_intent_obj,
                )
            except Exception as exc:
                # Preserve normal claim capture if conversational RAG is unavailable.
                logger.warning("Claimant conversational RAG response failed: %s", exc)

    # LangChain's sync invoke performs network/model work. Never run it on FastAPI's event loop.
    result = await asyncio.to_thread(build_conversation_graph().invoke, graph_input)
    extracted = result.get("extracted_data", {}) or {}
    if rag_reply:
        result["chat_intent"] = rag_reply.get("intent") or {}
        result["chat_retrieval"] = rag_reply.get("retrieval") or {}
        if rag_reply.get("answer"):
            result["next_question"] = rag_reply["answer"]
            result["message"] = rag_reply["answer"]

    # Policy verification is triggered by complete baseline facts, not by a conversational
    # confirmation flag. The claimant can correct facts at any time; verification is rerun
    # after each correction before submission.
    missing_baseline = list(result.get("missing_fields") or [])
    if not missing_baseline and extracted.get("policy_id") and extracted.get("event_date") and extracted.get("insurance_type"):
        try:
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
            result["policy_valid"] = bool(verification.get("valid"))
            if verification.get("valid"):
                if claim.status != "verified":
                    try:
                        transition_claim(db, claim, "verified", str(claim.claimant_id), "deterministic policy verification")
                    except ValueError:
                        claim.status = "verified"
                result["conversation_status"] = (
                    "collecting_dynamic"
                    if result.get("dynamic_missing") or result.get("missing_evidence")
                    else "ready_for_submission"
                )
            else:
                if claim.status != "verification_failed":
                    try:
                        transition_claim(db, claim, "verification_failed", str(claim.claimant_id), verification.get("reason", "policy verification failed"))
                    except ValueError:
                        claim.status = "verification_failed"
                result["conversation_status"] = "verification_failed"
        except Exception as exc:
            logger.exception("Policy verification failed unexpectedly")
            result["policy_verification"] = {
                "valid": False,
                "reason": "verification_service_error",
                "error_type": type(exc).__name__,
            }
            result["policy_valid"] = False

    # Persist canonical facts independently of the conversational JSON cache.
    persist_canonical_facts(
        db, claim, extracted,
        source_type="CLAIMANT",
        source_id=str(logical_turn),
        confidence=result.get("extraction_confidence"),
    )

    # Keep the conversational JSON as a cache only; the normalized requirement sync below
    # receives the same RAG authority marker used by the readiness engine.
    claim.pipeline_state = dict(result)
    flag_modified(claim, "pipeline_state")
    # Durable requirements are synchronized before readiness is evaluated.
    sync_claim_requirements(db, claim, result.get("dynamic_requirements") or [])

    # Submission is an explicit claimant action ("submit"/"file"), never an implicit
    # side effect of the LLM's conversational confirmation state. The backend recomputes
    # readiness and uses a durable unique submission record for exactly-once semantics.
    if result.get("submit_requested") and claim.status not in {"submitted", "assigned"}:
        policy_verification = result.get("policy_verification") or {}
        readiness = build_submission_readiness(db, claim, policy_verification)
        result["submission_readiness"] = readiness
        if readiness.get("ready"):
            try:
                locked = db.execute(
                    __import__("sqlalchemy").select(Claim).where(Claim.id == claim.id).with_for_update()
                ).scalar_one()
                existing_submission = db.query(ClaimSubmission).filter(
                    ClaimSubmission.claim_id == claim.id
                ).first()
                if existing_submission:
                    result["conversation_status"] = "submitted"
                    result["next_question"] = (
                        f"Your claim #{claim.ticket_id} has already been submitted. "
                        "You can follow its progress from Track Claim."
                    )
                    result["message"] = result["next_question"]
                else:
                    assigned = assign_claim(db, locked, str(claim.claimant_id))
                    transition_claim(db, locked, "submitted", str(claim.claimant_id), "explicit claimant submission")
                    idempotency_key = f"claim:{claim.id}:submission:v1"
                    db.add(ClaimSubmission(
                        claim_id=locked.id,
                        idempotency_key=idempotency_key,
                        submitted_by=str(claim.claimant_id),
                        result_json={"ticket_id": locked.ticket_id, "adjuster_id": str(assigned.id)},
                    ))
                    claim.status = "submitted"
                    result["assigned_adjuster_id"] = str(assigned.id)
                    result["assigned_adjuster_name"] = assigned.name
                    result["assigned_adjuster"] = {
                        "id": str(assigned.id), "name": assigned.name,
                        "specialization": assigned.specialization,
                    }
                    result["conversation_status"] = "submitted"
                    result["status"] = "submitted"
                    result["conversation_phase"] = "5_completed"
                    try:
                        from src.agents.submission_synthesizer import synthesize_claims_package
                        result["submission_package"] = synthesize_claims_package(result, db, locked)
                    except Exception as exc:
                        logger.warning("Submission dossier synthesis failed after durable acceptance: %s", exc)
                    result["next_question"] = (
                        f"Your claim #{claim.ticket_id} has been submitted and assigned to "
                        f"{assigned.name}. You can track its progress from Track Claim."
                    )
                    result["message"] = result["next_question"]
            except Exception as exc:
                db.rollback()
                logger.exception("Exactly-once claim submission failed")
                result["submission_error"] = type(exc).__name__
                result["next_question"] = (
                    "I couldn't complete the submission safely just now. Your claim details are saved; "
                    "please try submitting again."
                )
                result["message"] = result["next_question"]
        else:
            result["next_question"] = (
                "Your claim isn't ready to submit yet. "
                + (", ".join(
                    str(item.get("label") or item.get("key"))
                    for item in readiness.get("blocking_requirements", [])
                ) or "I still need a policy verification or review.")
                + "."
            )
            result["message"] = result["next_question"]
        result["submit_requested"] = False

    # Continuous gap/consistency analysis. The phase field below is a legacy UI projection, not workflow authority.
    try:
        from src.agents.gap_analysis import analyze_claim_gaps
        result["gap_analysis"] = analyze_claim_gaps(result)
        if claim.status in {"submitted", "assigned", "under_review", "closed"} or result.get("conversation_status") == "submitted":
            result["conversation_phase"] = "5_completed"
        elif result.get("missing_fields"):
            result["conversation_phase"] = "1_baseline"
        elif claim.status != "verified":
            result["conversation_phase"] = "2_verification"
        elif dynamic_rem or missing_ev or pending_review:
            result["conversation_phase"] = "3_rag_intake"
        elif not result.get("final_submission_confirmed"):
            result["conversation_phase"] = "4_gap_analysis"
        else:
            result["conversation_phase"] = "5_completed"
    except Exception as exc:
        logger.debug("Gap analysis / phase mapping error: %s", exc)

    result.pop("_workflow_event", None)

    # Durable requirements were synchronized before submission/readiness evaluation.
    # The claimant-facing answer is authoritative when the turn was a question.
    # Otherwise preserve the normal intake planner response. For mixed messages the
    # RAG answer takes precedence, while extraction/policy/evidence state continues.
    agent_text = result.get("next_question") or result.get("message", "")
    chat_intent = result.get("chat_intent") or {}
    if rag_reply.get("answer"):
        agent_text = rag_reply["answer"]
        result["next_question"] = agent_text
        result["message"] = agent_text

    # Voice barge-in can invalidate a turn while the LLM is still running. Do not
    # persist an assistant response the claimant has already interrupted.
    if is_turn_current is not None and not is_turn_current():
        db.rollback()
        return result
    try:
        from sqlalchemy import select
        locked_claim = db.execute(select(Claim).where(Claim.id == claim.id).with_for_update()).scalar_one()
        if int(getattr(locked_claim, "state_version", 1) or 1) != expected_state_version:
            db.rollback()
            raise ClaimTurnConflict("Claim changed while the turn was being processed. Please retry.")
        locked_claim.state_version = expected_state_version + 1
        event_id = uuid.uuid4().hex
        if not workflow_event:
            user_turn = ConversationTurn(claim_id=claim.id, turn_number=logical_turn, event_id=f"{event_id}:u", speaker="user", text=user_text)
            if attachment:
                user_turn.attachment = dict(attachment)
            db.add(user_turn)
        elif attachment:
            user_turn = ConversationTurn(
                claim_id=claim.id,
                turn_number=logical_turn,
                event_id=f"{event_id}:u",
                speaker="user",
                text=f"Uploaded evidence: {attachment.get('name') or 'evidence file'}",
            )
            user_turn.attachment = dict(attachment)
            db.add(user_turn)
        if agent_text:
            db.add(ConversationTurn(claim_id=claim.id, turn_number=logical_turn, event_id=f"{event_id}:a", speaker="agent", text=agent_text))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist conversation turn for %s", claim.ticket_id)
        raise
    return result
