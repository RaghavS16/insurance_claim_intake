# Production deployment

## Required services

- PostgreSQL with pgvector
- Private AWS S3 bucket for evidence and adjuster-managed knowledge
- LLM provider
- Embedding provider compatible with the configured vector dimension
- Optional reranker
- Pipecat voice runtime and its STT/TTS dependencies

## Database

Production and staging startup never create or alter schema. Run migrations as a deployment step:

    cd backend && alembic upgrade head

The application then runs only against the migrated schema.

## S3

Set these backend environment variables:

    ENVIRONMENT=production
    DEBUG=False
    AWS_REGION=eu-north-1
    S3_BUCKET=<private-bucket-name>
    S3_KNOWLEDGE_PREFIX=knowledge
    S3_EVIDENCE_PREFIX=claims
    S3_SERVER_SIDE_ENCRYPTION=AES256
    S3_PRESIGNED_URL_EXPIRE_SECONDS=300
    REQUIRE_S3_IN_PRODUCTION=True

Use an IAM role/workload identity rather than committing access keys.

Knowledge documents are stored under the knowledge prefix and claim evidence under the claims prefix. Keep the bucket private and block public access.

## Knowledge ownership

Knowledge ingestion and retrieval administration is **Adjuster-owned**. Admin manages platform operations, policies and adjuster accounts; Admin does not receive knowledge-management ownership.

## RAG operating rules

A retrieval outage is represented as a degraded RAG state. The claimant can continue baseline conversation, but claim-specific requirements must not be silently treated as empty and the claim cannot be submitted until authoritative claim-specific retrieval is available.

Requirement records retain source provenance so adjusters can trace generated requirements back to retrieved documents/chunks.

## Claim workflow

Critical operational objects are normalized into database tables for assignments, requirements, evidence, decisions, notes, audit events and copilot analyses. pipeline_state remains compatibility state and must not be treated as the source of truth for new workflow features.

## Security

- Do not deploy example credentials.
- Use a production secret of at least 32 characters.
- Keep DEBUG disabled.
- Keep S3 private.
- Use least-privilege IAM.
- Run database migrations separately from application startup.
- Keep test authentication fallback disabled outside the test environment.

## Health checks

- /health is the liveness probe.
- /ready is the readiness probe and verifies database connectivity and required production storage configuration.
