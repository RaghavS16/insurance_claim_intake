"""Harden tenant boundaries, auth state, and RAG provenance.

The migration is intentionally idempotent because the repository's 0000 baseline
creates ORM metadata directly. Existing rows are backfilled from their owning
claim/user/document before tenant columns become mandatory.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def _add_column(inspector, table: str, column: sa.Column) -> None:
    if inspector.has_table(table) and not _has_column(inspector, table, column.name):
        op.add_column(table, column)


def _has_index(inspector, table: str, name: str) -> bool:
    return any(i.get("name") == name for i in inspector.get_indexes(table))


def _add_index(inspector, table: str, name: str, columns: list[str]) -> None:
    if inspector.has_table(table) and not _has_index(inspector, table, name):
        op.create_index(name, table, columns)


def _backfill_from_claim(table: str) -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        f"UPDATE {table} t SET tenant_id = c.tenant_id "
        "FROM claims c WHERE t.claim_id = c.id AND (t.tenant_id IS NULL OR t.tenant_id = '')"
    ))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    # Core child records.
    child_tables = [
        "claim_assignments", "claim_requirements", "claim_evidence",
        "claim_evidence_requests", "claim_decisions", "claim_notes",
        "claim_audit_events", "copilot_analyses", "claim_facts",
        "claim_exceptions", "claim_submissions",
    ]
    for table in child_tables:
        _add_column(inspector, table, sa.Column("tenant_id", sa.String(36), nullable=True))
    inspector = sa.inspect(op.get_bind())

    for table in child_tables:
        if inspector.has_table(table):
            _backfill_from_claim(table)

    # Outbox events are currently claim aggregates. Do not invent a tenant for
    # unrelated legacy events; leave them visible for operators to reconcile.
    _add_column(inspector, "outbox_events", sa.Column("tenant_id", sa.String(36), nullable=True))
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("outbox_events"):
        op.get_bind().execute(sa.text(
            "UPDATE outbox_events o SET tenant_id = c.tenant_id "
            "FROM claims c WHERE o.aggregate_type = 'claim' AND o.aggregate_id = c.id "
            "AND (o.tenant_id IS NULL OR o.tenant_id = '')"
        ))

    # Auth-owned records.
    for table in ("revoked_tokens", "password_reset_otps", "policy_link_audit"):
        _add_column(inspector, table, sa.Column("tenant_id", sa.String(36), nullable=True))
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("revoked_tokens"):
        op.get_bind().execute(sa.text(
            "UPDATE revoked_tokens r SET tenant_id = u.tenant_id FROM users u "
            "WHERE r.user_id = u.id AND (r.tenant_id IS NULL OR r.tenant_id = '')"
        ))
    if inspector.has_table("password_reset_otps"):
        op.get_bind().execute(sa.text(
            "UPDATE password_reset_otps p SET tenant_id = u.tenant_id FROM users u "
            "WHERE p.user_id = u.id AND (p.tenant_id IS NULL OR p.tenant_id = '')"
        ))
    if inspector.has_table("policy_link_audit"):
        op.get_bind().execute(sa.text(
            "UPDATE policy_link_audit p SET tenant_id = u.tenant_id FROM users u "
            "WHERE p.user_id = u.id AND (p.tenant_id IS NULL OR p.tenant_id = '')"
        ))

    # Knowledge provenance.
    _add_column(inspector, "knowledge_documents", sa.Column("tenant_id", sa.String(36), nullable=True))
    _add_column(inspector, "knowledge_documents", sa.Column("jurisdiction", sa.String(120), nullable=True))
    _add_column(inspector, "knowledge_documents", sa.Column("document_version", sa.String(120), nullable=True))
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("knowledge_documents"):
        op.get_bind().execute(sa.text(
            "UPDATE knowledge_documents d SET tenant_id = u.tenant_id FROM users u "
            "WHERE d.uploaded_by = u.id AND (d.tenant_id IS NULL OR d.tenant_id = '')"
        ))
    if inspector.has_table("knowledge_documents"):
        op.get_bind().execute(sa.text(
            "UPDATE knowledge_documents SET tenant_id = COALESCE(tenant_id, '') "
            "WHERE tenant_id IS NULL"
        ))

    _add_column(inspector, "knowledge_chunks", sa.Column("tenant_id", sa.String(36), nullable=True))
    _add_column(inspector, "knowledge_chunks", sa.Column("page_number", sa.Integer(), nullable=True))
    _add_column(inspector, "knowledge_chunks", sa.Column("section_number", sa.String(120), nullable=True))
    _add_column(inspector, "knowledge_chunks", sa.Column("clause_number", sa.String(120), nullable=True))
    _add_column(inspector, "knowledge_chunks", sa.Column("citation_label", sa.String(300), nullable=True))
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("knowledge_chunks"):
        op.get_bind().execute(sa.text(
            "UPDATE knowledge_chunks k SET tenant_id = d.tenant_id "
            "FROM knowledge_documents d WHERE k.document_id = d.id "
            "AND (k.tenant_id IS NULL OR k.tenant_id = '')"
        ))
        op.get_bind().execute(sa.text(
            "UPDATE knowledge_chunks SET tenant_id = COALESCE(tenant_id, '') "
            "WHERE tenant_id IS NULL"
        ))

    # New durable auth/workflow/audit tables.
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("family_id", sa.String(36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by", sa.String(36), nullable=True),
        if_not_exists=True,
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], if_not_exists=True)
    op.create_index("ix_refresh_tokens_tenant_id", "refresh_tokens", ["tenant_id"], if_not_exists=True)
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"], if_not_exists=True)
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"], if_not_exists=True)

    op.create_table(
        "claim_submission_confirmations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("confirmed_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("claim_state_version", sa.Integer(), nullable=False),
        sa.Column("summary_sha256", sa.String(64), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        if_not_exists=True,
    )
    op.create_index("ix_claim_submission_confirmations_claim_id", "claim_submission_confirmations", ["claim_id"], if_not_exists=True)
    op.create_index("ix_claim_submission_confirmations_tenant_id", "claim_submission_confirmations", ["tenant_id"], if_not_exists=True)

    op.create_table(
        "system_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", sa.String(150), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=True),
        sa.Column("event_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        if_not_exists=True,
    )
    op.create_unique_constraint("uq_system_audit_sequence", "system_audit_events", ["tenant_id", "sequence_no"])
    op.create_index("ix_system_audit_tenant_created", "system_audit_events", ["tenant_id", "created_at"], if_not_exists=True)

    # New rows must have tenant context. Existing empty-string tenant values are
    # retained as quarantined legacy records and are never returned by tenant-scoped code.
    for table in child_tables + ["outbox_events", "revoked_tokens", "password_reset_otps", "policy_link_audit", "knowledge_documents", "knowledge_chunks"]:
        inspector = sa.inspect(op.get_bind())
        if inspector.has_table(table) and _has_column(inspector, table, "tenant_id"):
            op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"], if_not_exists=True)


def downgrade() -> None:
    op.drop_table("system_audit_events")
    op.drop_table("claim_submission_confirmations")
    op.drop_table("refresh_tokens")
