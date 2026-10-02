# Disaster Recovery Validation

## Objectives
- PostgreSQL RPO: validate against the managed backup/WAL configuration.
- PostgreSQL RTO: measure restore time from the latest restorable point.
- Redis: treat as recoverable coordination state; durable claim state remains PostgreSQL-backed.

## Restore drill
1. Provision an isolated disposable PostgreSQL instance from the latest automated backup.
2. Restore the database and run `alembic upgrade head`.
3. Execute the backend integration/security test suite against the restored database.
4. Verify representative claims, evidence metadata, audit events and outbox records.
5. Record restore duration, data-loss window and failed checks.
6. Destroy the disposable environment after evidence is retained.

## Release gate
A production release must not claim DR readiness until the restore drill has completed successfully in the target cloud environment. The repository supplies the schema, validation procedure and IaC; cloud backup execution and measured RPO/RTO remain environment-specific.
