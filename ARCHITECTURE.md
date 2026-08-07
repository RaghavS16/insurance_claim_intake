# System Architecture — A Voice-Driven Agentic AI System for Insurance Claim Intake and Adjudication

> **Status key used throughout this document:**
> ✅ **Built (August)** — implemented and tested in the current codebase
> 🔜 **September (planned)** — designed, not yet implemented
> 🔜 **October (planned)** — designed, not yet implemented

---

## High-Level Overview (Current State — August)

```
┌─────────────────────────────────────────────────────────────┐
│                      CLAIMANT INTERFACE                      │
│  (Next.js + TypeScript Frontend, App Router, Tailwind)       │
│  ✅ Text input (ClaimForm) — currently the only input mode   │
│  🔜 Voice input (Sept) — will become the primary mode,       │
│      text remains as fallback/accessibility option           │
│  ✅ Results display (decision, payout, fraud flags, JSON)    │
│  🔜 Spoken (TTS) response of the decision (Sept)              │
└──────────────────────┬──────────────────────────────────────┘
                       │ REST API (JSON) + multipart file upload
                       ↓
┌─────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND                           │
│                  (Python 3.11, Sync/Async)                    │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │  ✅ /api/v1/claims/intake        (POST)                   │ │
│ │  ✅ /api/v1/claims/{id}/documents (POST, GET)              │ │
│ │  ✅ /api/v1/claims/{id}/confirm   (POST)                   │ │
│ │  ✅ /api/v1/claims/{id}           (GET)                    │ │
│ │  ✅ /api/v1/document-requirements/{claim_type} (GET)       │ │
│ │  ✅ /health                                                │ │
│ │  🔜 /api/v1/voice/transcribe (Sept)                        │ │
│ │  🔜 /api/v1/voice/synthesize (Sept)                        │ │
│ └──────────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │          LANGGRAPH AGENTIC ORCHESTRATOR                   │ │
│ │  ✅ Two compiled graphs (see below), 6 active nodes        │ │
│ └──────────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │           VOICE PIPELINE  🔜 September                    │ │
│ │  - faster-whisper (STT), Piper (TTS) — not wired in yet   │ │
│ └──────────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │           LLM & RAG PIPELINE                              │ │
│ │  ✅ Ollama + Llama 3.1 8B — used for extraction only       │ │
│ │  🔜 nomic-embed-text + pgvector similarity search (Sept)  │ │
│ │     — coverage_checker is currently a rule-based stub     │ │
│ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────┬────────────────────────────────────┘
                          │
                          ↓
        ┌───────────────────────────────────────┐
        │           POSTGRESQL 15                │
        │   (single database, two roles)         │
        │                                         │
        │  ✅ Relational tables (built, seeded):  │
        │  - policies, adjusters, claims,        │
        │    documents, payment_requests,        │
        │    audit_log                           │
        │                                         │
        │  ✅ pgvector + pgcrypto extensions       │
        │     enabled (init.sql)                 │
        │  🔜 policy_embeddings table + vector    │
        │     similarity search (Sept)            │
        └───────────────────────────────────────┘
```

**Note:** There is only one database. PostgreSQL, with the `pgvector` extension already enabled, will hold both the relational data (built now) and the vector embeddings used for RAG retrieval (September) — no separate vector database service is planned or needed.

---

## Component Breakdown

### 1. Frontend (Next.js + TypeScript) — ✅ Built

**Responsibility:** Claim intake UI, document upload, result display.

**Implemented components:**
- `ClaimForm.tsx` — single component driving a 4-step flow: Describe Claim → Upload Documents → Review & Confirm → Decision. Includes example-claim quick-fill chips for demo purposes.
- `services/claims.ts` — typed API client (`submitIntake`, `confirmClaim`, `uploadDocument`, `getDocumentRequirements`) wrapping axios calls to the backend.

**Not yet built:**
- 🔜 `VoiceRecorder` component (Sept)
- 🔜 `AdjusterAssignment` / adjuster dashboard (Oct)
- 🔜 `ClaimHistory` (not currently scoped to a specific month — revisit if time allows)

**Tech in use:** Next.js App Router, TypeScript, inline styles (not yet migrated to Tailwind utility classes in `ClaimForm.tsx` despite `globals.css` defining a Tailwind-based design token set — worth normalizing before Sept), axios.

---

### 2. FastAPI Backend — ✅ Built (August scope)

**Responsibility:** API orchestration, request routing, graph invocation, persistence.

**Actual implemented routes** (`backend/src/api/main.py`):

```python
GET  /health
GET  /                                          # redirects to /docs

POST /api/v1/claims/intake
  Input:  { claim_text, input_mode, ticket_id? }
  Output: { ticket_id, extracted_data, missing_fields,
            awaiting_confirmation, message }
  Runs the intake graph only (extraction + mandatory-field check).
  Reusable across turns: pass the same ticket_id back with additional
  claim_text to fill in previously-missing fields.

POST /api/v1/claims/{ticket_id}/documents
  Input:  multipart form (document_type, file)
  Output: { document_id, document_type, filename, status }
  Validates document_type against the claim's claim_type; rejects
  (400) with a re-upload message if the type doesn't match.

GET  /api/v1/claims/{ticket_id}/documents
  Output: list of uploaded documents for the claim.

GET  /api/v1/document-requirements/{claim_type}
  Output: { claim_type, documents_needed, required_documents }

POST /api/v1/claims/{ticket_id}/confirm
  Input:  { confirmed }
  Output: { ticket_id, final_decision, closure_status,
            response_message, spoken_response, extracted_data,
            coverage_eligible, deductible_amount, payout_amount,
            fraud_score, fraud_flags, assigned_adjuster,
            missing_documents, audit_log }
  Runs the evaluation graph (policy → documents → coverage → fraud
  → route → format). Rejects (400) if mandatory fields are still
  missing.

GET  /api/v1/claims/{ticket_id}
  Output: current stored status/decision snapshot for the claim.
```

**Not yet built:**
- 🔜 `/api/v1/voice/transcribe`, `/api/v1/voice/synthesize` (Sept)
- 🔜 Adjuster action endpoints (approve/deny/request-info from dashboard) (Oct)
- 🔜 Feedback capture endpoint (Oct)
- 🔜 Appeal-case creation endpoint (Oct, references `UX_WALKTHROUGH.md` Path 6/10)

**Design note for the review panel:** intake and evaluation are deliberately two separate graphs invoked by two separate endpoints, with the confirmation step living in the API layer (not as a graph node) between them. This lets the frontend show the user their extracted data and let them edit it before the (currently free, but eventually costlier) evaluation graph runs — see `ClaimForm.tsx` step 3.

---

### 3. LangGraph Agentic Orchestrator — ✅ Built (August scope)

**Responsibility:** Multi-step reasoning, state management, decision making.

**Actual graph structure** (`backend/src/agents/graph.py`):

**Graph 1 — Intake** (`build_intake_graph`):
```
START → claim_extractor → mandatory_field_checker → END
```
Runs on every `/intake` call. Stops regardless of outcome; the API layer decides whether to re-prompt the user (fields still missing) or move to document upload / confirmation (fields complete), based on `missing_fields`.

**Graph 2 — Evaluation** (`build_evaluation_graph`, invoked only after `/confirm`):
```
START → policy_validator
          ├─(rejected)──────────────────────────────→ response_formatter
          └─(valid)→ document_requirement_checker
                        ├─(missing docs)─────────────→ response_formatter
                        └─(ready)→ coverage_checker
                                     ├─(not covered)──→ response_formatter
                                     └─(covered)→ fraud_detector
                                                    → route_decision
                                                    → response_formatter
                                                        → END
```

**Node-by-node status:**

| Node | Status | Notes |
|---|---|---|
| `claim_extractor` | ✅ Built | Ollama/Llama 3.1 8B, JSON-schema prompt, merges with prior turn's data |
| `mandatory_field_checker` | ✅ Built | Checks `policy_id`, `incident_date`, `claim_type`, `damage_description`, `claimed_amount` |
| `policy_validator` | ✅ Built | Real DB check — active flag + expiry date against `policies` table |
| `document_requirement_checker` | ✅ Built | Looks up `DOCUMENT_REQUIREMENTS` by claim_type; skips entirely for types needing none (e.g. `business`) |
| `coverage_checker` | ✅ Built, **stubbed logic** | Currently amount-only: `claimed_amount <= coverage_amount`. 🔜 Sept: replace with pgvector similarity search over `policy_embeddings` + LLM reasoning over retrieved clauses |
| `fraud_detector` | ✅ Built, **rule-based only** | Flags: near-policy-limit, future incident date, missing description, no supporting documents. No LLM reasoning yet. 🔜 Sept: incorporate document-derived data (e.g. repair estimate vs. claimed amount mismatch) |
| `route_decision` | ✅ Built | Assigns an active adjuster by specialization (falls back to `complex`); generates `ticket_id` if not already set |
| `response_formatter` | ✅ Built | Produces `response_message` and `spoken_response` (currently identical strings — kept as separate fields so Sept TTS phrasing can diverge without touching decision logic) |

**Real `ClaimState` schema** (`backend/src/agents/state.py`) — reproduced in full since this is what should appear in the review report, not a simplified sketch:

```python
class ClaimState(TypedDict, total=False):
    # Intake
    claim_text: str
    input_mode: str                # "voice" or "text"
    claim_type_hint: str
    extracted_data: Dict[str, Any]
    missing_fields: List[str]
    awaiting_confirmation: bool
    confirmed: bool

    # Documents
    documents: List[Dict[str, Any]]
    required_documents: List[str]
    missing_documents: List[str]
    documents_needed: bool

    # Policy validation
    policy_data: Dict[str, Any]
    validation_status: str         # "valid" | "rejected"

    # Coverage + deductible
    coverage_eligible: bool
    coverage_reasoning: str
    deductible_amount: float
    payout_amount: float

    # Risk assessment
    fraud_score: float
    fraud_flags: List[str]

    # Decision + routing
    assigned_adjuster: Dict[str, Any]
    ticket_id: str
    final_decision: str            # need_more_info | need_documents |
                                    # approved | denied |
                                    # flagged_for_review | manual_review

    # Closure + feedback
    closure_status: str            # closed | pending_review | awaiting_user
    response_message: str
    spoken_response: str           # same content as response_message today;
                                    # kept separate for Sept TTS phrasing
    audit_log: List[str]
```

**Final decision outcomes actually implemented** (`response_formatter`):
`need_more_info` → `need_documents` → `manual_review` (invalid policy) → `denied` (not covered) → `flagged_for_review` (`fraud_score >= 0.7`) → `approved`. All six are covered by `backend/tests/test_claims_pipeline.py`.

---

### 4. Voice Pipeline — 🔜 September (not yet built)

**Planned responsibility:** Convert speech to text (intake) and text to speech (response).

- **STT — faster-whisper:** claimant's audio → transcribed text → fed into `claim_extractor` unchanged (the node already only cares about `claim_text`, so no extractor changes are expected, only a new `/voice/transcribe` route in front of it)
- **TTS — Piper:** `spoken_response` (already a distinct state field, currently unused) → audio, returned to the frontend
- **Fallback:** text input continues to work exactly as it does today; `input_mode` already threads through the whole pipeline (`ClaimState.input_mode`) for this reason

`faster-whisper` is already pinned in `backend/requirements.txt`; Piper is not yet added anywhere and needs its own setup step per `SETUP_CHECKLIST.md`.

---

### 5. RAG Pipeline — 🔜 September (not yet built)

**Current state:** `coverage_checker` is a pure amount-comparison stub (see node table above). No embeddings are generated, no `policy_embeddings` table exists yet, and `nomic-embed-text` is pulled in Ollama per the setup checklist but not called anywhere in code.

**Planned flow (Sept):**
```
Query: "Is my claim covered for water damage?"
  ↓
[Vector Embedding] query text → embedding (Ollama, nomic-embed-text)
  ↓
[pgvector Search] SELECT ... ORDER BY embedding <-> query_vector LIMIT 3
  (over a new policy_embeddings table)
  ↓
[Augment Prompt] "Given these policy clauses: {retrieved_docs}, answer: {query}"
  ↓
[LLM Reasoning] Llama 3.1 reads clauses + reasons about coverage
  ↓
Output: coverage_eligible (bool) + coverage_reasoning (cited clause text)
```
`coverage_eligible` and `coverage_reasoning` are already fields on `ClaimState` and already populated (by the stub) today, so the September change is a node-internals swap, not a state-shape change.

---

### 6. PostgreSQL Database Schema — ✅ Built (relational), 🔜 vector table pending

**Relational tables — actually created** (`database/schema.sql`, mirrored in `backend/src/database/models.py`):

```sql
policies(id, policy_number, customer_id, policy_type, coverage_amount,
         deductible, effective_date, expiry_date, is_active, created_at)

adjusters(id, name, email, specialization, claims_assigned, is_active)

claims(id, ticket_id, policy_id, claim_date, incident_date, claim_type,
       input_mode, description, claimed_amount, extraction_confidence,
       validation_status, fraud_score, fraud_flags, assigned_adjuster_id,
       status, final_decision, closure_status, pipeline_state,
       created_at, updated_at)

documents(id, claim_id, document_type, original_filename, file_path,
          mime_type, file_size_bytes, ocr_text, extracted_metadata,
          classification_confidence, uploaded_at)
  -- ocr_text / extracted_metadata / classification_confidence exist
  -- now so Sept OCR can populate them without a migration; NULL today

payment_requests(id, claim_id, claimed_amount, deductible_amount,
                  payout_amount, status, created_at)
  -- stub only: populated on approval, no payment gateway ever called

audit_log(id, claim_id, action, timestamp, details)
```

Note: `claims.pipeline_state` (JSONB) is the mechanism that lets a claim's full `ClaimState` persist between the stateless `/intake` and `/confirm` calls — each API request compiles and invokes a fresh graph rather than holding an in-memory session.

**Not yet created:**
```sql
-- 🔜 September
CREATE TABLE policy_embeddings (
    id UUID PRIMARY KEY,
    policy_id UUID REFERENCES policies(id),
    clause_text TEXT,
    embedding vector(768),
    created_at TIMESTAMP
);
CREATE INDEX ON policy_embeddings USING ivfflat (embedding vector_cosine_ops);
```

**Extensions:** `vector` and `pgcrypto` are already enabled via `database/init.sql`, so this table can be added later without further extension setup.

---

### 7. Vector Store (PostgreSQL + pgvector) — 🔜 September

**What it will be:** Not a separate database — the `pgvector` extension (already enabled) adds a `vector` column type and similarity operators to the same PostgreSQL instance already storing relational data.

**Planned use cases:** RAG retrieval for coverage reasoning; optionally similarity search across historical claims for fraud signal in a later iteration (not currently scoped to any month).

---

## Data Flow Example: Full Claim Journey (Current — Text, August)

```
STEP 1: Claimant types
"My car was hit by a truck on July 15 in Mumbai. I have policy XYZ123.
Repair cost is 50,000 rupees."

STEP 2: Frontend → Backend
POST /api/v1/claims/intake { claim_text, input_mode: "text" }
→ claim_extractor (Llama 3.1 8B) → mandatory_field_checker
→ missing_fields == [] → awaiting_confirmation: true

STEP 3: Frontend shows extracted fields; user reviews/edits, then
uploads required documents (auto → damage_photo, repair_estimate)
POST /api/v1/claims/{id}/documents (x2)

STEP 4: User clicks Confirm
POST /api/v1/claims/{id}/confirm { confirmed: true }
→ policy_validator: XYZ123 active, coverage 500000, deductible 10000
→ document_requirement_checker: both required docs present
→ coverage_checker (stub): 50000 <= 500000 → eligible
→ fraud_detector: low score, no flags
→ route_decision: assigned to Priya Sharma (auto specialist)
→ response_formatter: final_decision = "approved", closure_status = "closed"

STEP 5: Backend → Frontend
JSON result rendered as the Decision card (payout, deductible, adjuster,
fraud score, collapsible raw JSON)

STEP 6: Database
claims row updated (status=evaluated, final_decision, closure_status,
full pipeline_state); payment_requests row inserted (stub, pending_finance)
```

**Planned voice variant (Sept)** — identical from Step 2 onward, with Step 1 becoming `audio → POST /voice/transcribe → claim_text` and Step 5 gaining a parallel `POST /voice/synthesize` call on `spoken_response`.

---

## Technology Choices & Why

| Component | Choice | Status | Why |
|-----------|--------|--------|-----|
| Backend | FastAPI | ✅ Built | Async-capable, fast, built-in OpenAPI docs (`/docs`) |
| Frontend | Next.js + React + TS | ✅ Built | Full-stack TypeScript, straightforward Vercel deployment path |
| Agent orchestration | LangGraph | ✅ Built | Explicit state machine, conditional edges map directly to business rules (policy → docs → coverage → fraud) |
| LLM | Llama 3.1 8B via Ollama | ✅ Built (extraction only) | Local, no API cost, sufficient for structured extraction |
| Database | PostgreSQL 15 | ✅ Built | Reliable, JSONB for `pipeline_state`/`audit_log`, doubles as vector store |
| Vector store | PostgreSQL + pgvector | 🔜 Sept | One database instead of two; extension already enabled |
| Voice (STT) | faster-whisper | 🔜 Sept | Open-source, self-hosted, no per-call cost |
| Voice (TTS) | Piper | 🔜 Sept | Open-source, fast, self-hosted |
| OCR | pytesseract + pdfplumber | 🔜 Sept | Not yet in `requirements.txt`; needed for document content matching |
| Deployment | Docker + GitHub Actions | 🔜 Oct | `docker-compose.yml` exists early, but no CI workflow yet |
| Object storage | Local disk (`uploads/`) | ✅ Built (interim) | `STORAGE_LOCAL_PATH`; AWS S3 remains optional/unbuilt |

---

## Deployment Architecture — 🔜 October (planned, not yet built)

```
┌──────────────────────────────────────────────────────────────┐
│                     GitHub Repository                         │
└─────────────┬──────────────────────────────────────────────────┘
              │ git push
              ↓
┌──────────────────────────────────────────────────────────────┐
│            GitHub Actions (CI/CD Pipeline)  🔜 Oct            │
│  - Run pytest (backend, already exists locally),              │
│    Jest (frontend, not yet written)                           │
│  - Build Docker images, push to registry                      │
└─────────┬────────────────────────────────────────────────────┘
          │
    ┌─────┴─────┐
    ↓           ↓
┌────────┐   ┌─────────────┐
│ Vercel │   │Railway/Render│
│Frontend│   │ Backend + DB │
│ 🔜 Oct │   │  🔜 Oct      │
└────────┘   └─────────────┘
```

`docker-compose.yml` and `database/init.sql`/`schema.sql`/`seed.sql` already exist and work locally (containerization scaffolding started ahead of schedule), but no GitHub Actions workflow, Vercel project, or Railway/Render deployment exists yet.

---

*This document is the single source of truth for architecture as of the August (Review 1) milestone. It should be updated at the start of September and October, not left as a static target-state description — move each 🔜 item to ✅ as it's actually built, rather than writing a new document.*