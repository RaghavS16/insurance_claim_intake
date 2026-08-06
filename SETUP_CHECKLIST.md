# Setup Checklist — A Voice-Driven Agentic AI System for Insurance Claim Intake

## Pre-Project Setup

### 1. System Requirements
- [ ] Windows 10/11
- [ ] Python 3.10+
- [ ] Node.js 18+
- [ ] PostgreSQL 14+
- [ ] Docker Desktop
- [ ] Git
- [ ] Tesseract-OCR (for Document Extraction)

Verify:
```bash
python --version
node --version
npm --version
docker --version
psql --version
```

### 2. GitHub Setup
```bash
git clone https://github.com/YOUR_USERNAME/insurance-claim-intake.git
cd insurance-claim-intake
```

### 3. Ollama Setup (Local LLM + Embedding Model)
- Download: https://ollama.com/download/windows
- Install & run
- Pull the reasoning model: `ollama pull llama3.1:8b`
- Pull an embedding model (needed for RAG): `ollama pull nomic-embed-text`
- Test: `ollama run llama3.1:8b` → type "hello" → confirm response

### 3.5 Tesseract-OCR Setup (Windows)
- Download the Windows installer from UB-Mannheim: https://github.com/UB-Mannheim/tesseract/wiki
- Install and ensure the installation directory (e.g., `C:\Program Files\Tesseract-OCR`) is added to your system PATH.
- Test: `tesseract --version`

---

## Backend Setup (FastAPI + PostgreSQL + pgvector)

### 4. Python Virtual Environment
```bash
cd insurance-claim-intake
python -m venv venv
venv\Scripts\activate
```

### 5. requirements.txt
```
fastapi>=0.104.1
uvicorn>=0.24.0
sqlalchemy>=2.0.23
psycopg2-binary>=2.9.9
pgvector>=0.2.5
pydantic>=2.5.0
pydantic-settings>=2.0.3
langchain>=0.2.0
langgraph>=0.2.0
langchain-ollama>=0.1.0
langchain-postgres>=0.0.9
faster-whisper>=0.10.0
python-dotenv>=1.0.0
pytest>=7.4.3
httpx>=0.25.0
pytesseract>=0.3.10
pdfplumber>=0.10.2
# boto3>=1.33.0  # Uncomment if using AWS S3 (Optional)
```

**Note on versions:** `langchain-ollama` and `langchain-postgres` are pinned with `>=` rather than an exact old version — `langchain-postgres==0.0.1` predates pgvector support and will conflict with `langchain>=0.2.0`. Using a floor version lets pip resolve compatible releases.

```bash
pip install -r backend/requirements.txt
python -c "import fastapi, langchain, sqlalchemy, faster_whisper, pgvector; print('All good!')"
```

### 6. Piper TTS (Windows)
```bash
# Download the Windows build from the Piper releases page,
# and a voice model (.onnx + .onnx.json)
# Test:
echo "Hello, this is a test." | piper --model en_US-ryan-medium.onnx --output_file test.wav
```

### 7. PostgreSQL with pgvector (local, Docker recommended)
```bash
docker run --name postgres-claim -e POSTGRES_PASSWORD=DBpassword -p 5432:5432 -d pgvector/pgvector:pg15
psql -h localhost -U postgres -c "\l"
```

**Enable the pgvector extension** (required before any vector column can be created):
```bash
psql -h localhost -U postgres -d insurance_claims -c "CREATE EXTENSION IF NOT EXISTS vector;"
```
If `insurance_claims` doesn't exist yet:
```bash
psql -h localhost -U postgres -c "CREATE DATABASE insurance_claims;"
```

### 8. backend/.env
```
DATABASE_URL=postgresql://postgres:DBpassword@localhost:5433/insurance_claims
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
SECRET_KEY=change-this-in-production
DEBUG=True
# AWS_ACCESS_KEY_ID=your_key_here          # Optional: For AWS S3
# AWS_SECRET_ACCESS_KEY=your_secret_here   # Optional: For AWS S3
# AWS_S3_BUCKET_NAME=your_bucket_here      # Optional: For AWS S3
```

### 9. Test FastAPI Backend
```bash
cd backend
uvicorn src.api.main:app --reload
# Visit http://127.0.0.1:8000/docs
```

---

## Frontend Setup (React + Next.js + TypeScript)

### 10. Create Project
```bash
cd insurance-claim-intake
npx create-next-app@latest frontend --typescript --tailwind
# TypeScript: Yes | ESLint: Yes | Tailwind: Yes | src/: Yes | App Router: Yes
```

### 11. Additional Dependencies
```bash
cd frontend
npm install @tanstack/react-query axios zod react-hook-form
```

For voice recording in-browser:
```bash
npm install react-media-recorder
```

### 12. frontend/.env.local
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 13. Test Frontend
```bash
npm run dev
# http://localhost:3000
```

---

## Docker Setup (Optional, recommended before September)

### 14. docker-compose.yml
```yaml
version: '3.8'
services:
  postgres:
    image: pgvector/pgvector:pg15
    environment:
      POSTGRES_PASSWORD: DBpassword
      POSTGRES_DB: insurance_claims
    ports: ["5433:5432"]
    volumes: ["postgres_data:/var/lib/postgresql/data"]
    # Enable the extension automatically on first startup:
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./database/init.sql:/docker-entrypoint-initdb.d/init.sql

  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql://postgres:DBpassword@postgres:5432/insurance_claims
      OLLAMA_BASE_URL: http://host.docker.internal:11434
    depends_on: [postgres]

  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000

volumes:
  postgres_data:
```

Create `database/init.sql` with:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```
This runs automatically the first time the Postgres container starts, so the extension is always ready.

```bash
docker-compose up
```

---

## Verification Checklist

### Backend
- [ ] Ollama running (`ollama list` shows `llama3.1:8b` and `nomic-embed-text`)
- [ ] PostgreSQL running (`psql -l`)
- [ ] pgvector extension enabled (`psql -c "\dx"` should list `vector`)
- [ ] FastAPI running (`curl http://localhost:8000/docs`)
- [ ] Whisper transcribes a test audio file
- [ ] Piper generates a test audio file
- [ ] Tesseract-OCR installed and in PATH (`tesseract --version`)

### Frontend
- [ ] Next.js running
- [ ] Voice recorder captures audio in-browser
- [ ] TypeScript compiling with no errors
- [ ] Tailwind CSS applied correctly

### Git
- [ ] GitHub repo created
- [ ] Initial commit made
- [ ] `.gitignore` present (venv, node_modules, .env)

---

## Troubleshooting

**Ollama not found:** ensure it's added to PATH (usually auto-added on Windows install)

**PostgreSQL connection refused:** restart Docker container (`docker restart postgres-claim`)

**`type "vector" does not exist` error:** the pgvector extension isn't enabled yet — run `CREATE EXTENSION IF NOT EXISTS vector;` on the target database

**Port already in use (8000, 3000, 5432):**
```bash
netstat -ano | findstr :8000
taskkill /PID <pid> /F
```

**npm install fails:**
```bash
npm cache clean --force
rm -r node_modules package-lock.json
npm install
```

**pip install fails on langchain-postgres:** make sure you're using `langchain-postgres>=0.0.9` (not `==0.0.1`), which is compatible with pgvector and current LangChain versions

---

## Next Steps After Setup
1. Read ARCHITECTURE.md
2. Build first FastAPI endpoint: `/health`
3. Build first React component: `VoiceRecorder`
4. Connect React → FastAPI
5. Start building the LangGraph agent
