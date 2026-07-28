from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.database.session import get_db
from src.agents.graph import build_claim_graph

app = FastAPI(title="Insurance Claim Intake API")

class ClaimRequest(BaseModel):
    claim_text: str
    input_mode: str = "text"

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/api/v1/claims/process")
def process_claim(request: ClaimRequest, db: Session = Depends(get_db)):
    graph = build_claim_graph(db)
    initial_state = {
        "claim_text": request.claim_text,
        "input_mode": request.input_mode,
        "fraud_score": 0.0,
        "fraud_flags": [],
        "audit_log": [],
    }
    result = graph.invoke(initial_state)
    return result