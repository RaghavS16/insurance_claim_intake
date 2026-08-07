# A Voice-Driven Agentic AI System for Insurance Claim Intake and Adjudication

MSc Capstone Project

## Project Overview
A production-grade system that automates insurance claim intake using:
- **Voice input (primary)** — claimant speaks their claim naturally; text input available as a fallback/accessibility option
- AI agent orchestration (validate → extract → check rules → flag fraud → route)
- RAG (retrieve relevant policies for context-aware decisions)
- Full-stack web UI (React + Next.js frontend)

## Timeline
- **August (Review 1)**: Core 7-step pipeline skeleton (text-only MVP), rule-based checks, no voice/OCR/RAG.
- **September (Review 2)**: Voice-in/voice-out (Whisper/Piper) + Document intelligence (OCR) + RAG (pgvector similarity search for coverage reasoning).
- **October (Review 3)**: Feedback capture loop + Adjuster dashboard + DevOps (Docker, CI/CD, Deployment). Final end-to-end 7-step workflow.
- **Post-October**: Final Viva

## Tech Stack

### Backend
- **FastAPI** (Python 3.10+) — REST API, agentic orchestration
- **PostgreSQL** — structured claim/policy/adjuster data
- **Vector DB** — PostgreSQL with pgvector (RAG - policy retrieval)
- **Ollama** (local dev) + Llama 3.1 LLM for agent reasoning
- **LangGraph** — agentic workflow orchestration
- **LangChain** — RAG pipeline + integrations
- **OCR** — pytesseract & pdfplumber (document intelligence)

### Frontend
- **React.js** + **Next.js** (TypeScript) — full-stack frontend
- **Tailwind CSS** — styling
- **Tanstack Query (React Query)** — server state management

### Voice
- **Whisper (faster-whisper)** — speech-to-text, self-hosted, open-source
- **Piper** — text-to-speech, self-hosted, open-source
- Voice is the primary interaction mode; a text form is available as a fallback

### Database & Storage
- **PostgreSQL** — production relational data (policies, claims, adjusters, audit log) **and** vector storage via the `pgvector` extension (policy embeddings for RAG) — one database, two roles
- **AWS S3** — enterprise-grade cloud object storage for uploaded claim documents (images/PDFs)
- **Redis** (optional) — caching, session management
- **MongoDB** (optional) — unstructured claim documents

### DevOps & Deployment
- **Docker** + **Docker Compose** — containerization, local/production parity
- **GitHub** — version control
- **GitHub Actions** — CI/CD pipeline
- **Vercel** — deploy React frontend
- **Railway/Render** — deploy FastAPI backend + managed PostgreSQL

## Project Goals & Success Metrics

### Functional Goals (7-Step Workflow)
1. **Intake**: Accept voice input → transcribe to text (STT), text fallback available.
2. **Extraction & Documents**: Multi-turn prompting for missing fields, extract structured data, process uploaded documents via OCR and validate type via content.
3. **Confirmation**: Return extracted fields for user review and speak back via TTS.
4. **Policy Validation**: Validate policy status (active/expired) against PostgreSQL.
5. **Risk Assessment**: Rule-based fraud detection enhanced with document-derived data.
6. **Claim Decision**: Use RAG to check coverage rules. Decide outcome (approved, denied, flagged_for_review).
7. **Closure + Feedback**: Route to adjuster if flagged, speak and show final decision, capture feedback (no payment processing — payment is explicitly out of scope).

### Success Metrics
- Data extraction accuracy: >85% on test claims
- Latency: <5 seconds per claim processing
- Fraud detection: >80% precision on fraud-flagged scenarios
- Code quality: linted, tested (pytest for backend, Jest for frontend)
- Documentation: complete README, API docs, deployment guide

### Learning Goals
- Master FastAPI + async Python
- Learn Next.js + TypeScript in a production context
- Implement a RAG pipeline with vector embeddings
- Build agentic workflows with LangGraph
- Deploy a containerized full-stack app
- CI/CD pipeline best practices


## Dev Environment (Windows)

### Prerequisites
- Python 3.10+
- Node.js 18+
- PostgreSQL 14+
- Docker Desktop
- Git + GitHub account

### Quick Start
```bash
# Backend
ollama pull llama3.1:8b
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.api.main:app --reload

# Frontend
cd frontend
npm install
npm run dev

# Database
docker-compose up postgres
```

## GitHub Repository Structure
```
insurance-claim-intake/
├── backend/
│   ├── src/
│   │   ├── agents/          # LangGraph agent definitions
│   │   ├── models/          # Pydantic models
│   │   ├── database/        # SQLAlchemy ORM, migrations
│   │   ├── rag/              # RAG pipeline (vector DB, retrieval)
│   │   ├── voice/            # STT (Whisper) + TTS (Piper) integration
│   │   ├── api/              # FastAPI routes
│   │   └── utils/
│   ├── tests/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/       # VoiceRecorder, ClaimForm (fallback), ClaimResults
│   │   ├── hooks/
│   │   ├── services/
│   │   └── styles/
│   ├── tests/
│   ├── package.json
│   ├── Dockerfile
│   └── .env.example
├── database/
│   ├── schema.sql
│   └── seed.sql
├── docker-compose.yml
├── .github/workflows/ci.yml
├── docs/
├── README.md
└── LICENSE
```
