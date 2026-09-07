"""Shared claim conversation turn processing independent of voice transport."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict

from sqlalchemy.orm import Session

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
    """Run the insurance conversation graph and persist the resulting turn."""
    prior_state = dict(getattr(claim, "pipeline_state", None) or {})

    try:
        turn = ConversationTurn(
            claim_id=claim.id,
            turn_number=turn_number,
            speaker="user",
            text=user_text,
        )
        db.add(turn)
        db.commit()
    except Exception as exc:
        logger.warning("Failed to persist conversation turn: %s", exc)
        db.rollback()

    graph_input = {
        **prior_state,
        "claim_text": user_text,
        "ticket_id": claim.ticket_id,
        "input_mode": input_mode,
    }

    graph = build_conversation_graph()
    result = await asyncio.to_thread(graph.invoke, graph_input)

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
            claim.event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
        except ValueError:
            logger.debug("Invalid normalized event date from graph: %r", event_date_str)

    try:
        db.commit()
    except Exception as exc:
        logger.warning("Failed to commit claim state update: %s", exc)
        db.rollback()

    agent_text = result.get("next_question") or result.get("message", "")
    if agent_text:
        try:
            agent_turn = ConversationTurn(
                claim_id=claim.id,
                turn_number=turn_number,
                speaker="agent",
                text=agent_text,
            )
            db.add(agent_turn)
            db.commit()
        except Exception as exc:
            logger.warning("Failed to persist agent conversation turn: %s", exc)
            db.rollback()

    return result
