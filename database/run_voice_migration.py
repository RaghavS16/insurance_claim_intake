"""
Apply database/migrate_voice.sql to PostgreSQL database.
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
    print("ERROR: DATABASE_URL not set.")
    sys.exit(1)

print("Connecting to:", DATABASE_URL.split("@")[-1])
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

migration_sql = (Path(__file__).parent / "migrate_voice.sql").read_text(encoding="utf-8")
print("Executing migrate_voice.sql...")
cur.execute(migration_sql)
print("Migration applied successfully!")

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='claims' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
print("Claims columns:", cols)

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
tables = [r[0] for r in cur.fetchall()]
print("Tables in public schema:", tables)

cur.close()
conn.close()
print("Done!")
