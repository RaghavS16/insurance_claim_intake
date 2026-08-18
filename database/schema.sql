-- ============================================================
-- Insurance Claim Intake System — Canonical PostgreSQL Schema
-- Matches SQLAlchemy models in backend/src/database/models.py
-- Strictly supports 6 insurance types:
--   health, senior_health, home, travel, motor, cyber
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- for gen_random_uuid()

-- -------------------------
-- Users
-- -------------------------
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name       VARCHAR NOT NULL,
    email           VARCHAR UNIQUE NOT NULL,
    phone           VARCHAR,
    password_hash   VARCHAR NOT NULL,
    role            VARCHAR NOT NULL CHECK (role IN ('CLAIMANT', 'ADJUSTER')),
    status          VARCHAR NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -------------------------
-- Policies
-- -------------------------
CREATE TABLE IF NOT EXISTS policies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_number   VARCHAR UNIQUE NOT NULL,
    customer_id     UUID NOT NULL,
    policy_type     VARCHAR NOT NULL,          -- health | senior_health | home | travel | motor | cyber
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
    specialization  VARCHAR NOT NULL,   -- health | senior_health | home | travel | motor | cyber
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
    claimant_id           UUID REFERENCES users(id),
    customer_id           VARCHAR,
    claim_date            DATE NOT NULL DEFAULT CURRENT_DATE,
    incident_date         DATE,
    claim_type            VARCHAR,          -- health | senior_health | home | travel | motor | cyber
    input_mode            VARCHAR NOT NULL DEFAULT 'text',   -- text | voice
    description           TEXT,
    claimed_amount        NUMERIC,
    extraction_confidence FLOAT,
    validation_status     VARCHAR,          -- valid | rejected
    status                VARCHAR NOT NULL DEFAULT 'draft',  -- draft | verified
    conversation_status   VARCHAR NOT NULL DEFAULT 'not_started', -- not_started | collecting | confirming | intake_complete
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
