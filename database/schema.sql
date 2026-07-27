-- Requires pgvector extension (see init.sql)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ===== Relational tables =====

CREATE TABLE policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_number VARCHAR UNIQUE NOT NULL,
    customer_id UUID NOT NULL,
    policy_type VARCHAR NOT NULL,        -- auto, home, business
    coverage_amount DECIMAL NOT NULL,
    deductible DECIMAL NOT NULL,
    effective_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE adjusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR NOT NULL,
    email VARCHAR UNIQUE NOT NULL,
    specialization VARCHAR NOT NULL,     -- auto, home, complex
    claims_assigned INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id UUID REFERENCES policies(id),
    claim_date DATE DEFAULT CURRENT_DATE,
    incident_date DATE,
    claim_type VARCHAR,
    input_mode VARCHAR DEFAULT 'text',   -- voice or text
    description TEXT,
    claimed_amount DECIMAL,
    extraction_confidence FLOAT,
    validation_status VARCHAR,           -- approved, rejected, review
    fraud_score FLOAT,
    fraud_flags JSONB DEFAULT '[]',
    assigned_adjuster_id UUID REFERENCES adjusters(id),
    status VARCHAR DEFAULT 'open',       -- open, approved, denied, paid
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID REFERENCES claims(id),
    action VARCHAR NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),
    details JSONB DEFAULT '{}'
);

-- ===== Vector store table (RAG — used from September onward, created now) =====

CREATE TABLE policy_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id UUID REFERENCES policies(id),
    clause_text TEXT NOT NULL,
    embedding vector(768),  -- nomic-embed-text output dimension
    created_at TIMESTAMP DEFAULT NOW()
);

-- Similarity search index (approximate nearest neighbor)
CREATE INDEX ON policy_embeddings USING ivfflat (embedding vector_cosine_ops);

-- ===== Helpful indexes for common lookups =====
CREATE INDEX idx_claims_policy_id ON claims(policy_id);
CREATE INDEX idx_claims_status ON claims(status);
CREATE INDEX idx_policies_policy_number ON policies(policy_number);
CREATE INDEX idx_audit_log_claim_id ON audit_log(claim_id);