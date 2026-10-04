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
