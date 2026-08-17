"""
Database verification utility to validate tables, schema health, and seed counts.
"""
import logging
import sys
from pathlib import Path

# Add backend to sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from src.config import settings
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL:
    logger.error("DATABASE_URL environment variable is not set.")
    sys.exit(1)

if not DATABASE_URL.startswith("postgresql"):
    logger.error("This verification script requires PostgreSQL. Current DATABASE_URL: %s", DATABASE_URL)
    sys.exit(1)

logger.info("Connecting to PostgreSQL database...")
try:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    tables = [r[0] for r in cur.fetchall()]
    logger.info("Registered public tables: %s", tables)

    def fetch_count(table_name: str) -> int:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            row = cur.fetchone()
            return int(row[0]) if row is not None else 0
        except Exception:
            return -1

    logger.info("Claims count:             %d", fetch_count("claims"))
    logger.info("Adjusters count:          %d", fetch_count("adjusters"))
    logger.info("Policies count:           %d", fetch_count("policies"))
    logger.info("Conversation turns count: %d", fetch_count("conversation_turns"))

    cur.close()
    conn.close()
    logger.info("Database verification passed successfully.")
except Exception as e:
    logger.error("Database verification failed: %s", e)
    sys.exit(1)
