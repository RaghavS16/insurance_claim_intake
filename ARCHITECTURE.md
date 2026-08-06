# System Architecture — A Voice-Driven Agentic AI System for Insurance Claim Intake and Adjudication

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      CLAIMANT INTERFACE                      │
│  (React + Next.js Frontend, TypeScript)                      │
│  - Voice input (CORE — primary interaction method)           │
│    Claimant speaks their claim naturally; STT transcribes it │
│  - Text input (fallback / accessibility option)              │
│  - Results display + spoken (TTS) response of the decision   │
└──────────────────────┬──────────────────────────────────────┘
                       │ REST API (JSON) + audio upload
                       ↓
┌─────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND                           │
│                  (Python, Async)                             │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │            /api/claims/{endpoint}                         │ │
│ │  - POST /transcribe (audio → text, Whisper)               │ │
│ │  - POST /extract-claim (text → structured data)          │ │
│ │  - POST /validate-policy (check DB)                      │ │
│ │  - POST /check-coverage (RAG + rules)                    │ │
│ │  - POST /assess-fraud (agentic decision)                 │ │
│ │  - POST /route-claim (assign to adjuster)                │ │
│ │  - POST /synthesize (text → audio response, Piper)       │ │
│ └──────────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │          LANGGRAPH AGENTIC ORCHESTRATOR                   │ │
│ │  Nodes (7-Step Workflow):                                 │ │
│ │  1. claim_extractor (Intake/Extract) + OCR + multi-turn │ │
│ │  2. confirmation_step (Confirm extracted fields)        │ │
│ │  3. policy_validator (Check DB status)                    │ │
│ │  4. coverage_checker (RAG query + LLM reasoning)         │ │
│ │  5. fraud_detector (Risk check with doc-derived info)   │ │
│ │  6. claim_decision (Decide outcome)                       │ │
│ │  7. closure_router (Feedback trigger & adjuster prep)   │ │
│ └──────────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │           VOICE PIPELINE                                  │ │
│ │  - faster-whisper (STT) — self-hosted, open-source        │ │
│ │  - Piper (TTS) — self-hosted, open-source                 │ │
│ └──────────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │           LLM & RAG PIPELINE                              │ │
│ │  - Ollama + Llama 3.1 (local dev) — agent reasoning       │ │
│ │  - Ollama + nomic-embed-text — generates vector embeddings│ │
│ │  - LangChain for RAG chains (retriever → prompt → LLM)   │ │
│ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────┬────────────────────────────────────┘
                          │
                          ↓
        ┌───────────────────────────────────────┐
        │           POSTGRESQL                   │
        │   (single database, two roles)         │
        │                                         │
        │  Relational tables:                    │
        │  - policies, claims, adjusters,        │
        │    audit_log                           │
        │                                         │
        │  Vector store (via pgvector extension):│
        │  - policy clause embeddings            │
        │  - historical claim embeddings         │
        │  - similarity search (RAG retrieval)   │
        └───────────────────────────────────────┘
```

**Note:** There is only one database here. PostgreSQL, with the `pgvector` extension enabled, handles both the relational data (policies, claims, adjusters) and the vector embeddings used for RAG retrieval — no separate vector database service is deployed.

## Component Breakdown

### 1. Frontend (React + Next.js + TypeScript)
**Responsibility:** Voice-first user interface, form handling, result display

**Key Components:**
- `VoiceRecorder` — captures the claimant's spoken claim (primary input method)
- `ClaimForm` — text fallback, used when voice isn't available/practical
- `ClaimResults` — display extraction results, validation status, fraud flags
- `AdjusterAssignment` — show routed adjuster info
- `ClaimHistory` — display past claims

**Tech:**
- Next.js App Router, TypeScript, Tailwind CSS
- React Query for server state
- `react-media-recorder` (or MediaRecorder API directly) for in-browser voice capture

---

### 2. FastAPI Backend (Python, Async)
**Responsibility:** API orchestration, voice processing, authentication, request routing

**Key Routes:**
```python
POST /api/v1/voice/transcribe
  Input: audio file (wav/webm)
  Output: { "text": "transcribed claim text" }

POST /api/v1/claims/extract
  Input: { "claim_text": "..." }
  Output: { "policy_id": "...", "incident_date": "...", "damages": [...] }

POST /api/v1/claims/validate
  Input: { "policy_id": "..." }
  Output: { "valid": true/false, "policy_details": {...} }

POST /api/v1/claims/assess
  Input: { claim_data: {...} }
  Output: { "fraud_score": 0.7, "flags": [...], "decision": "approve|review|deny" }

POST /api/v1/claims/route
  Input: { claim_data: {...}, decision: {...} }
  Output: { "adjuster_id": "...", "adjuster_email": "...", "ticket_id": "..." }

POST /api/v1/voice/synthesize
  Input: { "text": "Your claim has been approved..." }
  Output: audio file (spoken response)

GET /api/v1/claims/{ticket_id}
  Output: { claim_status, audit_log, adjuster_notes }
```

---

### 3. LangGraph Agentic Orchestrator
**Responsibility:** Multi-step reasoning, state management, decision making

**Agent Flow:**
```
START
  ↓
[0. Voice Transcription] (if voice input used)
  Input: audio → Whisper → raw claim text
  ↓
[1. Claim Extractor Node + Document Checker]
  Logic: mandatory_field_checker (loops if info missing) + OCR (pytesseract/pdfplumber) for docs
  Output: structured ClaimData object + Document intelligence
  ↓
[2. Confirmation Node]
  Logic: Return extracted fields for user review & confirmation
  ↓
[3. Policy Validator Node]
  Database: Query PostgreSQL for policy
  Output: PolicyData object or error
  ↓
[Decision: Valid policy?]
  NO → Route to manual review
  YES ↓
[4. Coverage Checker Node]
  RAG: Embed the claim text → pgvector similarity search → retrieve top-matching policy clauses
  LLM: "Does this claim fall under covered incidents?"
  Output: coverage_eligible (bool), reasoning
  ↓
[5. Fraud Detector Node]
  Rules: Check for patterns using text AND document-derived data
  LLM: "Assess fraud likelihood on 0-1 scale"
  Output: fraud_score, flags
  ↓
[6. Claim Decision Node]
  Logic: Compile coverage and fraud scores.
  Output: final_decision (approved | denied | flagged_for_review | manual_review)
  ↓
[7. Closure & Response Router Node]
  Logic: Sets closure_status (closed | pending_review) and routes to adjuster informational or active queue.
  Output: ClaimResponse JSON + spoken response text (sent to TTS) + Feedback trigger
  ↓
END → Return to API → Piper generates spoken response
```

**State Management:**
```python
class ClaimState:
    claim_text: str
    input_mode: str  # "voice" or "text"
    extracted_data: Optional[ClaimData]
    documents: List[dict]  # Uploaded docs with OCR content
    policy_data: Optional[PolicyData]
    coverage_eligible: Optional[bool]
    fraud_score: float
    fraud_flags: List[str]
    final_decision: str    # approved, denied, flagged_for_review, etc.
    closure_status: str    # closed, pending_review, awaiting_user
    assigned_adjuster: Optional[Adjuster]
    ticket_id: str
    audit_log: List[str]
```

---

### 4. Voice Pipeline
**Responsibility:** Convert speech to text (intake) and text to speech (response)

- **STT — faster-whisper:** claimant's audio → transcribed text, fed into the agent pipeline
- **TTS — Piper:** the agent's final decision/response text → spoken audio, returned to the frontend
- **Fallback:** if a claimant can't or doesn't want to use voice, the same pipeline accepts typed text directly at the extraction step, skipping STT

---

### 5. RAG Pipeline (Retrieval-Augmented Generation)
**Responsibility:** Context-aware LLM decisions using policy documents

**Two things are involved, and both live in this project:**
- **Vector embeddings** — numeric representations of policy text, generated by an embedding model (e.g., `nomic-embed-text` via Ollama)
- **Vector store** — where those embeddings are saved and searched; here, that's PostgreSQL via the `pgvector` extension (not a separate database)

```
Query: "Is my claim covered for water damage?"
  ↓
[Vector Embedding] query text → embedding (Ollama embedding model)
  ↓
[pgvector Search] SELECT ... ORDER BY embedding <-> query_vector LIMIT 3
  (finds the 3 most similar policy clauses stored in PostgreSQL)
  ↓
[Augment Prompt] "Given these policy clauses: {retrieved_docs}, answer: {query}"
  ↓
[LLM Reasoning] Llama 3.1 reads clauses + reasons about coverage
  ↓
Output: "Yes, covered. Policy section 3.2 states: ..."
```

---

### 6. PostgreSQL Database Schema

**Relational tables:**
```sql
CREATE TABLE policies (
    id UUID PRIMARY KEY,
    policy_number VARCHAR UNIQUE,
    customer_id UUID,
    policy_type VARCHAR, -- auto, home, business
    coverage_amount DECIMAL,
    deductible DECIMAL,
    effective_date DATE,
    expiry_date DATE,
    is_active BOOLEAN,
    created_at TIMESTAMP
);

CREATE TABLE claims (
    id UUID PRIMARY KEY,
    policy_id UUID REFERENCES policies(id),
    claim_date DATE,
    incident_date DATE,
    claim_type VARCHAR,
    input_mode VARCHAR, -- voice or text
    description TEXT,
    claimed_amount DECIMAL,
    extraction_confidence FLOAT,
    validation_status VARCHAR, -- approved, rejected, review
    fraud_score FLOAT,
    fraud_flags JSONB,
    assigned_adjuster_id UUID,
    status VARCHAR, -- open, approved, denied, paid
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE adjusters (
    id UUID PRIMARY KEY,
    name VARCHAR,
    email VARCHAR,
    specialization VARCHAR, -- auto, home, complex
    claims_assigned INT,
    is_active BOOLEAN
);

CREATE TABLE audit_log (
    id UUID PRIMARY KEY,
    claim_id UUID REFERENCES claims(id),
    action VARCHAR,
    timestamp TIMESTAMP,
    details JSONB
);
```

**Vector store table (requires `CREATE EXTENSION vector;` first):**
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE policy_embeddings (
    id UUID PRIMARY KEY,
    policy_id UUID REFERENCES policies(id),
    clause_text TEXT,
    embedding vector(768),  -- dimension depends on the embedding model used
    created_at TIMESTAMP
);

-- Similarity search index (approximate nearest neighbor)
CREATE INDEX ON policy_embeddings USING ivfflat (embedding vector_cosine_ops);
```

---

### 7. Vector Store (PostgreSQL + pgvector)
**What it is:** Not a separate database — the `pgvector` extension adds a `vector` column type and similarity-search operators to the same PostgreSQL instance used for relational data.

**Stores:** Policy clause embeddings, optionally historical claim embeddings

**Use Cases:**
- RAG retrieval: "Find policies covering water damage"
- Similarity search: "This claim is similar to claims X, Y, Z"
- Anomaly detection: "This claim is an outlier"

---

## Data Flow Example: Full Claim Journey (Voice)

```
STEP 1: Claimant speaks
"My car was hit by a truck on July 15 in Mumbai. I have policy XYZ123. Repair cost is 50,000 rupees."

STEP 2: Frontend → Backend
POST /api/v1/voice/transcribe (audio file)
→ Whisper transcribes to text

STEP 3: Text → Agent Pipeline (Extraction & Confirmation)
POST /api/v1/claims/extract
→ Extractor checks for missing fields, parses documents with OCR.
→ Confirmation asks user to confirm fields.

STEP 4: Agent Pipeline (Evaluation)
Node 3 (Policy Validator): confirms policy XYZ123 is active, auto insurance, limit 500000
Node 4 (Coverage Checker): embeds claim text, pgvector search retrieves clauses, confirms coverage.
Node 5 (Fraud Detector): checks doc data vs claim text. fraud_score = 0.15.
Node 6 (Claim Decision): coverage eligible + low fraud → final_decision = approved.
Node 7 (Closure Router): sets closure_status = closed, lists adjuster as contact. Builds response JSON + TTS text.

STEP 4: Backend → Frontend
JSON result + POST /api/v1/voice/synthesize → audio response

STEP 5: Frontend
Displays results AND plays spoken confirmation to the claimant

STEP 6: Database
INSERT into claims table + audit_log
```

---

## Technology Choices & Why

| Component | Choice | Why |
|-----------|--------|-----|
| Backend | FastAPI | Async, fast, great for AI/LLM integrations, built-in OpenAPI docs |
| Object Storage | AWS S3 (Optional) | Enterprise-grade cloud file storage for uploaded documents (Free tier) |
| Frontend | Next.js + React | Full-stack TypeScript, Vercel deployment, SSR |
| Voice (STT) | faster-whisper | Open-source, self-hosted, no per-call cost |
| Voice (TTS) | Piper | Open-source, fast, self-hosted |
| OCR (Docs) | pytesseract + pdfplumber | Open-source document text extraction |
| LLM Orchestration | LangGraph | Standard for agentic workflows, explicit state management |
| Vector store | PostgreSQL + pgvector | RAG support, one database instead of two, low ops burden |
| Database | PostgreSQL | Reliable, JSONB for audit logs, doubles as vector store |
| LLM | Llama 3.1 (Ollama) | Open-source, local, no API costs, runs on consumer hardware |
| Deployment | Docker + GitHub Actions | Reproducible environments, CI/CD automation |

---

## Deployment Architecture (October onwards)

```
┌──────────────────────────────────────────────────────────────┐
│                     GitHub Repository                         │
└─────────────┬──────────────────────────────────────────────────┘
              │ git push
              ↓
┌──────────────────────────────────────────────────────────────┐
│            GitHub Actions (CI/CD Pipeline)                    │
│  - Run pytest (backend), Jest (frontend)                     │
│  - Build Docker images, push to registry                     │
└─────────┬────────────────────────────────────────────────────┘
          │
    ┌─────┴─────┐
    ↓           ↓
┌────────┐   ┌─────────────┐
│ Vercel │   │Railway/Render│
│Frontend│   │ Backend + DB │
│        │   │(Postgres +   │
│        │   │ pgvector)    │
└────────┘   └─────────────┘
```
