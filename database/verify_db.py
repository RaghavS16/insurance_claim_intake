import psycopg2

conn = psycopg2.connect("postgresql://postgres:DBpassword@localhost:5433/insurance_claims")
conn.autocommit = True
cur = conn.cursor()

# Also ensure payment_requests table exists with all columns
cur.execute("""
    CREATE TABLE IF NOT EXISTS payment_requests (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        claim_id UUID NOT NULL REFERENCES claims(id),
        claimed_amount NUMERIC,
        deductible_amount NUMERIC,
        payout_amount NUMERIC,
        status VARCHAR NOT NULL DEFAULT 'pending_finance',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
""")
print("payment_requests: OK")

# Ensure audit_log table
cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        claim_id UUID REFERENCES claims(id),
        action VARCHAR NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        details JSONB NOT NULL DEFAULT '{}'
    )
""")
print("audit_log: OK")

# Verify all tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
tables = [r[0] for r in cur.fetchall()]
print(f"\nAll tables: {tables}")


def fetch_count(query: str) -> int:
    """Execute a COUNT query and safely return the result."""
    cur.execute(query)
    row = cur.fetchone()
    return int(row[0]) if row is not None else 0


print(f"Claims rows:    {fetch_count('SELECT COUNT(*) FROM claims')}")
print(f"Adjusters rows: {fetch_count('SELECT COUNT(*) FROM adjusters')}")
print(f"Policies rows:  {fetch_count('SELECT COUNT(*) FROM policies')}")

cur.close()
conn.close()
print("\nDatabase is healthy!")
