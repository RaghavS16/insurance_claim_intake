# Production hardening

This branch establishes the backend production baseline for the voice-driven claim agent.

## Runtime invariants

- Alembic is the only production schema authority.
- Production startup verifies that the database is at Alembic head.
- pgvector is fixed at 768 dimensions.
- Redis is required for production coordination and rate limiting.
- Rate limiting uses an atomic Redis Lua script and fails closed when Redis is unavailable.
- JWTs carry a session version and inactive users/session-version changes invalidate existing sessions.
- WebSocket voice events use the same DB-aware authentication semantics as HTTP and validate Origin.
- Adjusters are restricted to actively assigned claims; admins retain global access.
- Claim turns use optimistic `state_version` concurrency and immutable event IDs.
- Untrusted documents are bounded, malware-scanned, and never treated as instructions by LLM prompts.
- Policy wording ingestion defaults to `pending_review`; only published wording participates in policy retrieval.
- Evidence and knowledge uploads are size-bounded before processing.
- Production API errors do not expose exception strings.
- Production CORS methods/headers are explicit and security headers are applied globally.
- Production deployment runs migrations as a separate job before the API.
- Redis is password protected in the compose reference deployment.
- Production readiness verifies PostgreSQL, Redis, storage configuration and migration state.
- Password reset OTP consumption is serialized and logout revocations are persisted.
- Email verification is supported and can be required in production.

## Deployment prerequisites

The reference compose deployment requires operators to provide real secrets and services:

- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `SECRET_KEY`
- `HF_TOKEN` or the configured LLM provider credentials
- `S3_BUCKET` and AWS credentials/role
- SMTP credentials when `REQUIRE_EMAIL_VERIFICATION=true`
- ClamAV service (provided by the reference compose stack)
- managed Postgres/Redis, backups, monitoring, TLS termination and secret rotation for enterprise deployment

## Data migration note

Migration `0013` intentionally fails if an existing `knowledge_chunks.embedding` column is not `vector(768)`. Existing 1024-dimensional indexes must be re-embedded before production rollout. This prevents silent corruption or runtime shape errors.

## Operational requirements outside application code

Application code cannot create HA database replicas, cloud backups, disaster recovery regions, IAM policies, certificate management, legal retention policies, or a production incident process. Those must be provisioned by the deployment platform/IaC and verified before go-live.