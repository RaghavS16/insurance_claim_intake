"""
database/run_migration.py

R4-6: Previously this script hardcoded the DB connection string.
Now reads DATABASE_URL from the environment (or backend/.env) so
it can be run safely without committing credentials to source control.

Usage:
    # with docker-compose:
    DATABASE_URL=postgresql://postgres:DBpassword@localhost:5433/insurance_claims python database/run_migration.py
    # or with .env loaded by python-dotenv:
    cd backend && python ../database/run_migration.py
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
    load_dotenv()  # also pick up a .env in the cwd
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
    logger.error("This migration script only supports PostgreSQL. Got: %s", DATABASE_URL)
    sys.exit(1)

logger.info("Connecting to: %s", DATABASE_URL.split("@")[-1])  # log host/db, not credentials
conn = psycopg2.connect(DATABASE_URL)
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
    logger.info("Running: %s ...", sql[:80])
    cur.execute(sql)
    logger.info("  OK")

# Verify
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='claims' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
logger.info("Claims columns: %s", cols)

cur.close()
conn.close()
logger.info("Migration complete!")
