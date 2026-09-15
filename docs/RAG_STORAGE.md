# RAG and document storage

## Where documents go

There are two storage layers:

1. **Amazon S3** stores the original files.
   - Knowledge documents: `s3://<S3_BUCKET>/knowledge/...`
   - Claim evidence: `s3://<S3_BUCKET>/claims/<ticket>/evidence/...`
2. **PostgreSQL + pgvector** stores extracted/chunked text, metadata and 1024-dimensional embeddings.

The browser never needs AWS credentials. The backend owns the S3 credentials/IAM role. AWS supports time-limited presigned access when a browser needs an object directly.

## Where to upload RAG documents

Use **Adjuster Portal → Policy & Regulations**.

Upload:
- policy wording
- regulatory documents
- claim process/guidance documents
- insurer claim requirement documents

The upload pipeline is:

`upload → text extraction → LLM metadata extraction → chunking → embeddings → pgvector → S3 original`

The claimant conversation does not use a hardcoded motor/home/health requirement catalogue.

For each claim:

`claim facts → semantic retrieval → policy/regulatory evidence → LLM requirement generation → dynamic questions/evidence requests`

If no authoritative documents have been uploaded, the claim-specific requirement set is empty rather than being silently invented.

## Embeddings

Default:
`qwen/qwen3-embedding-0.6b`

The current schema uses 1024 dimensions, matching that model. Change `EMBEDDING_MODEL` only together with the pgvector dimension/migration if the replacement model has a different output size.

## Required environment

`S3_BUCKET`, `AWS_REGION`, `CLOUD_LLM_API_KEY`, `EMBEDDING_MODEL`.

In AWS deployment, prefer an IAM role over long-lived access keys.

## S3 CORS

Apply `infra/s3-cors.json` to the bucket and add the production frontend origin before deployment.
