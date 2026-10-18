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

