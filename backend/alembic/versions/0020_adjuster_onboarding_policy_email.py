from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("policies"):
        columns = {c["name"] for c in inspector.get_columns("policies")}
        if "policyholder_email" not in columns:
            op.add_column("policies", sa.Column("policyholder_email", sa.String(), nullable=True))

    if not inspector.has_table("adjuster_invitations"):
        op.create_table(
            "adjuster_invitations",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("email", sa.String(length=254), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("phone", sa.String(length=30), nullable=False),
            sa.Column("specialization", sa.String(length=60), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("accepted_user_id", sa.String(length=36), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("token_hash", name="uq_adjuster_invitation_token_hash"),
        )
        op.create_index("ix_adjuster_invitations_tenant", "adjuster_invitations", ["tenant_id"])
        op.create_index("ix_adjuster_invitations_email", "adjuster_invitations", ["email"])
        op.create_index("ix_adjuster_invitations_expires", "adjuster_invitations", ["expires_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("adjuster_invitations"):
        for index in ("ix_adjuster_invitations_expires", "ix_adjuster_invitations_email", "ix_adjuster_invitations_tenant"):
            op.drop_index(index, table_name="adjuster_invitations")
        op.drop_table("adjuster_invitations")
    if inspector.has_table("policies") and "policyholder_email" in {c["name"] for c in inspector.get_columns("policies")}:
        op.drop_column("policies", "policyholder_email")
