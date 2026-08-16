# Insurance Claim Intake Voice Agent

> **Shadow Project / Capstone — College Review 1: Voice Interface, Claim Intake & Data Collection**  
> Repository: [https://github.com/RaghavS16/insurance_claim_intake](https://github.com/RaghavS16/insurance_claim_intake)

---

## 1. Project Overview & Problem Statement

First Notice of Loss (FNOL) is the most critical and time-sensitive touchpoint in the insurance claims lifecycle. Traditional intake methods rely on static web forms or manual call center queues, leading to high abandonment rates, missing mandatory information, and delays in claim registration.

This project delivers an **AI-powered Conversational Voice Agent** for real-time insurance claim intake. Using voice activity detection (VAD), speech-to-text (STT), deterministic structured extraction with LLM support, and LangGraph-driven state management, the system guides claimants through interactive natural conversations to collect, validate, and persist complete claim records.

---

## 2. Review 1 Scope: Data Collection & Claim Intake

Review 1 strictly focuses on **Data Collection and Conversational Intake**:

1. **Voice Interface & WebSocket Streaming**: Bidirectional audio streaming over WebSocket (`/ws/claims/{ticket_id}/voice`) and REST intake (`/api/v1/claims/intake`).
2. **Voice Activity Detection (VAD)**: Real-time 16kHz mono audio segmentation using `webrtcvad` to detect utterance boundaries and ignore silence.
3. **Speech-to-Text (STT)**: Utterance transcription via `faster-whisper` (CTranslate2 Whisper with automatic CUDA GPU acceleration and CPU fallback).
4. **Text-to-Speech (TTS)**: Low-latency neural synthesis via `piper-tts` with browser Web Speech API fallback.
5. **LangGraph State Management**: Turn-by-turn conversational state machine tracking extraction confidence, conversation turns, and field-locking.
6. **Claim Information Extraction**: Structured JSON extraction powered by local LLM (`llama3.1:8b` via Ollama) with robust deterministic rule-based fallback.
7. **Mandatory Field Validation**: Continuous validation for 5 core fields:
   - `policy_id` (Policy identifier)
   - `incident_date` (Date of loss)
   - `claim_type` (`auto`, `home`, `business`)
   - `damage_description` (Loss/incident narrative)
   - `claimed_amount` (Estimated monetary loss)
8. **Dynamic Next-Question Generation**: Context-aware questioning targeting only uncollected or ambiguous fields.
9. **Conversational Intent Handling**: Native support for **repeat**, **correction**, **don't know**, and **defer** intents.
10. **Data Persistence**: Persistent turn history (`conversation_turns`) and claim state snapshots (`claims.pipeline_state`).
11. **Production Error Handling & Resilience**: Structured HTTP/WebSocket error responses, no leaked stack traces, and database connection safety.
12. **Automated Verification**: Comprehensive test suite covering extraction, multi-turn dialogue, error paths, and voice components.

---

## 3. Architecture & Review 1 Execution Flow

```
                                Claimant Voice (16kHz PCM)
                                           │
                                           ▼
                                 Voice Interface / WebSocket
                                           │
                                           ▼
                             Voice Activity Detection (VAD)
                                           │
                                           ▼
                              Speech-to-Text (STT: Whisper)
                                           │
                                           ▼
                                LangGraph Conversation Turn
                                           │
                                ┌──────────┴──────────┐
                                ▼                     ▼
                       Intent Classifier      LLM / Heuristic
                        (Repeat/Defer)       Claim Extractor
                                │                     │
                                └──────────┬──────────┘
                                           ▼
                                Mandatory Field Checker
                                           │
                          ┌────────────────┴────────────────┐
                          ▼                                 ▼
                 Missing Fields? (YES)             Missing Fields? (NO)
                          │                                 │
                          ▼                                 ▼
                Next Question Generator           Intake Completion Marker
                          │                                 │
                          └────────────────┬────────────────┘
                                           ▼
                              Text-to-Speech (TTS: Piper)
                                           │
                                           ▼
                                    Claimant Audio
```

### Review 1 LangGraph Topology
```
[User Utterance] ──> conversation_turn_processor
                            │
            ┌───────────────┴───────────────┐
   (normal / correction)            (repeat / defer)
            │                               │
            ▼                               │
     claim_extractor                        │
            │                               │
            └───────────────┬───────────────┘
                            ▼
                mandatory_field_checker
                            │
            ┌───────────────┴───────────────┐
      (missing fields)               (complete)
            │                               │
            ▼                               ▼
  next_question_generator         intake_completion_marker
            │                               │
            ▼                               ▼
          [END]                           [END]
```

---

## 4. Technology Stack

| Layer | Component | Technology | Rationale |
| :--- | :--- | :--- | :--- |
| **API & Backend** | Web Framework | FastAPI, Pydantic v2, Uvicorn | Async WebSocket & REST endpoints with high throughput |
| **Database** | ORM & DB | PostgreSQL, SQLAlchemy 2.0, SQLite (Tests) | Reliable relational schema with JSONB state snapshots |
| **Agent / Orchestration** | State Machine | LangGraph, LangChain, Ollama | State-machine graph with immutable checkpoints |
| **STT** | Transcription | Faster-Whisper (small / int8) | Low-latency inference with CUDA GPU & CPU fallback |
| **VAD** | Voice Segmentation | WebRTC VAD (`webrtcvad-wheels`) | CPU-light, deterministic silence/speech boundary detection |
| **TTS** | Voice Synthesis | Piper TTS (`piper-tts` ONNX) | Fast local neural speech synthesis with browser fallback |
| **Frontend** | Interactive Client | Next.js 16 (App Router), React 19, Tailwind CSS | Real-time audio streaming, live transcript, state visualizer |

---

## 5. Clean Code Organization

```
insurance_claim_intake/
├── backend/
│   ├── src/
│   │   ├── api/
│   │   │   ├── main.py              # REST API endpoints (intake, sessions, history)
│   │   │   └── voice_ws.py          # WebSocket audio streaming & VAD/STT/TTS loop
│   │   ├── agents/
│   │   │   ├── state.py             # Typed ClaimState definition
│   │   │   ├── nodes.py             # Review 1: extraction, validation, next question
│   │   │   ├── graph.py             # LangGraph compilation (Intake & Conversation graphs)
│   │   │   └── evaluation.py        # Review 2/3: isolated policy & evaluation nodes
│   │   ├── voice/
│   │   │   ├── vad.py               # WebRTC VAD utterance segmenter
│   │   │   ├── stt.py               # faster-whisper STT singleton & audio handler
│   │   │   ├── tts.py               # piper-tts wrapper & synthesis error handling
│   │   │   └── session.py           # Per-connection audio buffering state
│   │   ├── database/
│   │   │   ├── models.py            # SQLAlchemy models (Claim, ConversationTurn, etc.)
│   │   │   └── session.py           # Engine & session management
│   │   └── utils/
│   │       └── s3.py                # S3 storage integration
│   ├── tests/
│   │   ├── conftest.py              # Test database fixtures & offline LLM mocking
│   │   ├── test_claims_pipeline.py  # REST API & end-to-end integration tests
│   │   ├── test_conversation_graph.py # LangGraph conversation routing unit tests
│   │   └── test_voice_pipeline.py   # VAD, STT, and TTS unit tests
│   ├── Dockerfile
│   ├── requirements.txt             # Cleaned, categorized dependencies
│   └── .env.example                 # Environment configuration template
├── database/
│   ├── schema.sql                   # PostgreSQL schema definition
│   ├── seed.sql                     # Canonical policies & adjusters dataset
│   ├── migrate_voice.sql            # Conversation turns migration
│   ├── run_migration.py             # Schema migration utility
│   └── verify_db.py                 # Schema validation utility
├── frontend/
│   ├── src/app/
│   │   ├── layout.tsx               # Next.js root layout
│   │   ├── page.tsx                 # Real-time Voice & Text Claim Intake UI
│   │   └── globals.css              # Styling
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 6. How to Run Locally

### Prerequisites
- Python 3.11+
- Node.js 18+ (for frontend)
- PostgreSQL (or Docker)
- Ollama with `llama3.1:8b` (optional — deterministic fallback works offline)

---

### Step 1: Clone Repository & Configure Environment
```bash
git clone https://github.com/RaghavS16/insurance_claim_intake.git
cd insurance_claim_intake

# Backend Environment
cp backend/.env.example backend/.env
```

---

### Step 2: Set up Backend Virtual Environment
```bash
python -m venv venv

# Windows:
.\venv\Scripts\activate

# Linux/macOS:
source venv/bin/activate

pip install -r backend/requirements.txt
```

---

### Step 3: Run Database (Docker Compose or Local Postgres)
```bash
# Start PostgreSQL via Docker Compose
docker-compose up -d postgres

# Run schema migrations & verify
python database/run_migration.py
python database/verify_db.py
```

---

### Step 4: Start Backend API & Voice Server
```bash
cd backend
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```
API Documentation will be accessible at: `http://localhost:8000/docs`

---

### Step 5: Start Frontend UI
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000` in your browser to interact with the Voice Agent.

---

### Step 6: Run Automated Test Suite
```bash
python -m pytest backend/tests -v
```
All 50 unit and integration tests will execute in isolated in-memory SQLite instances.

---

## 7. Example Claim Intake Conversation

```text
[Turn 1]
AI Agent:  "Hello! I am your AI Claim Intake Assistant. What is your policy number or what happened?"
Claimant:  "My car was hit by a truck yesterday on the highway."

[State Extracted]
- claim_type: auto
- incident_date: 2026-08-15
- damage_description: "My car was hit by a truck yesterday on the highway."
- Missing: policy_id, claimed_amount

[Turn 2]
AI Agent:  "What is your policy number?"
Claimant:  "Policy XYZ123."

[State Extracted]
- policy_id: XYZ123
- Missing: claimed_amount

[Turn 3]
AI Agent:  "What is the estimated cost or amount you are claiming?"
Claimant:  "Around 45,000 rupees."

[State Extracted]
- claimed_amount: 45000.0
- Missing: NONE (All 5 mandatory fields present)
- confidence: 100%

[Turn 4]
AI Agent:  "Thank you for providing all the required details. Your ticket ID is CLAIM-B47C9E01. Your claim intake is complete and submitted for review."
```

---

## 8. Current Review 1 Limitations & Future Scope

### Review 1 Limitations
- Review 1 focuses on **data collection, validation, and conversation flow**. It intentionally does not issue automated underwriting settlements or payouts.
- Offline mode uses deterministic heuristic extraction when local Ollama inference is offline.

### Future Phases Roadmap
- **Review 2 (Policy Validation & Document Processing)**:
  - Policy status & date window verification against database
  - OCR document classification (`damage_photo`, `repair_estimate`, `fir`)
  - Deductible and coverage limit calculations
- **Review 3 (Agentic Workflow & Decision Automation)**:
  - Multi-factor fraud risk scoring
  - Automated adjuster load-balancing and routing
  - Settlement approval / denial decision engine
