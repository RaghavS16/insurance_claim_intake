"""Persist adjuster evidence requests and link claimant responses."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "claim_evidence_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("adjuster_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("adjusters.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="open"),
        sa.Column("response_note", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_claim_evidence_requests_claim", "claim_evidence_requests", ["claim_id"])
    op.create_index("ix_claim_evidence_requests_status", "claim_evidence_requests", ["status"])
    op.add_column(
        "claim_evidence",
        sa.Column("request_id", sa.String(36), sa.ForeignKey("claim_evidence_requests.id", ondelete="SET NULL"), nullable=True),
    )

def downgrade():
    op.drop_column("claim_evidence", "request_id")
    op.drop_index("ix_claim_evidence_requests_status", table_name="claim_evidence_requests")
    op.drop_index("ix_claim_evidence_requests_claim", table_name="claim_evidence_requests")
    op.drop_table("claim_evidence_requests")
