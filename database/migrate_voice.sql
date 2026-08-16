-- Review 1: conversation history table. Additive — does not touch existing
-- claims/documents/policies/adjusters tables.
CREATE TABLE IF NOT EXISTS conversation_turns (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id     UUID NOT NULL REFERENCES claims(id),
    turn_number  INTEGER NOT NULL,
    speaker      VARCHAR NOT NULL,   -- 'user' | 'agent'
    text         TEXT NOT NULL,
    audio_url    VARCHAR,            -- optional S3 path to raw audio segment
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversation_turns_claim_id
    ON conversation_turns(claim_id, turn_number);

-- conversation_status distinct from claim.status ("draft"/"evaluated") because
-- a claim can be mid-intake-conversation for many turns before it's even a
-- candidate for evaluation. Mirrors the closure_status vs final_decision split
-- already established for the evaluation graph.
ALTER TABLE claims ADD COLUMN IF NOT EXISTS conversation_status VARCHAR NOT NULL DEFAULT 'not_started';
-- not_started | in_progress | awaiting_documents | intake_complete
