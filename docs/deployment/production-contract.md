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
