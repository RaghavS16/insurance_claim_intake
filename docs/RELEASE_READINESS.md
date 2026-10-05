# Production release readiness

## Current release candidate

- Branch: `production-grade-UI-UX`
- Verified application commit before this handoff document: `be873ed7c2c3881f623979379878636eebcc0fb4`
- `main` remains unchanged.
- Automated production gates passed on the release candidate.

## Automated verification

The release candidate passed:

- Backend Production Checks
  - static/unit tests
  - migration upgrade and idempotency
  - ORM metadata validation
  - backend import/smoke validation
  - voice/WebRTC production tests
  - Terraform validation
  - disaster-recovery restore drill
  - backend supply-chain/SBOM checks
  - production release gate
- Frontend checks
  - ESLint
  - Vitest
  - Next.js production build
- Frontend container build
- Production Compose Validation
- Full Stack Runtime Smoke
  - dependency startup
  - backend health
  - frontend SPA serving
  - backend OpenAPI generation

## Production deployment prerequisites

Before a public go-live, configure real deployment values for:

- PostgreSQL/pgvector
- Redis with authentication
- object storage/S3-compatible storage
- LLM provider credentials and approved model allowlist
- ClamAV malware scanning
- HTTPS/TLS
- WebRTC STUN/TURN
- passkey RP ID and HTTPS origin
- SMTP when email verification or invitation email is enabled
- backups and secret rotation
- monitoring, alerting and log retention

Never place backend secrets in the frontend or commit deployment credentials.

## Required human acceptance

The repository does not contain a browser automation suite, so these checks require a real deployed environment and a human/browser test:

1. Claimant sign-in and unified text/voice conversation
2. Claimant policy linking and policy verification
3. Dynamic claim requirements/evidence collection from published knowledge
4. Evidence upload and claimant response to an adjuster request
5. Claim submission and claim tracking
6. Adjuster invitation, password setup and passkey registration
7. Adjuster queue, workbench, Copilot grounding, evidence requests and decision recording
8. Admin policy creation, CSV/XLSX import/export and claim reassignment
9. Knowledge upload, ingestion status, publish and version replacement
10. Cross-tenant negative authorization tests
11. Physical microphone/WebRTC voice path through the deployed TURN configuration

These human checks are the final release sign-off; automated CI success does not replace them.

## Recommended release sequence

1. Provision production infrastructure and secrets.
2. Run database migrations.
3. Start the stack and verify readiness.
4. Run the human acceptance matrix above.
5. Verify backup/restore and monitoring.
6. Tag the accepted commit and deploy that exact commit.
