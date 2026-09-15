# Phase 2/3 Architecture – Conversational Dynamic Intake, RAG, Adjuster Review

## Product principle

The claimant experience is conversational, not a fixed questionnaire. The six baseline fields are mandatory data requirements, not six mandatory questions.

The agent:
- understands each natural-language turn;
- extracts any facts supplied in that turn;
- resolves references and corrections using conversation context;
- keeps authoritative claim state;
- decides what would be the most helpful next conversational response;
- uses claim-specific knowledge only when domain-specific requirements are needed.

## Phase 1 reorganization

```text
USER (voice/text)
  -> Pipecat/STT or text endpoint
  -> turn guard / deduplication
  -> conversational semantic extraction
  -> authoritative claim-state merge
  -> baseline completeness check
  -> conversational response planner
  -> claimant
```

The six mandatory baseline fields remain:
`policy_id`, `insurance_type`, `event_date`, `event_description`, `event_location`, `estimated_claim_amount`.

Completeness is deterministic, but question ordering and wording are not. The LLM should never be forced into one-field-per-turn behavior.

## Phase 2

After baseline facts are sufficiently established and the policy is deterministically verified:

```text
claim type
  -> requirements resolver
  -> claim-specific requirement set
  -> conversational requirement planner
  -> dynamic intake
  -> evidence request / upload
  -> adjuster assignment
  -> adjuster queue
```

Phase 2 requirements are stored as structured requirement records rather than hard-coded questions. They can be sourced from the knowledge base, with an LLM translating retrieved requirements into natural dialogue.

## Phase 3 knowledge system

```text
Admin/Adjuster knowledge management
  -> document ingestion
  -> parsing + chunking
  -> metadata: insurance_type, document_type, version, effective_from, effective_to
  -> embeddings/index
  -> retrieval API
```

Retrieval is contextual:
- claim-specific requirements retrieval by insurance type and loss type;
- policy wording retrieval by policy number and incident date;
- regulatory retrieval by insurance type / topic and effective date.

The LLM reasons over retrieved evidence; it does not become the source of authority for policy validity or regulatory applicability.

## Adjuster workflow

```text
submitted claim
  -> specialization assignment
  -> queue
  -> claim detail / transcript
  -> evidence review
  -> AI copilot
  -> adjuster decision
  -> audit trail
```

The AI copilot may provide coverage observations, missing evidence, risk flags, and a grounded decision summary with source references. Final adjudication remains an adjuster action.

## Design source

The uploaded Adjuster Frontend reference package defines the visual direction for:
- claim queue / triage;
- claim file / voice transcript;
- evidence document review;
- AI copilot adjudication.

The implementation should preserve its high-minimalism visual language, DM Sans headlines, Plus Jakarta Sans body text, Open Sans labels, cyan primary accent, slate neutrals, generous whitespace, tonal layering, and Material Symbols iconography.
