# Insurance Claim Intake — production-grade UI

This branch contains the authenticated insurance product application and its production frontend.

## Frontend

- Next.js 16 + React 19 + TypeScript
- Next.js App Router with role-aware protected workspace
- Vitest + Testing Library
- Standalone Next.js production container
- Public runtime/build variable: `NEXT_PUBLIC_API_URL`

### Local development

```bash
cd frontend
npm install
npm run test
npm run build
npm run dev
```

### Production container

Set `NEXT_PUBLIC_API_URL` to the public API origin and run:

```bash
docker compose build frontend

docker compose up -d
```

The Next.js frontend is served on port 3000. The backend is on port 8000 by default.

## Product roles

### Claimant
Dashboard, policies, policy linking, claim intake, claims, tracking, evidence, voice intake, settings and authentication recovery/MFA.

### Adjuster
Claims queue, claim package/workbench, assignment, exceptions, evidence requests, decisions, notes, copilot, audit and knowledge search/management.

### Admin
Claims, adjuster management, policy inventory/import/lifecycle and system audit.

## Verification

Frontend CI runs lint, Vitest and the Next.js production build/container.

```bash
npm run lint
npm run test
npm run build
```

Backend and supply-chain checks run separately in GitHub Actions. Full end-to-end verification requires a configured environment containing PostgreSQL/pgvector, Redis, ClamAV, model credentials, S3 configuration when enabled, and production voice TURN/ICE configuration.

## Important deployment configuration

Do not put secrets in the frontend. `NEXT_PUBLIC_API_URL` is public configuration and is embedded into the browser bundle. Backend secrets remain server-side environment variables.

For realtime voice, configure the backend voice ICE/TURN settings and serve the frontend over HTTPS in production so browser microphone/WebRTC security requirements are satisfied.


## Free-tier deployment

The repository includes a zero-license-cost deployment path using Docker Compose and self-hosted/open-source runtime components.

See [docs/deployment-free-tier.md](docs/deployment-free-tier.md).

The guide covers Oracle Cloud Always Free, PostgreSQL/pgvector, Redis, ClamAV, Pipecat + local Whisper + Piper, HTTPS, TURN, backups and the production smoke test.

## Knowledge ingestion

Adjuster/admin knowledge uploads are queued through the transactional outbox. Upload returns a `job_id`; use `GET /api/v1/knowledge/ingestion/{job_id}` to check `pending`, `processed` or `dead_letter` status.

## Policy bulk import

Admin policy import accepts both CSV and XLSX files. Imports are tenant-scoped, schema-validated and preserve existing claimant linkage fields during upsert.
