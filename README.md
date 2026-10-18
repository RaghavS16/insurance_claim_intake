# IntelliClaim: Voice-Driven Agentic AI Insurance Intake & Adjudication System

IntelliClaim is a production-grade, multi-tenant insurance claim intake, AI-guided conversation, document verification, and adjuster adjudication platform. Built with FastAPI, Next.js 16, PostgreSQL with pgvector, Redis, AWS S3/KMS, ClamAV, and Pipecat WebRTC voice media orchestration.

---

## Architecture Overview

```mermaid
graph TD
    Client["Claimant / Adjuster Browser"] -->|HTTPS / WSS| Proxy["Reverse Proxy / AWS ALB / Caddy"]
    Proxy -->|/api/*| Backend["FastAPI Backend (Python 3.11)"]
    Proxy -->|/*| Frontend["Next.js 16 Frontend (Node 22)"]
    
    Backend --> DB[("PostgreSQL 15 + pgvector")]
    Backend --> Cache[("Redis 7 Cache & Rate Limiting")]
    Backend --> S3[("AWS S3 / Encrypted Storage")]
    Backend --> ClamAV["ClamAV Malware Scanner"]
    Backend --> Outbox["Durable Outbox Worker"]
    Backend --> LLM["Hugging Face / LLM Inference"]
    Backend --> Piper["Piper TTS Service"]
    Outbox --> SMTP["SMTP Email Gateway / Mailpit"]
```

- **Backend**: FastAPI with async SQLAlchemy, strict Pydantic schemas, RFC 6266 attachment sanitation, constant-time authentication, Redis account lockout, and pgvector knowledge retrieval.
- **Frontend**: Next.js 16 App Router, TypeScript, in-memory bearer token lifecycle with HttpOnly SameSite=Strict refresh cookies, and real-time polling with ETag 304 caching.
- **Voice Pipeline**: Self-hosted Pipecat WebRTC orchestrator, faster-whisper STT, and Piper neural TTS.
- **Storage & Security**: Strict extension & magic-byte verification, content-disposition sandbox headers, S3 server-side encryption, and ClamAV scanning before document consumption.

---

## Local Development Setup

### Prerequisites
- Python 3.11
- Node.js 22 & npm
- Docker and Docker Compose

### 1. Environment Configuration
Copy the provided `.env.example` templates:
```bash
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

### 2. Running with Docker Compose (Dev Profile)
Launch all services including Mailpit (SMTP debugging on port 8025/1025) and development settings:
```bash
docker compose --profile dev up -d --build
```

Access services:
- Frontend: `http://localhost:3000`
- Backend API & OpenAPI Docs: `http://localhost:8000/docs`
- Mailpit UI: `http://localhost:8025`
- Database: `localhost:5433` (mapped from 5432)

---

## Test & Verification Commands

### Backend Tests
```bash
# In backend virtual environment (Python 3.11):
pip install -r backend/requirements.lock
pytest -q backend/tests
```

### Database Migration & Drift Verification
```bash
cd backend
alembic upgrade head
alembic check   # Must report 'No new upgrade operations detected.'
```

### Frontend Checks
```bash
cd frontend
npm ci
npm run lint
npx tsc --noEmit
npm test
npm run build
npm audit --omit=dev --audit-level=high
```

### Security Scans
```bash
# Python dependencies
pip-audit -r backend/requirements.lock

# Node dependencies
npm audit --prefix frontend --omit=dev --audit-level=high
```

---

## Environment Variable Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `ENVIRONMENT` | Yes | `production` | Deployment mode (`development`, `test`, `staging`, `production`). |
| `DEBUG` | Yes | `false` | Enable verbose error traces (must be `false` in production). |
| `SECRET_KEY` | Yes | - | Secret key (min 32 chars) for JWT token signing. |
| `DATABASE_URL` | Yes | - | PostgreSQL connection string (`postgresql://user:pass@host:5432/db`). |
| `REDIS_URL` | Yes | `redis://localhost:6379/0` | Redis instance URL for tokens, cache, and rate limiting. |
| `REDIS_PASSWORD` | In Prod | - | Password for Redis instance. |
| `S3_BUCKET` | In Prod | - | Dedicated S3 bucket for evidence and policy documents. |
| `S3_KMS_KEY_ID` | Optional | - | AWS KMS Key ARN/ID for SSE-KMS encryption. |
| `EMAIL_BACKEND` | Yes | `smtp` | Email provider (`smtp` or `memory` for testing). |
| `SMTP_HOST` | In Prod | - | Hostname of SMTP mail provider. |
| `SMTP_PORT` | In Prod | `587` | Port for SMTP (587 for STARTTLS, 465 for SSL). |
| `SMTP_USERNAME` | In Prod | - | SMTP authentication username. |
| `SMTP_PASSWORD` | In Prod | - | SMTP authentication password. |
| `SMTP_FROM_EMAIL`| In Prod | - | Valid outbound email address. |
| `FORWARDED_ALLOW_IPS`| Yes | `127.0.0.1` | Trusted proxy CIDRs (never `*`). |
| `ALLOWED_ORIGINS`| Yes | - | Comma-separated list of browser origins permitted for CORS. |
| `PUBLIC_APP_URL` | Yes | - | Public canonical URL (must begin with `https://` in production). |
| `HF_TOKEN` | In Prod | - | Hugging Face inference token for LLM reasoning and extraction. |
| `AI_ALLOWED_MODELS`| Yes | - | Comma-separated list of approved AI models. |
| `VOICE_ICE_SERVERS`| In Prod | - | STUN/TURN server URLs for WebRTC voice media traversal. |

---

## Admin Account Bootstrap

To provision an initial tenant and system administrator safely without hardcoded secrets:

```bash
# Set credentials in environment (or omit ADMIN_PASSWORD for interactive prompt):
export ADMIN_EMAIL="admin@yourcompany.com"
export ADMIN_FULL_NAME="System Administrator"
export ADMIN_PHONE="+15551234567"
export ADMIN_PASSWORD="AStrongSecurePassword123!"

# Execute bootstrap script:
python backend/scripts/create_admin.py
```
This script is idempotent, validates password strength against production rules, ensures the default tenant exists, creates the user, and assigns the `ADMIN` role.

---

## Knowledge Base Bootstrap (Policy & Regulations)

The AI intake engine fails closed unless authoritative policy wording and insurance regulations are uploaded and published:

1. Log in to the Adjuster / Admin portal at `http://localhost:3000/adjuster/knowledge-base`.
2. Click **Upload Document**.
3. Select an authoritative insurance policy wording PDF or state regulation document.
4. Specify:
   - Document Type: `POLICY_WORDING` or `REGULATION`
   - Insurance Line: e.g. `AUTO`, `HOME`, `HEALTH`
   - Jurisdiction: e.g. `US-CA`
5. Click **Process & Ingest**. The background worker will extract text, chunk content, generate 768-dim embeddings via FastEmbed, and index vectors in PostgreSQL.
6. Click **Publish**. Once published, claimant intake conversations will automatically use the ingested policy requirements as the authoritative ground truth for claim questions and required evidence.
