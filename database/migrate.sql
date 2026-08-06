-- Run this to bring the existing claims table up to date with models.py
-- Safe to run multiple times (uses IF NOT EXISTS / DO NOTHING patterns)

ALTER TABLE claims ADD COLUMN IF NOT EXISTS ticket_id VARCHAR UNIQUE;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS pipeline_state JSONB NOT NULL DEFAULT '{}';
ALTER TABLE claims ADD COLUMN IF NOT EXISTS final_decision VARCHAR;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS closure_status VARCHAR;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS input_mode VARCHAR NOT NULL DEFAULT 'text';
ALTER TABLE claims ADD COLUMN IF NOT EXISTS fraud_flags JSONB NOT NULL DEFAULT '[]';
ALTER TABLE claims ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Backfill ticket_id for any existing rows that are NULL
UPDATE claims SET ticket_id = 'CLAIM-' || UPPER(SUBSTRING(gen_random_uuid()::text, 1, 8))
WHERE ticket_id IS NULL;

-- Make it NOT NULL after backfill
ALTER TABLE claims ALTER COLUMN ticket_id SET NOT NULL;
