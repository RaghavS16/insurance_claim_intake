"""Close production isolation, token, audit, versioning and knowledge-provenance gaps.

This forward-only migration is intentionally idempotent because revision 0000
materializes the current ORM schema on a fresh PostgreSQL database.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def _tables(bind):
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table):
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _add_column(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    if column.name not in _columns(bind, table):
        op.add_column(table, column)


def _add_index(name: str, table: str, columns: list[str], unique: bool = False) -> None:
    bind = op.get_bind()
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes(table)}
    if name not in indexes:
        op.create_index(name, table, columns, unique=unique)


def _ensure_table(name: str, creator) -> None:
    if name not in _tables(op.get_bind()):
        creator()


def upgrade() -> None:
    bind = op.get_bind()

    # Child claim/auth records inherit their tenant from the canonical parent.
    child_claim_tables = (
        "claim_assignments",
        "claim_requirements",
        "claim_evidence",
        "claim_evidence_requests",
        "claim_decisions",
        "claim_notes",
        "claim_audit_events",
        "copilot_analyses",
        "claim_facts",
        "claim_exceptions",
        "claim_submissions",
        "conversation_turns",
    )
    auth_child_tables = ("revoked_tokens", "password_reset_otps", "policy_link_audit")
    mfa_tables = ("mfa_challenges", "mfa_recovery_codes")

    for table in child_claim_tables + auth_child_tables + mfa_tables:
        if table in _tables(bind):
            _add_column(table, sa.Column("tenant_id", sa.String(36), nullable=True))
            _add_index(f"ix_{table}_tenant_id", table, ["tenant_id"])

    if "knowledge_documents" in _tables(bind):
        _add_column("knowledge_documents", sa.Column("tenant_id", sa.String(36), nullable=True))
        _add_column("knowledge_documents", sa.Column("jurisdiction", sa.String(120), nullable=True))
        _add_index("ix_knowledge_documents_tenant_id", "knowledge_documents", ["tenant_id"])
        _add_index("ix_knowledge_documents_jurisdiction", "knowledge_documents", ["jurisdiction"])
    if "knowledge_chunks" in _tables(bind):
        _add_column("knowledge_chunks", sa.Column("tenant_id", sa.String(36), nullable=True))
        _add_index("ix_knowledge_chunks_tenant_id", "knowledge_chunks", ["tenant_id"])

    if "outbox_events" in _tables(bind):
        _add_column("outbox_events", sa.Column("tenant_id", sa.String(36), nullable=True))
        _add_index("ix_outbox_events_tenant_id", "outbox_events", ["tenant_id"])

    # Backfill child ownership from canonical tenant-owned parents.
    for table in child_claim_tables:
        if table in _tables(bind):
            bind.execute(sa.text(f"""
                UPDATE {table} child
                   SET tenant_id = claims.tenant_id
                  FROM claims
                 WHERE child.claim_id = claims.id
                   AND child.tenant_id IS NULL
            """))

    for table in auth_child_tables + mfa_tables:
        if table in _tables(bind):
            bind.execute(sa.text(f"""
                UPDATE {table} child
                   SET tenant_id = users.tenant_id
                  FROM users
                 WHERE child.user_id = users.id
                   AND child.tenant_id IS NULL
            """))

    if "knowledge_documents" in _tables(bind):
        first_tenant = bind.execute(
            sa.text("SELECT id FROM tenants ORDER BY created_at, id LIMIT 1")
        ).scalar()
        if first_tenant:
            bind.execute(sa.text("""
                UPDATE knowledge_documents
                   SET tenant_id = :tid
                 WHERE tenant_id IS NULL
            """).bindparams(tid=str(first_tenant)))
        bind.execute(sa.text("""
            UPDATE knowledge_chunks kc
               SET tenant_id = kd.tenant_id
              FROM knowledge_documents kd
             WHERE kc.document_id = kd.id
               AND kc.tenant_id IS NULL
        """))

    if "outbox_events" in _tables(bind):
        bind.execute(sa.text("""
            UPDATE outbox_events oe
               SET tenant_id = c.tenant_id
              FROM claims c
             WHERE oe.aggregate_type = 'claim'
               AND oe.aggregate_id = c.id
               AND oe.tenant_id IS NULL
        """))

    # Tenant-local policy numbers.
    if "policies" in _tables(bind):
        bind.execute(sa.text(
            "ALTER TABLE policies DROP CONSTRAINT IF EXISTS policies_policy_number_key"
        ))
        bind.execute(sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_policy_tenant_number "
            "ON policies (tenant_id, policy_number)"
        ))

    # Prevent duplicate active assignments under concurrency.
    if "claim_assignments" in _tables(bind):
        bind.execute(sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_claim_assignment "
            "ON claim_assignments (claim_id) WHERE is_active"
        ))

    # Rotating refresh tokens.
    if "refresh_tokens" not in _tables(bind):
        op.create_table(
            "refresh_tokens",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("tenant_id", sa.String(36), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
            sa.Column("family_id", sa.String(36), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("replaced_by_id", sa.String(36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("user_agent", sa.String(500), nullable=True),
            sa.Column("ip_address", sa.String(100), nullable=True),
        )
        _add_index("ix_refresh_tokens_tenant_id", "refresh_tokens", ["tenant_id"])
        _add_index("ix_refresh_tokens_user_active", "refresh_tokens", ["user_id", "revoked_at"])
        _add_index("ix_refresh_tokens_family", "refresh_tokens", ["family_id"])

    # System-wide immutable audit log.
    if "system_audit_events" not in _tables(bind):
        op.create_table(
            "system_audit_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("tenant_id", sa.String(36), nullable=False),
            sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("event_type", sa.String(120), nullable=False),
            sa.Column("resource_type", sa.String(80), nullable=False),
            sa.Column("resource_id", sa.String(150), nullable=True),
            sa.Column("action", sa.String(80), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        _add_index("ix_system_audit_events_tenant_id", "system_audit_events", ["tenant_id"])
        _add_index("ix_system_audit_events_created_at", "system_audit_events", ["created_at"])
        _add_index("ix_system_audit_events_type", "system_audit_events", ["event_type"])

    # Historical policy metadata snapshots.
    if "policy_versions" not in _tables(bind):
        op.create_table(
            "policy_versions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("tenant_id", sa.String(36), nullable=False),
            sa.Column("policy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("policies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("policy_type", sa.String(), nullable=False),
            sa.Column("coverage_amount", sa.Numeric(), nullable=False),
            sa.Column("deductible", sa.Numeric(), nullable=False),
            sa.Column("effective_date", sa.Date(), nullable=False),
            sa.Column("expiry_date", sa.Date(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("policy_id", "version_number", name="uq_policy_version_number"),
        )
        _add_index("ix_policy_versions_tenant_id", "policy_versions", ["tenant_id"])
        _add_index("ix_policy_versions_policy", "policy_versions", ["policy_id", "is_active"])

    bind.execute(sa.text("""
        INSERT INTO policy_versions(
            id, tenant_id, policy_id, version_number, policy_type,
            coverage_amount, deductible, effective_date, expiry_date,
            is_active, snapshot_json, created_at
        )
        SELECT :id_prefix || replace(p.id::text, '-', '')::text,
               p.tenant_id, p.id, 1, p.policy_type,
               p.coverage_amount, p.deductible, p.effective_date, p.expiry_date,
               p.is_active,
               json_build_object(
                   'policy_number', p.policy_number,
                   'customer_id', p.customer_id::text,
                   'policyholder_name', p.policyholder_name,
                   'policyholder_dob', p.policyholder_dob,
                   'policyholder_phone_last4', p.policyholder_phone_last4
               ),
               p.created_at
          FROM policies p
         WHERE NOT EXISTS (
               SELECT 1 FROM policy_versions pv
                WHERE pv.policy_id = p.id AND pv.version_number = 1
         )
    """).bindparams(id_prefix=str(uuid.uuid4())[:7]))

    # Fail closed before enforcing the DB tenant boundary.
    for table in child_claim_tables + auth_child_tables + mfa_tables + ("knowledge_documents", "knowledge_chunks"):
        if table in _tables(bind):
            nulls = bind.execute(sa.text(f"SELECT count(*) FROM {table} WHERE tenant_id IS NULL")).scalar() or 0
            if nulls:
                raise RuntimeError(f"0017 cannot enforce tenant isolation: {table} has {nulls} unowned rows.")
            op.alter_column(table, "tenant_id", nullable=False)

    if "outbox_events" in _tables(bind):
        # Claim outbox records must be tenant-owned; other aggregate types may be legacy-neutral.
        pass

    # PostgreSQL trigger-based append-only enforcement for audit/version rows.
    bind.execute(sa.text("""
        CREATE OR REPLACE FUNCTION prevent_immutable_audit_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'append-only record';
        END;
        $$ LANGUAGE plpgsql;
    """))
    for table, trigger in (
        ("system_audit_events", "trg_system_audit_immutable"),
        ("claim_audit_events", "trg_claim_audit_immutable"),
        ("policy_versions", "trg_policy_version_immutable"),
    ):
        if table in _tables(bind):
            bind.execute(sa.text(f"""
                DROP TRIGGER IF EXISTS {trigger} ON {table};
                CREATE TRIGGER {trigger}
                BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION prevent_immutable_audit_mutation();
            """))

def downgrade() -> None:
    raise RuntimeError("0017 is forward-only; use a new migration for production schema changes.")
