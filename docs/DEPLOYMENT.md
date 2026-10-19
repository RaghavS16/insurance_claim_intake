# IntelliClaim Production Deployment & Security Operations Manual

## 1. Compromised Credentials Notice
> [!CAUTION]
> **COMPROMISED CREDENTIALS NOTICE**:
> All credentials, default passwords, and test administrator accounts previously committed to historical development git revisions or seed files are **COMPROMISED** and must NEVER be used or reused in any environment (development, staging, or production).
>
> All production deployments must provision administrative accounts using `python backend/scripts/create_admin.py` with unique credentials supplied via secure environment variables or interactive prompts.

---

## 2. Human-Only Items Checklist
The following items require human operator action and must never be committed to git or hardcoded:
- [ ] **Rotate Compromised Credentials**: Ensure any database initialized with historical seed scripts has had old admin accounts revoked or passwords reset to unique high-entropy secrets.
- [ ] **Real Secrets Provisioning**:
  - `SECRET_KEY`: Minimum 32-character random string (e.g. `openssl rand -hex 32`).
  - `POSTGRES_PASSWORD`: Strong database password.
  - `REDIS_PASSWORD`: Strong Redis authentication password.
- [ ] **Transactional Email (SMTP)**:
  - Production SMTP service credentials (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`).
  - Active verified sending domain with SPF, DKIM, and DMARC configured.
- [ ] **AI & LLM Services**:
  - `HF_TOKEN`: Valid Hugging Face API token for production model inference.
  - Optional `GROQ_API_KEY` or `GEMINI_API_KEY`.
- [ ] **Cloud Storage & Encryption**:
  - Private S3 Bucket with SSE enabled (`S3_BUCKET`, `AWS_REGION`).
  - KMS Customer Managed Key ARN (`S3_KMS_KEY_ID`) for SSE-KMS encryption.
  - AWS IAM credentials or ECS IAM execution/task roles with scoped least privilege.
- [ ] **WebRTC Voice Infrastructure**:
  - TURN server credentials (`TURN_REALM`, `TURN_USERNAME`, `TURN_PASSWORD`, `VOICE_ICE_SERVERS`).
- [ ] **Domain & TLS Certificates**:
  - Production domain DNS pointing to ALB / Reverse proxy.
  - ACM TLS Certificate ARN for HTTPS termination.
- [ ] **Knowledge Base Ingestion**:
  - Upload authoritative insurance policy wording PDFs and regulatory guideline documents through the Adjuster Knowledge Base and publish them.
- [ ] **Compliance & Security Reviews**:
  - Legal and privacy review regarding claimant PII and document retention.
  - External penetration test and automated vulnerability scan against production endpoint.

---

## 3. Proxy & Forwarded Headers Security
> [!WARNING]
> **Proxy Headers Configuration (`FORWARDED_ALLOW_IPS`)**:
> - Uvicorn must only trust forwarded headers (`X-Forwarded-For`, `X-Forwarded-Proto`) from trusted reverse proxies.
> - `FORWARDED_ALLOW_IPS` must be configured with specific CIDR blocks corresponding to the VPC/ALB subnets or Docker network (e.g. `10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.1`).
> - **`FORWARDED_ALLOW_IPS` MUST NEVER BE SET TO `*`** unless the container is deployed in a strictly isolated private network where ONLY the load balancer can physically reach the container. Allowing arbitrary forwarded IPs enables client IP spoofing and bypasses rate limits and security controls.

---

## 4. Pre-Deploy Checklist
Before cutting over production traffic to a new release:
1. **Target Branch Verification**: Verify deployment is built from `release/production-ready` tag/commit.
2. **Environment Variables Audit**: Verify all production variables in AWS Parameter Store / Secrets Manager match required specifications. Ensure `ENVIRONMENT=production`, `DEBUG=false`, `ALLOW_INSECURE_TEST_AUTH=false`.
3. **Database Connectivity**: Verify PostgreSQL 15 has the `vector` extension enabled and connectivity succeeds.
4. **Redis Cache**: Verify Redis 7 instance is reachable with TLS and authentication.
5. **Storage Verification**: Confirm S3 bucket policy blocks public access and allows `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, and `s3:HeadBucket`.
6. **Malware Scanner**: Verify ClamAV container or daemon is reachable on `CLAMAV_HOST:CLAMAV_PORT`.
7. **Model Baked Verification**: Verify container images contain required FastEmbed, Faster-Whisper, and NLTK model caches and do not attempt network downloads during startup.

---

## 5. Migration Procedure

### AWS ECS (Automated One-Off Task)
Run the migration task definition prior to updating backend and frontend services:
```bash
aws ecs run-task \
  --cluster intelliclaim-production \
  --task-definition intelliclaim-migration:latest \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-12345678,subnet-87654321],securityGroups=[sg-migration-task],assignPublicIp=DISABLED}"
```
Wait for the task to finish and verify exit code is 0 in AWS CloudWatch logs.

### Docker Compose
```bash
# Run the migration service container:
docker compose --env-file /etc/intelliclaim/production.env run --rm migrate
```

### Manual CLI Execution
```bash
cd backend
DATABASE_URL="postgresql://user:password@db-host:5432/insurance_claims" alembic upgrade head
alembic check
```

---

## 6. Backup & Disaster Recovery

### PostgreSQL Backup (with pgvector)
PostgreSQL with pgvector stores high-dimensional vector embeddings in `knowledge_chunks`. Regular logical backups must preserve vector definitions:
```bash
# Export compressed binary backup:
pg_dump -h db-host -U postgres -d insurance_claims -Fc -f /backups/insurance_claims_$(date +%Y%m%d_%H%M%S).dump

# Restoration:
pg_restore -h db-host -U postgres -d insurance_claims -c --if-exists /backups/insurance_claims_YYYYMMDD_HHMMSS.dump
```
Ensure target database has extension `vector` installed prior to restoration: `CREATE EXTENSION IF NOT EXISTS "vector";`.

### S3 Evidence & Knowledge Backup
1. Enable S3 Versioning and S3 Object Lock on the primary production bucket.
2. Enable cross-region replication (CRR) to a secondary backup region with separate KMS encryption keys.
3. Test DR restore drill periodically using `backend/scripts/restore_drill.py`.

---

## 7. Rollback Procedure

If severe anomalies or errors are detected after release:

1. **ECS Service Rollback**:
   Revert the ECS task definition to the previous stable revision:
   ```bash
   aws ecs update-service --cluster intelliclaim-production --service backend --task-definition intelliclaim-backend:PREVIOUS_REVISION
   aws ecs update-service --cluster intelliclaim-production --service frontend --task-definition intelliclaim-frontend:PREVIOUS_REVISION
   ```
2. **Database Schema Rollback**:
   If the new release included schema migrations that must be rolled back:
   ```bash
   cd backend
   alembic downgrade -1
   ```
   > [!IMPORTANT]
   > Do not downgrade beyond destructive schema changes that delete columns containing active claimant data. Prefer hotfix forward migrations.

---

## 8. Health Checks & Monitoring

The backend exposes two standard probes:
- `GET /health`: Liveness probe. Returns `{"status":"ok"}` with 200 OK. Used by load balancers for basic process health.
- `GET /ready`: Readiness probe. In production, verifies connectivity to PostgreSQL, Redis (`PING`), S3 (`head_bucket`), and ClamAV (malware scanner ping). Returns 200 OK when all critical dependencies are ready, or 503 Service Unavailable if any required service is down.

Log format: Structured JSON logs emitted to stdout/stderr. Forward to CloudWatch / Datadog / OpenTelemetry collector.

---

## 9. Authentication & Security Note: MFA / Passkeys Status

> [!NOTE]
> MFA and Passkeys (WebAuthn) tables are retained in database migrations for architectural provenance (`0015_mfa`, `0018_worker_identity_and_webauthn`). However, hardware passkey/MFA verification flows are currently not active on user login endpoints. Authentication uses secure email OTP verification, argon2/bcrypt password hashing with constant-time verification, and HttpOnly SameSite=Strict cookie session management. The setting `PRIVILEGED_PASSKEY_REQUIRED` has been deprecated and removed.

---

## 10. Zero-Dollar Demo Deployment Architecture (Synthetic Data Only)

> [!CAUTION]
> **SYNTHETIC DATA RESTRICTION**:
> The zero-dollar local and cloud deployment architectures described below are strictly designed for proof-of-concept demonstrations, developer testing, and non-sensitive synthetic data. They MUST NEVER be used for production operations or actual claimant PII / PHI.

### 10.1 Zero-Dollar Local Demo Profile (`docker-compose.free-demo.yml`)
For completely free, self-hosted, offline-capable demonstrations:
- **Database & Vectors**: PostgreSQL 16 with pgvector (`pgvector/pgvector:pg16`), bound strictly to `127.0.0.1:5432`.
- **Cache & Locks**: Redis 7 Alpine (`redis:7-alpine`), bound strictly to `127.0.0.1:6379`.
- **Object Storage**: Local MinIO container (`minio/minio`), providing an S3-compatible API bound to `127.0.0.1:9000`. Storage is persisted in Docker named volume `demo_minio_data`.
- **AI Models**: Local small language models via Ollama (`llama3.2:3b` or `mistral:7b`) with FastEmbed (`BAAI/bge-base-en-v1.5`) embeddings running on local CPU.
- **Voice**: Disabled (`ENABLE_VOICE=false`) since TURN infrastructure is not provisioned.
- **Reverse Proxy**: Optional Caddy proxy terminating TLS for demo subdomains (`profiles: ["proxy"]`).

To run:
```bash
docker compose -f docker-compose.free-demo.yml --env-file deploy/free-demo.env.example up -d
```

### 10.2 Zero-Dollar Cloud Demo Architecture
For public-facing online demonstrations using cloud free tiers with synthetic claims:
1. **Frontend**: **Vercel Hobby Tier**
   - Hosts Next.js 16 app with automatic CI deployments.
   - Configure environment variables:
     - `INTERNAL_API_URL`: URL of the FastAPI backend on Render.
     - `NEXT_PUBLIC_API_URL`: Public backend endpoint or left empty for same-origin rewrite proxying.
2. **Backend**: **Render Free Web Service**
   - Deploys FastAPI container from `backend/Dockerfile`.
   - Supports dynamic `$PORT` via the updated CMD.
   - Configure `ALLOWED_ORIGINS` to include your Vercel deployment domain.
3. **Database**: **Neon Serverless PostgreSQL**
   - Free tier includes PostgreSQL 16 with `pgvector` extension enabled.
   - Provide standard `DATABASE_URL` with SSL mode `sslmode=require`.
4. **Cache**: **Upstash Serverless Redis**
   - Free tier with TLS endpoint and token authentication for distributed rate limiting.
5. **Storage**: **AWS S3 (Free Usage Tier)**
   - 5 GB standard S3 storage with private bucket policies and IAM programmatic credentials.
6. **Email**: **Gmail SMTP (Free via App Password)**
   - Free transactional email delivery for test OTPs using standard TLS on port 587.

