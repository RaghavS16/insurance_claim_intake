"""Complete tenant-scoped production workflow schema.

Adds tenant boundaries to every tenant-owned workflow/knowledge table and
persists explicit final-submission confirmation metadata.
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

TENANT_TABLES = (
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
    "outbox_events",
    "mfa_challenges",
    "mfa_recovery_codes",
    "conversation_turns",
    "knowledge_documents",
    "revoked_tokens",
    "policy_link_audit",
    "password_reset_otps",
    "voice_sessions",
)

def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)

def _columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}

def upgrade():
    bind = op.get_bind()

    # Every existing row from 0016 belongs to the tenant already attached to
    # its parent claim/user/document. Backfill before tightening constraints.
    for table in TENANT_TABLES:
        if not _has_table(bind, table):
            continue
        cols = _columns(bind, table)
        if "tenant_id" not in cols:
            op.add_column(table, sa.Column("tenant_id", sa.String(36), nullable=True))

        if table in {"claim_assignments","claim_requirements","claim_evidence","claim_evidence_requests",
                     "claim_decisions","claim_notes","claim_audit_events","copilot_analyses",
                     "claim_facts","claim_exceptions","claim_submissions","outbox_events"}:
            op.execute(sa.text(
                f"UPDATE {table} t SET tenant_id = c.tenant_id "
                f"FROM claims c WHERE t.claim_id = c.id AND t.tenant_id IS NULL"
            ))
        elif table in {"conversation_turns","voice_sessions"}:
            op.execute(sa.text(
                f"UPDATE {table} t SET tenant_id = c.tenant_id "
                f"FROM claims c WHERE t.claim_id = c.id AND t.tenant_id IS NULL"
            ))
        elif table == "knowledge_documents":
            op.execute(sa.text(
                "UPDATE knowledge_documents d SET tenant_id = u.tenant_id "
                "FROM users u WHERE d.uploaded_by = u.id AND d.tenant_id IS NULL"
            ))
        else:
            op.execute(sa.text(
                f"UPDATE {table} t SET tenant_id = u.tenant_id "
                f"FROM users u WHERE t.user_id = u.id AND t.tenant_id IS NULL"
            ))

        # Any remaining legacy rows get the sole legacy tenant from 0016.
        op.execute(sa.text(
            "UPDATE " + table + " SET tenant_id = (SELECT id FROM tenants ORDER BY created_at LIMIT 1) "
            "WHERE tenant_id IS NULL"
        ))
        op.alter_column(table, "tenant_id", nullable=False)
        op.create_index(f"ix_{table}_tenant_id_0017", table, ["tenant_id"], if_not_exists=True)

    # Exact metadata required for submission confirmation.
    if _has_table(bind, "claims"):
        cols = _columns(bind, "claims")
        if "final_submission_confirmation_digest" not in cols:
            op.add_column("claims", sa.Column("final_submission_confirmation_digest", sa.String(64), nullable=True))
        if "final_submission_confirmed_at" not in cols:
            op.add_column("claims", sa.Column("final_submission_confirmed_at", sa.DateTime(timezone=True), nullable=True))

def downgrade():
    bind = op.get_bind()
    if _has_table(bind, "claims"):
        cols = _columns(bind, "claims")
        if "final_submission_confirmed_at" in cols:
            op.drop_column("claims", "final_submission_confirmed_at")
        if "final_submission_confirmation_digest" in cols:
            op.drop_column("claims", "final_submission_confirmation_digest")
    for table in reversed(TENANT_TABLES):
        if _has_table(bind, table):
            op.drop_index(f"ix_{table}_tenant_id_0017", table_name=table)
            if "tenant_id" in _columns(bind, table):
                op.drop_column(table, "tenant_id")
