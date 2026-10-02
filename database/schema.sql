-- ============================================================
-- Insurance Claim Intake System — Canonical PostgreSQL Schema
-- Matches SQLAlchemy models in backend/src/database/models.py
-- Strictly supports 6 insurance types:
--   health, senior_health, home, travel, motor, cyber
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";  -- for gen_random_uuid()

-- -------------------------
-- Users
-- -------------------------
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name       VARCHAR NOT NULL,
    email           VARCHAR UNIQUE NOT NULL,
    phone           VARCHAR,
    password_hash   VARCHAR NOT NULL,
    role            VARCHAR NOT NULL CHECK (role IN ('CLAIMANT', 'ADJUSTER', 'ADMIN')),
    status          VARCHAR NOT NULL DEFAULT 'active',
    email_verified_at TIMESTAMPTZ,
    session_version INTEGER NOT NULL DEFAULT 1,
    last_login_at TIMESTAMPTZ,
    mfa_required BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -------------------------
-- Policies
-- -------------------------
CREATE TABLE IF NOT EXISTS policies (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_number           VARCHAR UNIQUE NOT NULL,
    customer_id             UUID REFERENCES users(id),
    policy_type             VARCHAR NOT NULL,          -- health | senior_health | home | travel | motor | cyber
    coverage_amount         NUMERIC NOT NULL,
    deductible              NUMERIC NOT NULL,
    effective_date          DATE NOT NULL,
    expiry_date             DATE NOT NULL,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    policyholder_name       VARCHAR,
    policyholder_dob        DATE,
    policyholder_phone      VARCHAR,
    policyholder_phone_last4 VARCHAR(4),
    linked_at               TIMESTAMPTZ,
    link_attempts           INTEGER NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -------------------------
-- Policy Link Audit
-- -------------------------
CREATE TABLE IF NOT EXISTS policy_link_audit (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    policy_number   VARCHAR NOT NULL,
    outcome         VARCHAR NOT NULL,
    ip_address      VARCHAR,
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
    event_date            DATE,
    insurance_type        VARCHAR,          -- health | senior_health | home | travel | motor | cyber
    input_mode            VARCHAR NOT NULL DEFAULT 'text',   -- text | voice
    event_description     TEXT,
    estimated_claim_amount NUMERIC,
    extraction_confidence FLOAT,
    validation_status     VARCHAR,          -- valid | rejected
    status                VARCHAR NOT NULL DEFAULT 'draft',  -- draft | verified
    conversation_status   VARCHAR NOT NULL DEFAULT 'not_started', -- not_started | collecting | confirming | intake_complete
    pipeline_state        JSONB NOT NULL DEFAULT '{}',
    state_version         INTEGER NOT NULL DEFAULT 1,
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
    event_id     VARCHAR(64) UNIQUE,
    speaker      VARCHAR NOT NULL,   -- 'user' | 'agent'
    text         TEXT NOT NULL,
    audio_url    VARCHAR,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversation_turns_claim_id
    ON conversation_turns(claim_id, turn_number);

-- -------------------------
-- Password Reset OTPs
-- -------------------------
CREATE TABLE IF NOT EXISTS password_reset_otps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    otp_hash        VARCHAR NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    verified        BOOLEAN NOT NULL DEFAULT FALSE,
    consumed        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_password_reset_otps_user_id
    ON password_reset_otps(user_id, created_at DESC);

-- -------------------------
-- Revoked Tokens
-- -------------------------
CREATE TABLE IF NOT EXISTS revoked_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_jti       VARCHAR UNIQUE NOT NULL,
    user_id         UUID REFERENCES users(id),
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_revoked_tokens_jti
    ON revoked_tokens(token_jti);



-- -------------------------
-- Semantic RAG Knowledge
-- Originals live in S3; chunks and embeddings live in PostgreSQL/pgvector.
-- -------------------------
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name VARCHAR NOT NULL,
    source_uri VARCHAR NOT NULL,
    document_type VARCHAR NOT NULL,
    insurance_type VARCHAR,
    content_sha256 VARCHAR(64) NOT NULL,
    uploaded_by UUID REFERENCES users(id),
    metadata_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_knowledge_documents_type ON knowledge_documents(document_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_documents_insurance ON knowledge_documents(insurance_type);
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document ON knowledge_chunks(document_id);
CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_hnsw ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);


-- Canonical normalized workflow tables. Runtime production uses Alembic;
-- this file remains a portable bootstrap/reference schema.
CREATE TABLE IF NOT EXISTS claim_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    adjuster_id UUID NOT NULL REFERENCES adjusters(id) ON DELETE RESTRICT,
    assigned_by UUID REFERENCES users(id) ON DELETE SET NULL,
    reason TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    unassigned_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_claim_assignments_active ON claim_assignments(claim_id) WHERE is_active;

CREATE TABLE IF NOT EXISTS claim_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    requirement_key VARCHAR(150) NOT NULL,
    label VARCHAR(500) NOT NULL,
    question_hint TEXT,
    status VARCHAR(40) NOT NULL DEFAULT 'unknown',
    required BOOLEAN NOT NULL DEFAULT TRUE,
    evidence_type VARCHAR(100),
    condition_json JSONB NOT NULL DEFAULT '{}',
    provenance_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(claim_id, requirement_key)
);

CREATE TABLE IF NOT EXISTS claim_evidence_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    adjuster_id UUID NOT NULL REFERENCES adjusters(id) ON DELETE RESTRICT,
    request_text TEXT NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'open',
    response_note TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    responded_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS claim_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
    requirement_id UUID REFERENCES claim_requirements(id) ON DELETE SET NULL,
    object_key VARCHAR(1000) UNIQUE NOT NULL,
    original_filename VARCHAR(500) NOT NULL,
    content_type VARCHAR(200) NOT NULL,
    size_bytes INTEGER NOT NULL CHECK(size_bytes > 0),
    sha256 VARCHAR(64),
    status VARCHAR(40) NOT NULL DEFAULT 'uploaded',
    document_type VARCHAR(100),
    verification_status VARCHAR(40) NOT NULL DEFAULT 'REVIEW_REQUIRED',
    verification_confidence DOUBLE PRECISION,
    detected_document_type VARCHAR(150),
    requested_evidence_type VARCHAR(150),
    request_id UUID REFERENCES claim_evidence_requests(id) ON DELETE SET NULL,
    analysis_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS claim_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    adjuster_id UUID NOT NULL REFERENCES adjusters(id) ON DELETE RESTRICT,
    decision VARCHAR(40) NOT NULL,
    rationale TEXT NOT NULL,
    approved_amount NUMERIC,
    ai_recommendation_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS claim_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    author_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    note TEXT NOT NULL,
    visibility VARCHAR(30) NOT NULL DEFAULT 'internal',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS claim_audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    event_type VARCHAR(100) NOT NULL,
    old_value_json JSONB NOT NULL DEFAULT '{}',
    new_value_json JSONB NOT NULL DEFAULT '{}',
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS claim_exceptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    severity VARCHAR(30) NOT NULL DEFAULT 'medium',
    reason TEXT NOT NULL,
    source_type VARCHAR(60) NOT NULL DEFAULT 'SYSTEM_RULE',
    source_id VARCHAR(150),
    blocking BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR(30) NOT NULL DEFAULT 'open',
    resolution_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS claim_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    fact_key VARCHAR(150) NOT NULL,
    value_json JSONB NOT NULL DEFAULT '{}',
    state VARCHAR(40) NOT NULL DEFAULT 'PROPOSED',
    source_type VARCHAR(60) NOT NULL,
    source_id VARCHAR(150),
    confidence DOUBLE PRECISION,
    provenance_json JSONB NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(claim_id, fact_key)
);

CREATE TABLE IF NOT EXISTS claim_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID UNIQUE NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    idempotency_key VARCHAR(200) UNIQUE NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'accepted',
    submitted_by UUID REFERENCES users(id) ON DELETE SET NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    result_json JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS voice_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id VARCHAR(200) UNIQUE NOT NULL,
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    provider VARCHAR(60) NOT NULL,
    model VARCHAR(120) NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'connecting',
    close_reason VARCHAR(200),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    duration_seconds INTEGER
);
