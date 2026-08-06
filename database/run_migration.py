import psycopg2

conn = psycopg2.connect("postgresql://postgres:DBpassword@localhost:5433/insurance_claims")
conn.autocommit = True
cur = conn.cursor()

statements = [
    "ALTER TABLE claims ADD COLUMN IF NOT EXISTS ticket_id VARCHAR UNIQUE",
    "ALTER TABLE claims ADD COLUMN IF NOT EXISTS pipeline_state JSONB NOT NULL DEFAULT '{}'",
    "ALTER TABLE claims ADD COLUMN IF NOT EXISTS final_decision VARCHAR",
    "ALTER TABLE claims ADD COLUMN IF NOT EXISTS closure_status VARCHAR",
    "ALTER TABLE claims ADD COLUMN IF NOT EXISTS input_mode VARCHAR NOT NULL DEFAULT 'text'",
    "ALTER TABLE claims ADD COLUMN IF NOT EXISTS fraud_flags JSONB NOT NULL DEFAULT '[]'",
    "ALTER TABLE claims ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
    # Backfill ticket_id for any existing rows that are NULL
    "UPDATE claims SET ticket_id = 'CLAIM-' || UPPER(SUBSTRING(gen_random_uuid()::text, 1, 8)) WHERE ticket_id IS NULL",
]

for sql in statements:
    print(f"Running: {sql[:70]}...")
    cur.execute(sql)
    print("  OK")

# Verify
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='claims' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
print(f"\nClaims columns now: {cols}")

cur.close()
conn.close()
print("\nMigration complete!")
