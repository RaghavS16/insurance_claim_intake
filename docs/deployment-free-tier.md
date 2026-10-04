# Free-tier deployment

This is the supported zero-license-cost deployment path for this project.

## Architecture

```text
Internet
   |
HTTPS / Cloudflare Tunnel or a DNS + Let's Encrypt reverse proxy
   |
Oracle Cloud Always Free VM
   |
   +-- Next.js frontend
   +-- FastAPI backend
   +-- PostgreSQL + pgvector
   +-- Redis
   +-- ClamAV
   +-- Piper HTTP TTS
   +-- transactional outbox worker

External optional free-tier services:
   +-- Hugging Face Inference Providers / other configured free-tier LLM route
```

Oracle Cloud currently documents Always Free compute resources, including up to two AMD E2.1.Micro VMs and an Ampere A1 allowance equivalent to 2 OCPUs and 12 GB RAM. The Always Free resources are subject to regional capacity and tenancy limits.

## 1. Create the VM

Use an Oracle Cloud Always Free Ampere A1 VM where available.

Recommended target:

- Ubuntu 24.04
- 2 OCPUs
- 12 GB RAM
- at least 100 GB block storage
- public IPv4 address
- TCP 80/443 exposed only if using a direct reverse proxy
- SSH restricted to your IP

If A1 capacity is unavailable, wait or use one of the smaller Always Free shapes. Do not select paid shapes.

## 2. Install Docker

Install Docker Engine and Compose v2 on the VM.

Verify:

```bash
docker --version
docker compose version
```

## 3. Clone the release branch

```bash
git clone --branch production-grade-UI-UX https://github.com/RaghavS16/insurance_claim_intake.git
cd insurance_claim_intake
```

Do not deploy from `main`.

## 4. Configure secrets

```bash
cp backend/.env.example backend/.env
```

Generate a strong application secret:

```python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set:

- `SECRET_KEY`
- PostgreSQL credentials
- `REDIS_PASSWORD`
- `ALLOWED_ORIGINS`
- `AI_ALLOWED_MODELS`
- LLM provider credentials
- `VOICE_ICE_SERVERS`
- `PASSKEY_RP_ID`
- `PASSKEY_ORIGIN`

Never commit `backend/.env`.

## 5. Database and object storage

The Compose stack uses PostgreSQL + pgvector locally and can use an S3-compatible endpoint through `S3_ENDPOINT_URL`.

For a managed free-tier variant, Supabase Free provides PostgreSQL and pgvector support and Supabase Storage provides an S3-compatible interface. Configure the generated server-side S3 access key/secret and the project's S3 endpoint.

For Supabase S3:

```text
S3_ENDPOINT_URL=https://<project-ref>.storage.supabase.co/storage/v1/s3
S3_BUCKET=<bucket>
AWS_ACCESS_KEY_ID=<server-side-s3-access-key>
AWS_SECRET_ACCESS_KEY=<server-side-s3-secret>
S3_SERVER_SIDE_ENCRYPTION=
```

The application automatically uses path-style addressing for custom S3 endpoints.

## 6. Redis

The default Compose stack runs Redis locally.

If you instead use the Upstash Redis Free tier, set:

```text
REDIS_URL=<tls redis url>
```

The Free tier currently has explicit storage, bandwidth and command quotas. Keep production traffic within those quotas; do not attach a payment method or upgrade the database if the requirement is strictly zero-cost.

## 7. Voice

The repository now includes an isolated Piper HTTP runtime.

The voice path is:

```text
Browser WebRTC
 -> Pipecat
 -> local Whisper
 -> claim agent
 -> Piper HTTP
 -> browser audio
```

Set:

```text
VOICE_TTS_BASE_URL=http://piper:5001/synthesize
```

You must also configure a real STUN/TURN setup for browser WebRTC. The repository includes an optional self-hosted Coturn profile for a Linux VM. Set `TURN_REALM`, `TURN_USERNAME`, `TURN_PASSWORD`, `TURN_EXTERNAL_IP` and `VOICE_ICE_SERVERS`, then start with `docker compose --profile turn up -d`. The Coturn profile uses host networking and UDP 3478 plus the configured relay port range; open those ports in the VM firewall. The placeholder values in `.env.example` are not deployable.

For very small free-tier VMs, prefer a smaller Whisper model:

```text
VOICE_STT_MODEL=Systran/faster-distil-whisper-small.en
```

## 8. Start the stack

```bash
docker compose pull
docker compose build
docker compose --profile turn up -d
docker compose ps
```

Check:

```bash
docker compose logs --tail=200 backend
docker compose logs --tail=200 piper
docker compose logs --tail=200 outbox-worker
```

The migration service must complete successfully before the backend becomes healthy.

## 9. HTTPS

For a public deployment, do not expose the application over plain HTTP.

Two zero-license-cost options are:

1. Cloudflare Tunnel, if you already have a domain on Cloudflare.
2. A reverse proxy such as Caddy with a domain whose DNS you control.

Cloudflare Tunnel is available on all Cloudflare plans, but publishing an application through the normal Tunnel workflow requires a Cloudflare-managed domain.

Do not expose PostgreSQL, Redis, or Piper publicly.

## 10. Security rules

The public surface should be limited to:

```text
443/tcp  HTTPS
22/tcp   SSH, restricted by source IP
```

Keep these internal:

```text
5432 PostgreSQL
6379 Redis
3310 ClamAV
5001 Piper
8000 FastAPI
3000 Next.js
```

## 11. Backups

A free deployment is not automatically a durable deployment.

Before calling the environment production-ready:

- schedule PostgreSQL logical backups
- copy backups to a second storage location
- test restoration
- retain encryption keys/secrets separately
- verify object-storage retention
- periodically run the repository DR restore test

## 12. Free-tier limitations

This deployment is zero-license-cost, but it is not equivalent to a paid HA/SLA architecture.

Expected limitations include:

- limited CPU/RAM
- limited object/database storage
- limited Redis throughput
- no paid uptime SLA
- no multi-zone HA
- voice inference is CPU intensive
- WebRTC quality depends on TURN availability and network conditions
- free-tier provider quotas can be exhausted

The application must therefore fail closed when a critical dependency is unavailable rather than silently downgrade security controls.

## 13. Final smoke test

Run:

```bash
docker compose ps
curl -fsS http://127.0.0.1:8000/health
```

Then verify manually:

1. claimant text intake
2. claimant evidence upload
3. claimant claim tracking
4. claimant voice intake
5. adjuster queue
6. adjuster claim workbench
7. adjuster evidence request
8. claimant response to evidence request
9. adjuster Copilot
10. admin adjuster creation
11. privileged passkey enrollment/login
12. admin CSV policy import
13. admin Excel policy import
14. knowledge upload
15. knowledge ingestion status
16. knowledge publish
17. cross-tenant negative authorization test
