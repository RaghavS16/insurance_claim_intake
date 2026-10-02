"""Add durable evidence verification fields."""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def _has_baseline():
    bind = op.get_bind()
    return (
        bind.dialect.name == "postgresql"
        and bind.execute(
            sa.text("SELECT to_regclass('public.schema_baseline')")
        ).scalar()
        is not None
    )


def upgrade():
    if _has_baseline():
        return
    op.add_column("claim_evidence", sa.Column("verification_status", sa.String(40), nullable=False, server_default="REVIEW_REQUIRED"))
    op.add_column("claim_evidence", sa.Column("verification_confidence", sa.Float(), nullable=True))
    op.add_column("claim_evidence", sa.Column("detected_document_type", sa.String(150), nullable=True))
    op.add_column("claim_evidence", sa.Column("requested_evidence_type", sa.String(150), nullable=True))
    op.create_index("ix_claim_evidence_verification_status", "claim_evidence", ["verification_status"])


def downgrade():
    if _has_baseline():
        return
    op.drop_index("ix_claim_evidence_verification_status", table_name="claim_evidence")
    op.drop_column("claim_evidence", "requested_evidence_type")
    op.drop_column("claim_evidence", "detected_document_type")
    op.drop_column("claim_evidence", "verification_confidence")
    op.drop_column("claim_evidence", "verification_status")
