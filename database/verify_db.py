"""
database/verify_db.py

R4-6: Previously this script hardcoded the DB connection string.
Now reads DATABASE_URL from the environment (or backend/.env) so
it can be run safely without committing credentials to source control.

Usage:
    DATABASE_URL=postgresql://postgres:DBpassword@localhost:5433/insurance_claims python database/verify_db.py
"""
import logging
import os
import sys
from pathlib import Path

# Load backend/.env so the script works when run from the repo root.
try:
    from dotenv import load_dotenv
    backend_env = Path(__file__).resolve().parent.parent / "backend" / ".env"
    load_dotenv(dotenv_path=backend_env)
    load_dotenv()
except ImportError:
    pass

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.error(
        "DATABASE_URL environment variable is not set. "
        "Set it in backend/.env or export it before running this script."
    )
    sys.exit(1)

if not DATABASE_URL.startswith("postgresql"):
    logger.error("This verify script only supports PostgreSQL. Got: %s", DATABASE_URL)
    sys.exit(1)

logger.info("Connecting to: %s", DATABASE_URL.split("@")[-1])
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

# Ensure payment_requests table exists with all columns
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
logger.info("payment_requests: OK")

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
logger.info("audit_log: OK")

# Verify all tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
tables = [r[0] for r in cur.fetchall()]
logger.info("All tables: %s", tables)


def fetch_count(query: str) -> int:
    """Execute a COUNT query and safely return the result."""
    cur.execute(query)
    row = cur.fetchone()
    return int(row[0]) if row is not None else 0


logger.info("Claims rows:    %d", fetch_count("SELECT COUNT(*) FROM claims"))
logger.info("Adjusters rows: %d", fetch_count("SELECT COUNT(*) FROM adjusters"))
logger.info("Policies rows:  %d", fetch_count("SELECT COUNT(*) FROM policies"))

cur.close()
conn.close()
logger.info("Database is healthy!")
