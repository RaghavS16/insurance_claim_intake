"""
Apply conversation turns and voice lifecycle migration to PostgreSQL database.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

backend_env = Path(__file__).resolve().parent.parent / "backend" / ".env"
load_dotenv(dotenv_path=backend_env)
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable is not set.")
    sys.exit(1)

print("Connecting to database...")
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

migration_sql = (Path(__file__).parent / "migrate_voice.sql").read_text(encoding="utf-8")
print("Executing migrate_voice.sql...")
cur.execute(migration_sql)
print("Migration applied successfully.")

cur.close()
conn.close()
