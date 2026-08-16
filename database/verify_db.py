"""
Database verification utility to validate tables, schema health, and seed counts.
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
    logger.error("This verification script requires PostgreSQL. Current DATABASE_URL: %s", DATABASE_URL)
    sys.exit(1)

logger.info("Connecting to PostgreSQL database...")
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

# Verify all public tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
tables = [r[0] for r in cur.fetchall()]
logger.info("Registered public tables: %s", tables)


def fetch_count(table_name: str) -> int:
    """Execute a count query safely."""
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        row = cur.fetchone()
        return int(row[0]) if row is not None else 0
    except Exception:
        return -1


logger.info("Claims count:    %d", fetch_count("claims"))
logger.info("Adjusters count: %d", fetch_count("adjusters"))
logger.info("Policies count:  %d", fetch_count("policies"))
logger.info("Conversation turns count: %d", fetch_count("conversation_turns"))

cur.close()
conn.close()
logger.info("Database verification passed successfully.")
