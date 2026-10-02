# Production deployment contract

Required components:
- API deployment with readiness/liveness probes.
- Dedicated Alembic migration job that completes before API rollout.
- Dedicated outbox worker deployment with at-least-once delivery.
- Private object storage with quarantine and lifecycle rules.
- Managed PostgreSQL Multi-AZ with automated backups/PITR.
- Managed Redis HA with TLS.
- ClamAV service reachable only from the backend network.
- OTLP collector/exporter endpoint.
- Secrets supplied by the platform secret manager, never committed.

The AWS Terraform under `infra/aws` is a starting point and must be parameterized with VPC/subnets/security groups before applying.

## Voice production contract

- Voice signaling is claim-scoped and authenticated.
- Voice sessions are pinned to a worker through the HttpOnly worker-affinity cookie and durable worker_id.
- Redis owns the distributed session reservation/lease; the media connection remains owned by the pinned worker.
- Production voice configuration must include at least one TURN ICE server.
- Voice event streams are bounded by Redis MAXLEN and have an explicit TTL. Raw transcript text is bounded before publication.
- Worker draining must reject new voice reservations and allow existing sessions to terminate or be transferred by the deployment controller.

## AI production contract

- Production/staging must define AI_ALLOWED_MODELS and AI_PROMPT_VERSION.
- Unapproved model identifiers fail closed.
- Local model fallback is opt-in and must itself be present in the approved model set.
- Claimant AI turns are tenant rate-, concurrency-, and estimated-token-budget controlled.
- Model/prompt changes require the committed claimant regression manifest and staging evaluation evidence.

## Release gates

The backend release gate must be green before production rollout. It validates:
- Python compile/import health
- AI regression-manifest structure
- fresh-database Alembic migration
- repeated Alembic upgrade idempotency
- production hardening regression tests
- Terraform format/init/validation

The PostgreSQL restore-drill workflow separately validates dump/restore integrity and records measured dump/restore duration. A cloud-provider restore drill must still be executed in the target production account before the first live release.
