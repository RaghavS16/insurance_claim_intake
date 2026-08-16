"""
Database migration script to ensure schema compatibility for claims table.
"""
import logging
import os
import sys
from pathlib import Path

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
    logger.error("DATABASE_URL environment variable is not set.")
    sys.exit(1)

if not DATABASE_URL.startswith("postgresql"):
    logger.error("This migration script only supports PostgreSQL. Got: %s", DATABASE_URL)
    sys.exit(1)

logger.info("Connecting to database...")
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
    "UPDATE claims SET ticket_id = 'CLAIM-' || UPPER(SUBSTRING(gen_random_uuid()::text, 1, 8)) WHERE ticket_id IS NULL",
]

for sql in statements:
    logger.info("Executing: %s", sql[:60])
    cur.execute(sql)

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='claims' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
logger.info("Claims columns: %s", cols)

cur.close()
conn.close()
logger.info("Migration completed successfully.")
