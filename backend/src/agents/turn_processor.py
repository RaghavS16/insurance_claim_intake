"""Shared, transaction-safe claim conversation turn processing."""
from __future__ import annotations

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
    turn_number: int,
) -> Dict[str, Any]:
    """Process one claimant turn and persist user, state and agent response atomically."""
    prior_state = dict(getattr(claim, "pipeline_state", None) or {})
    if claim.conversation_status in {"pending_verification", "verified", "verification_failed", "escalated", "submitted"}:
        return prior_state

    graph_input = {**prior_state, "claim_text": user_text, "ticket_id": claim.ticket_id, "input_mode": input_mode}
    result = build_conversation_graph().invoke(graph_input)
    extracted = result.get("extracted_data", {}) or {}

    claim.pipeline_state = dict(result)
    claim.insurance_type = extracted.get("insurance_type")
    claim.event_description = extracted.get("event_description")
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
        db.add(ConversationTurn(claim_id=claim.id, turn_number=turn_number, speaker="user", text=user_text))
        if agent_text:
            db.add(ConversationTurn(claim_id=claim.id, turn_number=turn_number, speaker="agent", text=agent_text))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist conversation turn for %s", claim.ticket_id)
        raise
    return result
