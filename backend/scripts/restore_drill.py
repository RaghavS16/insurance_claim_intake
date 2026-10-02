"""Execute a measurable PostgreSQL dump/restore drill against an isolated database."""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo


def _admin_url(source_url: str) -> str:
    info = conninfo_to_dict(source_url)
    info["dbname"] = "postgres"
    return make_conninfo(**info)


def _db_url(source_url: str, dbname: str) -> str:
    info = conninfo_to_dict(source_url)
    info["dbname"] = dbname
    return make_conninfo(**info)


def _run(*args: str) -> None:
    subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def main() -> None:
    source_url = os.environ["DATABASE_URL"]
    restore_db = f"dr_restore_{uuid.uuid4().hex[:10]}"
    dump_path = Path(os.environ.get("DR_DUMP_PATH", "/tmp/insurance_claims_dr.dump"))
    admin_url = _admin_url(source_url)
    restore_url = _db_url(source_url, restore_db)
    sentinel = str(uuid.uuid4())
    started = time.perf_counter()

    with psycopg.connect(source_url) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO tenants (id, name, status, created_at) VALUES (%s, %s, 'active', now())", (sentinel, 'DR Drill Tenant'))

    dump_started = time.perf_counter()
    _run("pg_dump", "--format=custom", "--no-owner", "--file", str(dump_path), source_url)
    dump_seconds = time.perf_counter() - dump_started

    try:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute('CREATE DATABASE "' + restore_db + '"')

        restore_started = time.perf_counter()
        _run("pg_restore", "--no-owner", "--no-privileges", "--dbname", restore_url, str(dump_path))
        restore_seconds = time.perf_counter() - restore_started

        with psycopg.connect(restore_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version_num FROM alembic_version")
                versions = [str(row[0]) for row in cur.fetchall()]
                cur.execute("SELECT count(*) FROM tenants WHERE id = %s", (sentinel,))
                sentinel_count = int(cur.fetchone()[0])
                required_tables = {
                    "claims", "claim_requirements", "claim_evidence",
                    "claim_submissions", "system_audit_events", "outbox_events",
                    "voice_sessions", "webauthn_credentials",
                }
                cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                actual_tables = {str(row[0]) for row in cur.fetchall()}
                missing = sorted(required_tables - actual_tables)

        if sentinel_count != 1:
            raise RuntimeError("DR sentinel row was not restored")
        if missing:
            raise RuntimeError(f"Restored database is missing required tables: {missing}")
        if not versions:
            raise RuntimeError("Restored database has no Alembic version")

        report = {
            "status": "passed",
            "restore_database": restore_db,
            "migration_versions": versions,
            "dump_seconds": round(dump_seconds, 3),
            "restore_seconds": round(restore_seconds, 3),
            "total_seconds": round(time.perf_counter() - started, 3),
            "sentinel_restored": True,
        }
        Path(os.environ.get("DR_REPORT_PATH", "/tmp/insurance_claims_dr_report.json")).write_text(
            json.dumps(report, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2))
    finally:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute('DROP DATABASE IF EXISTS "' + restore_db + '"')
        try:
            dump_path.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
