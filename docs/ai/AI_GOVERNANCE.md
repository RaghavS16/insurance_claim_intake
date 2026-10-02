# AI Governance

This repository treats models and prompts as versioned production dependencies.

## Release controls

- AI_ALLOWED_MODELS is mandatory in staging/production when model governance is enabled.
- The exact provider-qualified model identifier must be present in the allowlist.
- AI_PROMPT_VERSION identifies the prompt contract used by claimant-facing orchestration.
- Local Ollama fallback is disabled in the production compose reference configuration and must only be enabled when the local model is explicitly approved.
- Claimant AI work is guarded by tenant-scoped request, concurrency, and estimated-token budgets.
- Raw tenant IDs, claim IDs, transcripts, filenames, and other PII must not be used as telemetry metric labels.
- Claim submission readiness is deterministic and cannot be produced by an LLM response.

## Evaluation manifest

backend/evaluations/claimant_regression_cases.json is the minimum regression contract for claimant-facing behavior. It covers retrieval-first Q&A, unsupported-policy refusal, mixed question/fact turns, dynamic requirement behavior, explicit submission confirmation, and tenant isolation assumptions.

A release must validate the manifest schema and run the configured model evaluation suite in staging before enabling a new model/prompt combination in production.

## Model change procedure

1. Update the exact model identifier or AI_PROMPT_VERSION.
2. Run the regression manifest against the candidate configuration.
3. Verify structured extraction/requirement outputs remain schema-valid.
4. Verify policy claims remain citation-backed.
5. Verify deterministic readiness still blocks unsupported submission paths.
6. Record the approved model, prompt, and knowledge versions in release evidence.

The application records selected prompt/model governance metadata in the claim turn state and audit trail without storing raw prompts as telemetry.
