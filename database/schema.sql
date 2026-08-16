-- ============================================================
-- Insurance Claim Intake System — PostgreSQL Schema
-- Matches SQLAlchemy models in backend/src/database/models.py
-- Run: psql -U postgres -d insurance_claims -f database/schema.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- for gen_random_uuid()

-- -------------------------
-- Policies
-- -------------------------
CREATE TABLE IF NOT EXISTS policies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_number   VARCHAR UNIQUE NOT NULL,
    customer_id     UUID NOT NULL,
    policy_type     VARCHAR NOT NULL,          -- auto | home | business
    coverage_amount NUMERIC NOT NULL,
    deductible      NUMERIC NOT NULL,
    effective_date  DATE NOT NULL,
    expiry_date     DATE NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -------------------------
-- Adjusters
-- -------------------------
CREATE TABLE IF NOT EXISTS adjusters (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR NOT NULL,
    email           VARCHAR UNIQUE NOT NULL,
    specialization  VARCHAR NOT NULL,   -- auto | home | business | complex
    claims_assigned INTEGER NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

-- -------------------------
-- Claims
-- -------------------------
CREATE TABLE IF NOT EXISTS claims (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id             VARCHAR UNIQUE NOT NULL,
    policy_id             UUID REFERENCES policies(id),
    claim_date            DATE NOT NULL DEFAULT CURRENT_DATE,
    incident_date         DATE,
    claim_type            VARCHAR,          -- auto | home | business
    input_mode            VARCHAR NOT NULL DEFAULT 'text',   -- text | voice
    description           TEXT,
    claimed_amount        NUMERIC,
    extraction_confidence FLOAT,
    validation_status     VARCHAR,          -- valid | rejected
    fraud_score           FLOAT,
    fraud_flags           JSONB NOT NULL DEFAULT '[]',
    assigned_adjuster_id  UUID REFERENCES adjusters(id),
    status                VARCHAR NOT NULL DEFAULT 'draft',  -- draft | evaluated
    conversation_status   VARCHAR NOT NULL DEFAULT 'not_started', -- not_started | in_progress | awaiting_documents | intake_complete
    final_decision        VARCHAR,          -- need_more_info | need_documents | approved | denied | flagged_for_review | manual_review
    closure_status        VARCHAR,          -- awaiting_user | pending_review | closed
    pipeline_state        JSONB NOT NULL DEFAULT '{}',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -------------------------
-- Conversation Turns
-- -------------------------
CREATE TABLE IF NOT EXISTS conversation_turns (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id     UUID NOT NULL REFERENCES claims(id),
    turn_number  INTEGER NOT NULL,
    speaker      VARCHAR NOT NULL,   -- 'user' | 'agent'
    text         TEXT NOT NULL,
    audio_url    VARCHAR,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversation_turns_claim_id
    ON conversation_turns(claim_id, turn_number);

-- -------------------------
-- Documents (Review 2/3)
-- -------------------------
CREATE TABLE IF NOT EXISTS documents (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id                  UUID NOT NULL REFERENCES claims(id),
    document_type             VARCHAR NOT NULL,   -- damage_photo | repair_estimate | fir
    original_filename         VARCHAR,
    file_path                 VARCHAR NOT NULL,
    mime_type                 VARCHAR,
    file_size_bytes           INTEGER,
    ocr_text                  TEXT,
    extracted_metadata        JSONB NOT NULL DEFAULT '{}',
    classification_confidence FLOAT,
    uploaded_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -------------------------
-- Payment Requests (Review 2/3 Stub)
-- -------------------------
CREATE TABLE IF NOT EXISTS payment_requests (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id          UUID NOT NULL REFERENCES claims(id),
    claimed_amount    NUMERIC,
    deductible_amount NUMERIC,
    payout_amount     NUMERIC,
    status            VARCHAR NOT NULL DEFAULT 'pending_finance',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -------------------------
-- Audit Log
-- -------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id  UUID REFERENCES claims(id),
    action    VARCHAR NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    details   JSONB NOT NULL DEFAULT '{}'
);

-- ============================================================
-- Seed Data
-- ============================================================

INSERT INTO policies (policy_number, customer_id, policy_type, coverage_amount, deductible, effective_date, expiry_date, is_active)
VALUES
    ('XYZ123', gen_random_uuid(), 'auto', 500000, 10000, '2024-01-01', '2030-12-31', TRUE),
    ('HOME456', gen_random_uuid(), 'home', 1000000, 10000, '2025-03-01', '2026-02-28', TRUE),
    ('AUTO789', gen_random_uuid(), 'auto', 300000, 5000, '2020-01-01', '2022-12-31', FALSE)
ON CONFLICT (policy_number) DO NOTHING;

INSERT INTO adjusters (name, email, specialization, is_active)
VALUES
    ('Priya Sharma',    'priya@insure.co',   'auto',     TRUE),
    ('Rohan Mehta',     'rohan@insure.co',   'home',     TRUE),
    ('Anjali Gupta',    'anjali@insure.co',  'business', TRUE),
    ('Complex Review',  'complex@insure.co', 'complex',  TRUE)
ON CONFLICT (email) DO NOTHING;