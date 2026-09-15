# Adjuster Frontend Design Reference

This implementation reference is derived from the uploaded Adjuster Frontend package.

## Screens

1. Claim Queue / Triage
   - Left navigation branded InsureClaimAI / Adjuster Portal.
   - Operations Core navigation.
   - High-density claim queue with status, type, amount, age/priority and assignment.
   - Calm white/soft-gray surfaces with restrained cyan active state.

2. Claim File / Voice Transcript
   - Claim identity and status header.
   - Voice transcript as the primary claim narrative.
   - Extracted facts shown as supporting structured data, not as the claimant interaction itself.
   - Clear transition from intake transcript to adjuster review.

3. Evidence / Document Review
   - Evidence list with document type, status and review state.
   - Document preview/review area.
   - Missing evidence and verification state visible without overwhelming the transcript.

4. AI Copilot / Adjudication
   - Claim facts and policy context beside an AI analysis panel.
   - Coverage observations, risk flags, evidence gaps and recommendation.
   - Source/evidence references visible so the copilot is grounded.
   - Final decision remains an explicit adjuster action.

## Visual system

- High-minimalism / quietly intelligent.
- Crisp white canvas and soft smoke-gray tonal surfaces.
- Cyan primary accent for active state, voice indicator and primary action.
- Slate blue-gray for secondary controls.
- DM Sans for headings.
- Plus Jakarta Sans for body text.
- Open Sans for labels and metadata.
- Material Symbols icons.
- Generous whitespace and light borders/shadows.
- Avoid glassmorphism, neon glow and excessive cards.

## Product rule

The claimant frontend must remain voice-first and conversational. The adjuster frontend may expose structured claim facts because it is an operations tool, but it must preserve the same calm visual language.

## Backend contract

The adjuster UI can consume:
- GET /api/v1/adjuster/queue
- GET /api/v1/adjuster/claims/{ticket_id}
- PATCH /api/v1/adjuster/claims/{ticket_id}
- GET /api/v1/adjuster/claims/{ticket_id}/copilot

The claim file response contains conversation, dynamic requirements, evidence state and copilot state so the frontend does not need to reconstruct workflow state locally.
