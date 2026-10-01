"""Canonical workflow persistence: claim facts, exceptions and exactly-once submissions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "claim_facts" not in tables:
        op.create_table(
            "claim_facts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
            sa.Column("fact_key", sa.String(150), nullable=False),
            sa.Column("value_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("state", sa.String(40), nullable=False, server_default="PROPOSED"),
            sa.Column("source_type", sa.String(60), nullable=False),
            sa.Column("source_id", sa.String(150), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("provenance_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("claim_id", "fact_key", name="uq_claim_fact_key"),
        )
        op.create_index("ix_claim_facts_claim", "claim_facts", ["claim_id"])
        op.create_index("ix_claim_facts_state", "claim_facts", ["state"])

    if "claim_exceptions" not in tables:
        op.create_table(
            "claim_exceptions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
            sa.Column("event_type", sa.String(100), nullable=False),
            sa.Column("severity", sa.String(30), nullable=False, server_default="medium"),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("source_type", sa.String(60), nullable=False, server_default="SYSTEM_RULE"),
            sa.Column("source_id", sa.String(150), nullable=True),
            sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("status", sa.String(30), nullable=False, server_default="open"),
            sa.Column("resolution_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_claim_exceptions_claim", "claim_exceptions", ["claim_id", "blocking", "status"])
        op.create_index("ix_claim_exceptions_status", "claim_exceptions", ["status"])

    if "claim_submissions" not in tables:
        op.create_table(
            "claim_submissions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
            sa.Column("idempotency_key", sa.String(200), nullable=False),
            sa.Column("status", sa.String(40), nullable=False, server_default="accepted"),
            sa.Column("submitted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("result_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("claim_id", name="uq_claim_submission_claim"),
            sa.UniqueConstraint("idempotency_key", name="uq_claim_submission_idempotency"),
        )


def downgrade():
    op.drop_table("claim_submissions")
    op.drop_index("ix_claim_exceptions_status", table_name="claim_exceptions")
    op.drop_index("ix_claim_exceptions_claim", table_name="claim_exceptions")
    op.drop_table("claim_exceptions")
    op.drop_index("ix_claim_facts_state", table_name="claim_facts")
    op.drop_index("ix_claim_facts_claim", table_name="claim_facts")
    op.drop_table("claim_facts")
