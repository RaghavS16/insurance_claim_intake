"""Shared, transaction-safe claim conversation turn processing."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from src.agents.graph import build_conversation_graph
from src.database.models import Claim, ConversationTurn
from src.utils.logger import app_logger

logger = app_logger


async def process_claimant_turn(
    db: Session,
    claim: Claim,
    user_text: str,
    input_mode: str,
    turn_number: int | None = None,
) -> Dict[str, Any]:
    """Process one claimant turn without blocking the event loop during LLM work."""
    if claim.status == "submitted" or claim.conversation_status in {"submitted", "confirmed"}:
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
        return {**state, "next_question": agent_reply, "message": agent_reply, "conversation_status": "confirmed"}

    if claim.conversation_status in {"pending_verification", "verified", "verification_failed", "escalated"}:
        return dict(getattr(claim, "pipeline_state", None) or {})

    prior_turns = db.query(ConversationTurn).filter(ConversationTurn.claim_id == claim.id).count()
    logical_turn = (prior_turns // 2) + 1
    prior_state = dict(getattr(claim, "pipeline_state", None) or {})
    graph_input = {**prior_state, "claim_text": user_text, "ticket_id": claim.ticket_id, "input_mode": input_mode}

    # LangChain's sync invoke performs network/model work. Never run it on FastAPI's event loop.
    result = await asyncio.to_thread(build_conversation_graph().invoke, graph_input)
    extracted = result.get("extracted_data", {}) or {}

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
    try:
        db.add(ConversationTurn(claim_id=claim.id, turn_number=logical_turn, speaker="user", text=user_text))
        if agent_text:
            db.add(ConversationTurn(claim_id=claim.id, turn_number=logical_turn, speaker="agent", text=agent_text))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist conversation turn for %s", claim.ticket_id)
        raise
    return result
